"""v0.5.0 I5 finding F2: the import report's models, sanitizer and frozen schema (unit level)."""

import ast
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ingestion.import_report import (
    DOCUMENT_POINTER_CODES,
    ConfiguredRun,
    ReportEmittedCounts,
    ReportRun,
    build_import_report,
    sanitize_locator,
    sanitize_pointer,
)
from app.ingestion.import_report_schema import (
    IMPORT_REPORT_SCHEMA_PATH,
    SERVICE_IMPORT_REPORT_SCHEMA_PATH,
    render_import_report_schema,
    render_service_import_report_schema,
)
from app.sources.import_stats import (
    ClaimEffectSet,
    ImportRunStats,
    SourceClaimEffects,
    SourceImportStats,
    SourceRunResult,
    TombstoneDecision,
)
from app.sources.inventory import InventoryStatus
from app.sources.model import DiagnosticCode, IngestionDiagnostic, IngestionResult

SID_A = "urn:aip:source:filesystem:" + "a" * 64
SID_B = "urn:aip:source:filesystem:" + "b" * 64
APP_DIR = Path(__file__).resolve().parents[2] / "app"


def test_committed_import_report_schemas_match_the_generated_schemas():
    for path, render in (
        (IMPORT_REPORT_SCHEMA_PATH, render_import_report_schema),
        (SERVICE_IMPORT_REPORT_SCHEMA_PATH, render_service_import_report_schema),
    ):
        assert path.read_text() == render(), (
            f"{path.name} is out of date - regenerate it with "
            "`uv run python -m app.ingestion.import_report_schema` after a deliberate, recorded "
            "contract change."
        )


def test_locators_under_the_configured_root_become_relative(tmp_path):
    root = tmp_path / "decl"
    root.mkdir()
    assert sanitize_locator(str(root / "svc" / "openapi.yaml"), root=root) == "svc/openapi.yaml"
    assert sanitize_locator("decl/svc/openapi.yaml", root=Path("decl")) == "svc/openapi.yaml"
    assert sanitize_locator(str(root), root=root) == "."


def test_locators_outside_the_root_are_never_absolute(tmp_path):
    root = tmp_path / "decl"
    root.mkdir()
    assert sanitize_locator("/etc/passwd", root=root) is None
    assert sanitize_locator("k8s/envelope.yaml", root=root) == "k8s/envelope.yaml"
    assert sanitize_locator(None, root=root) is None


def test_pointers_keep_json_pointers_and_ids_but_drop_host_paths(tmp_path):
    root = tmp_path / "decl"
    root.mkdir()
    (root / "svc").mkdir()
    doc = DiagnosticCode.SERVICE_IDENTITY_UNRESOLVED  # a JSON-Pointer code
    file = DiagnosticCode.TOMBSTONE_FILE_UNAVAILABLE  # a file-locator code
    # A locator under the configured root is made relative to it, whatever the code.
    assert sanitize_pointer(str(root / "svc"), code=file, root=root) == "svc"
    assert sanitize_pointer(str(root / "svc"), code=doc, root=root) == "svc"
    # RFC 6901 pointers pass through for a JSON-Pointer code, and ids pass through for any code.
    assert sanitize_pointer("/calls/0", code=doc, root=root) == "/calls/0"
    assert sanitize_pointer("", code=doc, root=root) == ""
    assert sanitize_pointer("schema:owned:" + "c" * 64, code=file, root=root) == (
        "schema:owned:" + "c" * 64
    )
    # An absolute path outside the root is dropped for a file-locator code.
    assert sanitize_pointer(str(tmp_path), code=file, root=root) is None
    assert sanitize_pointer(None, code=file, root=root) is None


def test_pointer_decision_is_syntactic_not_existence_dependent(tmp_path):
    root = tmp_path / "decl"
    root.mkdir()
    missing = "/tmp/secret-that-does-not-exist.yaml"
    assert not Path(missing).exists()
    for code in DiagnosticCode:
        if code in DOCUMENT_POINTER_CODES:
            continue
        # A nonexistent absolute path is dropped exactly like an existing one.
        assert sanitize_pointer(missing, code=code, root=root) is None, code
        assert sanitize_pointer(str(tmp_path), code=code, root=root) is None, code
    for code in DiagnosticCode:
        # Windows, UNC, backslash, URL and parent-segment forms are dropped for every code.
        for value in (
            "C:\\secret\\bindings.yaml",
            "c:/secret/bindings.yaml",
            "\\\\server\\share\\x.yaml",
            "svc\\openapi.yaml",
            "file:///tmp/x.yaml",
            "../outside/openapi.yaml",
        ):
            assert sanitize_pointer(value, code=code, root=root) is None, (code, value)


