"""CLI entry point for the real-world validation comparator and capture tool (I1 §32-33/§31).

    uv run python -m real_world_validation compare --expected <path> --actual <path>
    uv run python -m real_world_validation capture --neo4j-uri ... --out <path>

Fully generic: no `--system` flag or system-specific branch in this module (parent spec §24 forbids
production `if system == "..."` hacks). System-specific dossier paths/scope are a caller/shell
concern, passed in as plain arguments.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import neo4j
import pydantic
import yaml

from app.architecture_intelligence.bootstrap import (
    build_production_service,
    production_service_kwargs,
)
from app.graph.repository import build_driver, open_session
from app.settings import load_config
from app.sources.service_workload_mapping import load_service_workload_mapping
from real_world_validation.capture import (
    capture_actual_facts,
    capture_deployment_facts,
    write_actual_facts,
)
from real_world_validation.comparator import compare
from real_world_validation.loader import load_actual, load_actual_deployments, load_expected
from real_world_validation.model import (
    KNOWN_RELATION_TYPES,
    ExpectedValidationError,
    ScopeDeclaration,
)
from real_world_validation.reporter import has_release_blocking_finding, render

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_INVALID = 2


def _compare(expected_path: Path, actual_path: Path) -> int:
    try:
        expected = load_expected(expected_path)
        actual = load_actual(actual_path)
        actual_deployments = load_actual_deployments(actual_path)
        findings = compare(expected, actual, actual_deployments)
    except (ExpectedValidationError, ValueError) as exc:
        print(f"invalid validation configuration: {exc}", file=sys.stderr)
        return EXIT_INVALID

    print(render(findings))
    return EXIT_FAILURES if has_release_blocking_finding(findings) else EXIT_OK


def _comma_list(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _capture(args: argparse.Namespace) -> int:
    entities = _comma_list(args.scope_entities)
    relation_types = _comma_list(args.scope_relation_types) if args.scope_relation_types else None
    if relation_types is not None:
        unknown = set(relation_types) - KNOWN_RELATION_TYPES
        if unknown:
            print(
                f"invalid validation configuration: unknown --scope-relation-types: "
                f"{', '.join(sorted(unknown))}",
                file=sys.stderr,
            )
            return EXIT_INVALID
    scope = ScopeDeclaration(entities=entities, relation_types=relation_types)

    password = args.neo4j_password or os.environ.get("NEO4J_PASSWORD")
    if not password:
        print(
            "invalid validation configuration: --neo4j-password or $NEO4J_PASSWORD is required",
            file=sys.stderr,
        )
        return EXIT_INVALID

    if args.aip_config is not None and args.until is None:
        print(
            "invalid validation configuration: --aip-config (deployment capture) requires --until, "
            "since a public DEPLOYED_AS answer needs a complete observation window",
            file=sys.stderr,
        )
        return EXIT_INVALID

    # --aip-config is validated before any connection is opened. A config or mapping-artifact problem
    # is invalid configuration (exit 2), never a traceback. Only the specific failures
    # `load_config` can raise are caught. The mapping artifact is loaded through its own diagnosing
    # loader, so `build_production_service` below never reaches its raise-on-diagnostics path.
    service_kwargs = None
    if args.aip_config is not None:
        try:
            config = load_config(args.aip_config)
        except (OSError, yaml.YAMLError, pydantic.ValidationError) as exc:
            print(f"invalid validation configuration: --aip-config: {exc}", file=sys.stderr)
            return EXIT_INVALID
        _document, diagnostics = load_service_workload_mapping(
            config.sources.service_workload_mapping
        )
        if diagnostics:
            detail = "; ".join(f"{d.code.value}: {d.message}" for d in diagnostics)
            print(
                f"invalid validation configuration: service-workload mapping artifact: {detail}",
                file=sys.stderr,
            )
            return EXIT_INVALID
        service_kwargs = production_service_kwargs(config)
        service_kwargs["database"] = args.database

    driver = build_driver(args.neo4j_uri, args.neo4j_user, password)
    deployments = None
    try:
        with open_session(driver, database=args.database, read_only=True) as session:
            facts = capture_actual_facts(
                session,
                scope=scope,
                environment=args.environment,
                since=args.since,
                until=args.until,
            )
        if service_kwargs is not None:
            # v0.5.0 I5 §7: DEPLOYED_AS only through the public projection, from a service built
            # exactly as the app builds it. --database overrides the config's graph database,
            # matching the relation capture above.
            service = build_production_service(driver, **service_kwargs)
            deployments = capture_deployment_facts(
                service,
                scope=scope,
                environment=args.environment,
                since=args.since,
                until=args.until,
            )
    except (neo4j.exceptions.Neo4jError, neo4j.exceptions.DriverError) as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return EXIT_INVALID
    finally:
        driver.close()

    write_actual_facts(args.out, facts, deployments)
    deployment_note = "" if deployments is None else f" and {len(deployments)} deployments"
    print(f"captured {len(facts)} facts{deployment_note} to {args.out}")
    return EXIT_OK


def _iso_datetime(value: str) -> datetime:
    """A naive timestamp would silently mean "no timezone" to Neo4j's driver, which is exactly
    the wrong ambiguity for an environment/window-qualified evidence query - require an explicit
    offset (a trailing Z or +HH:MM), matching every other timestamp this project accepts."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(f"timestamp must be timezone-aware: {value!r}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m real_world_validation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare_parser = subparsers.add_parser("compare", help="compare expected vs. actual facts")
    compare_parser.add_argument(
        "--expected", required=True, type=Path, help="path to expected.yaml"
    )
    compare_parser.add_argument(
        "--actual", required=True, type=Path, help="path to an actual-facts capture"
    )

    capture_parser = subparsers.add_parser(
        "capture", help="capture AIP's actual canonical facts from a live Neo4j graph"
    )
    capture_parser.add_argument("--neo4j-uri", required=True)
    capture_parser.add_argument("--neo4j-user", required=True)
    capture_parser.add_argument(
        "--neo4j-password",
        default=None,
        help="falls back to $NEO4J_PASSWORD - prefer the env var over the command line where practical",
    )
    capture_parser.add_argument("--database", default="neo4j")
    capture_parser.add_argument("--environment", required=True)
    capture_parser.add_argument("--since", required=True, type=_iso_datetime)
    capture_parser.add_argument("--until", default=None, type=_iso_datetime)
    capture_parser.add_argument(
        "--scope-entities", required=True, help="comma-separated canonical entity ids"
    )
    capture_parser.add_argument(
        "--scope-relation-types",
        default=None,
        help="comma-separated relation types, or omit for any",
    )
    capture_parser.add_argument("--out", required=True, type=Path)
    capture_parser.add_argument(
        "--aip-config",
        default=None,
        type=Path,
        help="AIP config file; when given, also captures public DEPLOYED_AS outcomes for the "
        "scoped services (requires --until)",
    )

    args = parser.parse_args(argv)
    if args.command == "capture":
        return _capture(args)
    return _compare(args.expected, args.actual)


if __name__ == "__main__":
    sys.exit(main())
