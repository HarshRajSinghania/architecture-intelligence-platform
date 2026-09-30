from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.import_api import _run_all_configured_sources
from app.canonical.infrastructure import KubernetesEvidenceMode
from app.graph.importer import ImportRunStats
from app.ingestion.import_report import ConfiguredRun
from app.settings import AppConfig, Secrets, Settings, SourcesConfig
from app.sources.inventory import InventoryStatus
from app.sources.model import KubernetesSourceConfig


def _settings(*, migrations: list[Path]) -> Settings:
    config = AppConfig(sources=SourcesConfig(directories=[], migrations=migrations))
    return Settings(config=config, secrets=Secrets(neo4j_user="neo4j", neo4j_password="test"))


def test_no_configured_migrations_runs_with_no_directories_and_no_error():
    settings = _settings(migrations=[])
    import_id, run_results = _run_all_configured_sources(settings, driver=None)
    assert import_id
    assert run_results == []


def test_a_missing_configured_migration_file_raises_before_touching_the_driver(tmp_path):
    """I1 spec §5.1.1: "Missing or modified migration configuration is diagnosed and MUST NOT fall
    back to a directory slug or name-derived identity" - a broken configured migration path must
    fail the whole request loudly, not silently import with an empty/partial index. The driver is
    passed as None here and must never be touched, since the failure happens before any per-source
    loop iteration runs."""
    settings = _settings(migrations=[tmp_path / "does-not-exist.yaml"])
    with pytest.raises(HTTPException) as exc_info:
        _run_all_configured_sources(settings, driver=None)
    assert exc_info.value.status_code == 500
    assert "migration mapping configuration is invalid" in exc_info.value.detail


def test_configured_clusters_are_imported_alongside_configured_directories(tmp_path):
    # I2 Draft 0.2 slice 2b-i: sources.clusters is a second, source-kind-neutral loop alongside
    # sources.directories - mocked here (a unit test, no real Neo4j) to confirm the wiring calls
    # import_kubernetes_source once per configured cluster with the right config object.
    cluster_config = KubernetesSourceConfig(
        id="checkout-cluster",
        root=tmp_path,
        envelope_relative_path="envelope.yaml",
        cluster_uid="cluster-uid",
        evidence_mode=KubernetesEvidenceMode.CAPTURED_RESOURCE,
        authorized_producer="producer",
        authority_record="authority",
    )
    config = AppConfig(sources=SourcesConfig(directories=[], clusters=[cluster_config]))
    settings = Settings(config=config, secrets=Secrets(neo4j_user="neo4j", neo4j_password="test"))

    stub_stats = ImportRunStats(
        inventory_status=InventoryStatus.COMPLETE,
        committed=True,
        per_source={},
        removed_source_instance_ids=(),
        diagnostics=(),
    )
    with patch("app.graph.import_runs.import_kubernetes_source") as mock_import_kubernetes_source:
        mock_import_kubernetes_source.return_value = stub_stats
        import_id, run_results = _run_all_configured_sources(settings, driver="fake-driver")

    assert import_id
    mock_import_kubernetes_source.assert_called_once()
    call_kwargs = mock_import_kubernetes_source.call_args.kwargs
    assert call_kwargs["source_config"] is cluster_config
    # v0.5.0 I5 F2: each run is carried with its kind, configured id and root, so the import
    # report can say which configured source a run belongs to.
    assert run_results == [
        ConfiguredRun(
            kind="kubernetes",
            configured_source_id="checkout-cluster",
            root=tmp_path,
            stats=stub_stats,
        )
    ]


def test_configuration_errors_are_a_domain_error_below_the_route(tmp_path):
    from app.graph.import_runs import ImportConfigurationError, run_all_configured_sources

    sources = SourcesConfig(directories=[], migrations=[tmp_path / "missing-migrations.yaml"])
    with pytest.raises(
        ImportConfigurationError, match="migration mapping configuration is invalid"
    ):
        run_all_configured_sources(sources, driver=None, database="neo4j")

    sources = SourcesConfig(directories=[], tombstones=[tmp_path / "missing-tombstones.yaml"])
    with pytest.raises(ImportConfigurationError, match="tombstone configuration is invalid"):
        run_all_configured_sources(sources, driver=None, database="neo4j")


def test_a_missing_configured_tombstone_file_is_a_500_with_the_same_detail(tmp_path):
    config = AppConfig(
        sources=SourcesConfig(directories=[], tombstones=[tmp_path / "missing-tombstones.yaml"])
    )
    settings = Settings(config=config, secrets=Secrets(neo4j_user="neo4j", neo4j_password="test"))
    with pytest.raises(HTTPException) as exc_info:
        _run_all_configured_sources(settings, driver=None)
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail.startswith("tombstone configuration is invalid: [")