def _pointer_sites() -> dict[str, list[tuple[str, str]]]:
    """Every `code=DiagnosticCode.X, source_pointer=<expr>` construction under `app/`."""
    sites: dict[str, list[tuple[str, str]]] = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            keywords = {k.arg: k.value for k in node.keywords}
            code = keywords.get("code")
            if (
                isinstance(code, ast.Attribute)
                and isinstance(code.value, ast.Name)
                and code.value.id == "DiagnosticCode"
                and "source_pointer" in keywords
            ):
                where = f"{path.relative_to(APP_DIR.parent)}:{node.lineno}"
                sites.setdefault(code.attr, []).append(
                    (ast.unparse(keywords["source_pointer"]), where)
                )
    return sites


def test_document_pointer_codes_never_carry_a_file_locator():
    """The guard behind `DOCUMENT_POINTER_CODES`: every site emitting one of those codes builds its
    pointer from a document pointer or an id, never from a locator, path or root."""
    sites = _pointer_sites()
    host_path_shaped = re.compile(r"locator|root|path|candidate|file|str\(")
    for code in DOCUMENT_POINTER_CODES:
        assert sites.get(code.value), f"{code} has no emitting site to check"
        for expression, where in sites[code.value]:
            if expression == "None":
                continue
            assert not host_path_shaped.search(expression), (code, expression, where)


def _stats(**overrides) -> ImportRunStats:
    base = {
        "inventory_status": InventoryStatus.PARTIAL,
        "committed": False,
        "per_source": {},
        "removed_source_instance_ids": (),
        "diagnostics": (),
    }
    base.update(overrides)
    return ImportRunStats(**base)


def test_builder_sorts_results_diagnostics_and_runs_and_drops_messages(tmp_path):
    root = tmp_path / "decl"
    root.mkdir()
    stats = _stats(
        source_results=(
            SourceRunResult(SID_B, str(root / "b" / "openapi.yaml"), IngestionResult.ACCEPTED, ()),
            SourceRunResult(
                SID_A,
                str(root / "a" / "openapi.yaml"),
                IngestionResult.REJECTED_UNSUPPORTED,
                (
                    IngestionDiagnostic(
                        code=DiagnosticCode.SERVICE_IDENTITY_UNRESOLVED,
                        message=f"secret detail {root}",
                        source_pointer=str(root / "a" / "openapi.yaml"),
                    ),
                ),
            ),
        ),
        tombstone_decisions=(TombstoneDecision(SID_A, "1", False, "STALE_PRIOR_REVISION"),),
    )
    report = build_import_report(
        "import-1",
        [
            ConfiguredRun(kind="kubernetes", configured_source_id="z", root=root, stats=_stats()),
            ConfiguredRun(kind="filesystem", configured_source_id="a", root=root, stats=stats),
        ],
    )

    assert [(run.kind, run.configured_source_id) for run in report.runs] == [
        ("filesystem", "a"),
        ("kubernetes", "z"),
    ]
    run = report.runs[0]
    assert [r.source_instance_id for r in run.source_results] == [SID_A, SID_B]
    assert run.source_results[0].locator == "a/openapi.yaml"
    assert run.source_results[0].diagnostics[0].source_pointer == "a/openapi.yaml"
    assert run.tombstones[0].reason.value == "STALE_PRIOR_REVISION"
    dumped = report.model_dump_json()
    assert "secret detail" not in dumped and str(root) not in dumped


def _source_result(sid: str, *, effects: dict | None) -> dict:
    return {
        "source_instance_id": sid,
        "source_kind": "filesystem",
        "locator": "svc/openapi.yaml",
        "result": "ACCEPTED",
        "adapter_identity": "openapi-adapter@1",
        "mapping_rule_version": "v1",
        "dialect_version": "3.1.0",
        "semantic_input_digest": "d" * 64,
        "service_ids": ["service:a"],
        "emitted": dict.fromkeys(ReportEmittedCounts.model_fields, 0),
        "effects": effects,
        "diagnostics": [],
    }


EMPTY_SET = {"node_ids": [], "relation_keys": [], "internal_count": 0}
EFFECTS = {
    "graph_revision_advanced": True,
    "added": {"node_ids": ["service:a"], "relation_keys": [], "internal_count": 1},
    "changed": EMPTY_SET,
    "expired": EMPTY_SET,
    "ownership_removed": EMPTY_SET,
}
REMOVAL_EFFECTS = {
    **EFFECTS,
    "added": EMPTY_SET,
    "expired": {"node_ids": ["service:a"], "relation_keys": ["CALLS:a:b"], "internal_count": 2},
}


def _removal(sid: str) -> dict:
    return {"source_instance_id": sid, "effects": REMOVAL_EFFECTS}


