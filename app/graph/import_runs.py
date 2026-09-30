"""Running every configured source through a real import (`POST /api/import`): the configured
filesystem directories and Kubernetes clusters, each as its own discovery run, sharing one
migration-mapping index and one tombstone set per request.

Moved out of `app.api.import_api` so the route only maps outcomes to HTTP.
"""

import logging
import time
import uuid

from app.graph.importer import (
    ImportRunStats,
    import_all_sources,
    import_kubernetes_source,
)
from app.ingestion.import_report import ConfiguredRun
from app.settings import SourcesConfig
from app.sources.migration_mappings import load_migration_mappings
from app.sources.tombstones import load_tombstones

logger = logging.getLogger("architecture_intelligence.import")


class ImportConfigurationError(Exception):
    """The operator's configured migration mappings or tombstones cannot be loaded - a
    configuration error for the whole request, never a per-source data problem."""


def _log_run(import_id: str, run_stats: ImportRunStats, duration_ms: int) -> None:
    for source_instance_id, stats in run_stats.per_source.items():
        logger.info(
            "Imported import_id=%s source=%s locator=%s result=%s nodes_written=%d "
            "relations_written=%d nodes_expired=%d relations_expired=%d "
            "graph_revision_advanced=%s duration_ms=%d",
            import_id,
            source_instance_id,
            stats.locator,
            stats.result,
            stats.nodes_written,
            stats.relations_written,
            stats.nodes_expired,
            stats.relations_expired,
            stats.graph_revision_advanced,
            duration_ms,
        )
    if run_stats.removed_source_instance_ids:
        logger.info(
            "Removed import_id=%s sources=%s",
            import_id,
            ",".join(run_stats.removed_source_instance_ids),
        )


def run_all_configured_sources(
    sources: SourcesConfig, *, driver, database: str
) -> tuple[str, list[ConfiguredRun]]:
    """Imports every configured filesystem directory and Kubernetes cluster, each as its own
    discovery run (I1 spec §6), and returns the request's import id with one `ConfiguredRun` per
    configured source. Raises `ImportConfigurationError` - before touching the driver - when the
    configured migration mappings or tombstones fail to load."""
    # I1 spec §5.1.1: "Missing or modified migration configuration is diagnosed and MUST NOT fall
    # back to a directory slug or name-derived identity" - loaded once per request (not once per
    # configured source directory) since the same shared-identity index applies uniformly across
    # every directory's own discovery run. A broken configured migration file is an operator
    # configuration error, not a per-source data problem, so it fails the whole request loudly
    # rather than silently importing with a partial/empty index.
    migration_index, migration_diagnostics = load_migration_mappings(sources.migrations)
    if migration_diagnostics:
        raise ImportConfigurationError(
            "migration mapping configuration is invalid: "
            f"{[d.message for d in migration_diagnostics]}"
        )

    # I2 Draft 0.2 §3 prerequisite slice's minimal operator-facing tombstone surface - loaded once
    # per request, mirroring the migration-mapping load above; a broken configured tombstone file is
    # an operator configuration error, not a per-source data problem.
    tombstones, tombstone_diagnostics = load_tombstones(sources.tombstones)
    if tombstone_diagnostics:
        raise ImportConfigurationError(
            f"tombstone configuration is invalid: {[d.message for d in tombstone_diagnostics]}"
        )

    import_id = uuid.uuid4().hex
    run_results = []
    for source_config in sources.directories:
        start = time.perf_counter()
        run_stats = import_all_sources(
            driver,
            database=database,
            source_config=source_config,
            migration_mappings=migration_index,
            tombstones=tombstones,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        _log_run(import_id, run_stats, duration_ms)
        run_results.append(
            ConfiguredRun(
                kind="filesystem",
                configured_source_id=source_config.id,
                root=source_config.root,
                stats=run_stats,
            )
        )
    for cluster_config in sources.clusters:
        start = time.perf_counter()
        run_stats = import_kubernetes_source(
            driver,
            database=database,
            source_config=cluster_config,
            migration_mappings=migration_index,
            tombstones=tombstones,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        _log_run(import_id, run_stats, duration_ms)
        run_results.append(
            ConfiguredRun(
                kind="kubernetes",
                configured_source_id=cluster_config.id,
                root=cluster_config.root,
                stats=run_stats,
            )
        )
    return import_id, run_results