def test_run_model_enforces_unique_sorted_lists_and_identity_formats():
    common = {
        "kind": "filesystem",
        "configured_source_id": "x",
        "discovery_scope_id": None,
        "scope_definition_digest": None,
        "inventory_status": "COMPLETE",
        "committed": True,
        "inventory_revision": None,
        "source_results": [],
        "tombstones": [],
        "diagnostics": [],
    }
    ReportRun(**common, removals=[_removal(SID_A), _removal(SID_B)])
    with pytest.raises(ValidationError):
        ReportRun(**common, removals=[_removal(SID_A), _removal(SID_A)])
    with pytest.raises(ValidationError):
        ReportRun(**common, removals=[_removal(SID_B), _removal(SID_A)])
    with pytest.raises(ValidationError):
        ReportRun(**common, removals=[_removal("not-a-source-id")])
    with pytest.raises(ValidationError):
        ReportRun(**{**common, "inventory_revision": "rev-1"}, removals=[])
    with pytest.raises(ValidationError):
        ReportRun(
            **{**common, "source_results": [_source_result(SID_B, effects=EFFECTS)] * 2},
            removals=[],
        )
    with pytest.raises(ValidationError):  # a removal adds nothing
        ReportRun(**common, removals=[{"source_instance_id": SID_A, "effects": EFFECTS}])
    with pytest.raises(ValidationError):  # effect identities are unique and sorted
        ReportRun(
            **common,
            removals=[
                {
                    "source_instance_id": SID_A,
                    "effects": {
                        **REMOVAL_EFFECTS,
                        "expired": {**EMPTY_SET, "node_ids": ["service:b", "service:a"]},
                    },
                }
            ],
        )
    with pytest.raises(ValidationError):  # service ids are unique and sorted
        ReportRun(
            **{
                **common,
                "source_results": [
                    {**_source_result(SID_A, effects=EFFECTS), "service_ids": ["b", "a"]}
                ],
            },
            removals=[],
        )


def test_run_model_ties_effects_and_removals_to_the_commit():
    committed = {
        "kind": "filesystem",
        "configured_source_id": "x",
        "discovery_scope_id": None,
        "scope_definition_digest": None,
        "inventory_status": "COMPLETE",
        "committed": True,
        "inventory_revision": None,
        "tombstones": [],
        "diagnostics": [],
    }
    not_committed = {**committed, "inventory_status": "PARTIAL", "committed": False}
    ReportRun(**committed, source_results=[_source_result(SID_A, effects=EFFECTS)], removals=[])
    ReportRun(**not_committed, source_results=[_source_result(SID_A, effects=None)], removals=[])
    with pytest.raises(ValidationError):  # a committed source always has effects
        ReportRun(**committed, source_results=[_source_result(SID_A, effects=None)], removals=[])
    with pytest.raises(ValidationError):  # a run that did not commit changed nothing (I1 §6)
        ReportRun(
            **not_committed, source_results=[_source_result(SID_A, effects=EFFECTS)], removals=[]
        )
    with pytest.raises(ValidationError):
        ReportRun(**not_committed, source_results=[], removals=[_removal(SID_A)])


def test_malformed_operator_source_ids_and_dialects_never_fail_the_report(tmp_path):
    """A rejected tombstone's diagnostic carries its operator-supplied target, which need not be a
    source id; the report must still build (after a commit, failing here would be a 500)."""
    root = tmp_path / "decl"
    root.mkdir()
    stats = _stats(
        inventory_status=InventoryStatus.COMPLETE,
        committed=True,
        source_results=(
            SourceRunResult(
                SID_A,
                str(root / "a" / "openapi.yaml"),
                IngestionResult.ACCEPTED,
                (),
                source_kind="filesystem",
                dialect_version="/tmp/not a dialect",
            ),
        ),
        per_source={
            SID_A: SourceImportStats(
                SID_A,
                "a/openapi.yaml",
                IngestionResult.ACCEPTED,
                1,
                0,
                0,
                0,
                True,
                effects=SourceClaimEffects(added=ClaimEffectSet(public_node_ids=("service:a",))),
            )
        },
        diagnostics=(
            IngestionDiagnostic(
                code=DiagnosticCode.TOMBSTONE_SCOPE_MISMATCH,
                message="unknown target",
                source_instance_id="../../not-a-source-id",
            ),
        ),
        tombstone_decisions=(TombstoneDecision("../../not-a-source-id", "1", False, None),),
    )
    report = build_import_report(
        "import-1",
        [ConfiguredRun(kind="filesystem", configured_source_id="a", root=root, stats=stats)],
    )
    [run] = report.runs
    assert run.diagnostics[0].source_instance_id is None
    assert run.tombstones[0].target_source_instance_id == "../../not-a-source-id"
    assert run.source_results[0].dialect_version is None
    assert run.source_results[0].effects.added.node_ids == ["service:a"]
