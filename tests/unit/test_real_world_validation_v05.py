"""v0.5.0 I5 Slice 1: the v0.5 additions to the real-world validation tooling (I5 §3, §7).

The additions are deterministic label-pair capture, `PUBLISHES_TO` status, `DEPLOYED_AS`
expectations, forbidden facts, and the capture CLI's `--aip-config`. The v0.3 behaviour is covered,
unchanged, by the other `test_real_world_validation_*` modules.
"""

import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from app.architecture_intelligence.bootstrap import production_service_kwargs
from app.graph_schema.registry import RELATIONS
from app.settings import AppConfig
from real_world_validation import capture
from real_world_validation.__main__ import EXIT_INVALID, EXIT_OK, main
from real_world_validation.comparator import compare
from real_world_validation.loader import load_actual_deployments, load_expected
from real_world_validation.model import (
    DeploymentFact,
    ExpectedDeployment,
    ExpectedDocument,
    ExpectedValidationError,
    ForbiddenDeployment,
    ForbiddenRelation,
    RelationFact,
    ScopeDeclaration,
    WorkloadKey,
)
from real_world_validation.reporter import render

REPO = Path(__file__).resolve().parents[2]
WORKLOAD = WorkloadKey(namespace="heroes", kind="DEPLOYMENT", name="rest-fights")


# --- §3 gap 1: deterministic, complete label-pair capture ----------------------------------------


def test_capture_query_covers_every_admitted_label_pair():
    query = capture._CLASSIFIED_QUERY + capture._EVIDENCE_QUERY
    for relation_type, definition in RELATIONS.items():
        for source_label in definition.source_labels:
            for target_label in definition.target_labels:
                assert (
                    f"MATCH (a:{source_label})-[r:{relation_type}]->(t:{target_label})" in query
                ), (relation_type, source_label, target_label)


def test_capture_query_is_identical_under_different_hash_seeds():
    """The old `next(iter(frozenset))` label choice changed with PYTHONHASHSEED."""
    program = (
        "import hashlib; from real_world_validation import capture; "
        "print(hashlib.sha256((capture._CLASSIFIED_QUERY + capture._EVIDENCE_QUERY)"
        ".encode()).hexdigest())"
    )
    digests = {
        subprocess.run(
            [sys.executable, "-c", program],
            env={"PYTHONHASHSEED": seed, "PATH": ""},
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("0", "1", "2", "3", "42")
    }
    assert len(digests) == 1


def test_publishes_to_has_runtime_status():
    assert "PUBLISHES_TO" in capture._RUNTIME_STATUS_RELATION_TYPES
    assert "PUBLISHES_TO" not in capture._EVIDENCE_ONLY_RELATION_TYPES


# --- §7: expected.yaml vocabulary ------------------------------------------------------------------


def _write(tmp_path: Path, document: dict, name: str = "expected.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    return path


def _expected(**extra) -> dict:
    document = {
        "system": "quarkus-super-heroes",
        "upstream_revision": "8ea0337",
        "scope": {"entities": ["service:rest-fights"]},
    }
    document.update(extra)
    return document


_WORKLOAD_YAML = {"namespace": "heroes", "kind": "DEPLOYMENT", "name": "rest-fights"}


def test_loader_parses_deployments_and_forbidden_facts(tmp_path):
    path = _write(
        tmp_path,
        _expected(
            expected={
                "deployments": [
                    {
                        "id": "d1",
                        "service": "service:rest-fights",
                        "workload": _WORKLOAD_YAML,
                        "status": "RESOLVED_CONFIGURED",
                        "supporting_methods": ["RESOLVED_CONFIGURED"],
                    }
                ]
            },
            forbidden={
                "relations": [
                    {
                        "id": "f1",
                        "type": "SENDS",
                        "source": "service:rest-fights",
                        "target": "queue:fights",
                    }
                ],
                "deployments": [
                    {"id": "f2", "service": "service:rest-fights", "workload": _WORKLOAD_YAML}
                ],
            },
        ),
    )

    document = load_expected(path)

    [deployment] = document.expected_deployments
    assert deployment.fact == DeploymentFact(
        service="service:rest-fights",
        workload=WORKLOAD,
        status="RESOLVED_CONFIGURED",
        supporting_methods=("RESOLVED_CONFIGURED",),
    )
    assert document.forbidden_relations == (
        ForbiddenRelation(
            id="f1", type="SENDS", source="service:rest-fights", target="queue:fights"
        ),
    )
    assert document.forbidden_deployments == (
        ForbiddenDeployment(id="f2", service="service:rest-fights", workload=WORKLOAD),
    )


@pytest.mark.parametrize(
    ("extra", "reason"),
    [
        (
            {"expected": {"deployments": [{"id": "d", "status": "RESOLVED"}]}},
            "unknown deployment status",
        ),
        (
            {
                "expected": {
                    "deployments": [
                        {
                            "id": "d",
                            "status": "RESOLVED_EXPLICIT",
                            "supporting_methods": ["RESOLVED_CONFIGURED", "RESOLVED_EXPLICIT"],
                        }
                    ]
                }
            },
            "canonical strength order",
        ),
        (
            {
                "expected": {
                    "deployments": [
                        {
                            "id": "d",
                            "status": "UNRESOLVED",
                            "workload": {**_WORKLOAD_YAML, "kind": "POD"},
                        }
                    ]
                }
            },
            "unknown workload kind",
        ),
        (
            {
                "expected": {
                    "deployments": [{"id": "d", "service": "service:other", "status": "UNRESOLVED"}]
                }
            },
            "unscoped Service",
        ),
        (
            {
                "forbidden": {
                    "relations": [
                        {
                            "id": "f",
                            "type": "SENDS",
                            "source": "service:other",
                            "target": "queue:q",
                        }
                    ]
                }
            },
            "outside the scope",
        ),
        ({"forbidden": {"relations": [], "extra": []}}, "unknown field"),
        (
            {
                "expected": {"deployments": [{"id": "dup", "status": "UNRESOLVED"}]},
                "forbidden": {
                    "deployments": [
                        {"id": "dup", "service": "service:rest-fights", "workload": _WORKLOAD_YAML}
                    ]
                },
            },
            "duplicate finding id",
        ),
    ],
)
def test_loader_rejects_invalid_v05_sections(tmp_path, extra, reason):
    with pytest.raises(ExpectedValidationError, match=reason):
        load_expected(_write(tmp_path, _expected(**extra)))


@pytest.mark.parametrize("system", ["quarkus-super-heroes", "apache-airflow"])
def test_committed_v03_expected_files_still_load_unchanged(system):
    document = load_expected(REPO / "docs" / "real-world-validation" / system / "expected.yaml")
    assert document.expected_relations
    assert document.expected_deployments == ()
    assert document.forbidden_relations == () and document.forbidden_deployments == ()


def test_actual_deployments_distinguish_absent_from_empty(tmp_path):
    assert load_actual_deployments(_write(tmp_path, {"relations": []}, "a.yaml")) is None
    assert (
        load_actual_deployments(_write(tmp_path, {"relations": [], "deployments": []}, "b.yaml"))
        == []
    )


# --- §7: comparator ---------------------------------------------------------------------------------


def _document(**overrides) -> ExpectedDocument:
    defaults = {
        "system": "s",
        "upstream_revision": "r",
        "scope": ScopeDeclaration(entities=("service:rest-fights",)),
        "expected_relations": (),
    }
    defaults.update(overrides)
    return ExpectedDocument(**defaults)


def _deployment(status="RESOLVED_CONFIGURED", methods=("RESOLVED_CONFIGURED",), workload=WORKLOAD):
    return DeploymentFact(
        service="service:rest-fights",
        workload=workload,
        status=status,
        supporting_methods=methods,
    )


def _classes(findings):
    return {f.id: f.classification for f in findings}


def test_deployment_correct_missing_and_mismatched():
    expected = _document(expected_deployments=(ExpectedDeployment(id="d1", fact=_deployment()),))
    assert _classes(compare(expected, [], [_deployment()])) == {"d1": "CORRECT"}
    assert _classes(compare(expected, [], [])) == {"d1": "MISSING_SUPPORTED"}
    assert _classes(compare(expected, [], [_deployment(status="RESOLVED_EXPLICIT")])) == {
        "d1": "INCORRECT_SUPPORTED"
    }


def test_supporting_methods_are_compared_only_when_asserted():
    loose = _document(
        expected_deployments=(ExpectedDeployment(id="d1", fact=_deployment(methods=None)),)
    )
    strict = _document(expected_deployments=(ExpectedDeployment(id="d1", fact=_deployment()),))
    actual = [_deployment(methods=("RESOLVED_CONFIGURED", "RESOLVED_OBSERVED"))]
    assert _classes(compare(loose, [], actual)) == {"d1": "CORRECT"}
    assert _classes(compare(strict, [], actual)) == {"d1": "INCORRECT_SUPPORTED"}


def test_unexpected_captured_deployment_is_incorrect_supported():
    findings = compare(_document(), [], [_deployment()])
    [finding] = findings
    assert finding.classification == "INCORRECT_SUPPORTED"
    assert (
        finding.id == "unexpected:DEPLOYED_AS:service:rest-fights:heroes/DEPLOYMENT/rest-fights:-"
    )


def test_forbidden_relation_present_or_absent():
    fact = RelationFact(type="SENDS", source="service:rest-fights", target="queue:fights")
    document = _document(
        forbidden_relations=(
            ForbiddenRelation(id="f1", type="SENDS", source=fact.source, target=fact.target),
        )
    )
    absent = compare(document, [], [])
    present = compare(document, [fact], [])

    assert _classes(absent) == {"f1": "CORRECT"}
    # reported once, under the forbidden id, not again as `unexpected:`
    assert _classes(present) == {"f1": "INCORRECT_SUPPORTED"}
    assert present[0].severity == "CRITICAL"


@pytest.mark.parametrize(
    ("status", "violated"),
    [
        ("RESOLVED_EXPLICIT", True),
        ("RESOLVED_CONFIGURED", True),
        ("RESOLVED_OBSERVED", True),
        ("UNRESOLVED", False),
        ("CONFLICT", False),
    ],
)
def test_forbidden_deployment_is_violated_only_by_a_resolved_outcome(status, violated):
    document = _document(
        forbidden_deployments=(
            ForbiddenDeployment(id="f1", service="service:rest-fights", workload=WORKLOAD),
        )
    )
    findings = compare(document, [], [_deployment(status=status, methods=())])
    assert _classes(findings) == {"f1": "INCORRECT_SUPPORTED" if violated else "CORRECT"}


def test_deployment_expectations_need_a_deployment_capture():
    document = _document(expected_deployments=(ExpectedDeployment(id="d1", fact=_deployment()),))
    with pytest.raises(ValueError, match="no deployments section"):
        compare(document, [], None)


def test_report_counts_forbidden_facts_separately():
    fact = RelationFact(type="SENDS", source="service:rest-fights", target="queue:fights")
    document = _document(
        expected_deployments=(ExpectedDeployment(id="d1", fact=_deployment()),),
        forbidden_relations=(
            ForbiddenRelation(id="f1", type="SENDS", source=fact.source, target=fact.target),
        ),
    )
    report = render(compare(document, [], [_deployment()]))

    assert "Expected supported facts:      1" in report
    assert "Correct:                       1" in report
    assert "Forbidden facts proven absent: 1" in report
    assert "Forbidden facts present:       0" in report
    assert "DEPLOYED_AS service:rest-fights -> heroes/DEPLOYMENT/rest-fights" in report
    assert "Forbidden: SENDS service:rest-fights -> queue:fights" in report


# --- the capture CLI's --aip-config -------------------------------------------------------------------


@contextmanager
def _fake_session(*_args, **_kwargs):
    yield MagicMock()


_CAPTURE_ARGS = [
    "capture",
    "--neo4j-uri",
    "bolt://localhost:7687",
    "--neo4j-user",
    "neo4j",
    "--neo4j-password",
    "secret",
    "--environment",
    "quarkus-i5",
    "--since",
    "2026-09-24T00:00:00+00:00",
    "--scope-entities",
    "service:rest-fights",
]


def test_aip_config_requires_a_complete_window(tmp_path):
    code = main([*_CAPTURE_ARGS, "--out", str(tmp_path / "a.yaml"), "--aip-config", "config.yaml"])
    assert code == EXIT_INVALID


def test_aip_config_captures_deployments_with_the_app_service_factory(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {"architecture_intelligence": {"telemetry": {"service_aliases": {"x": "service:y"}}}}
        )
    )
    built = {}

    def _build(driver, **kwargs):
        built.update(kwargs)
        return "service"

    monkeypatch.setattr("real_world_validation.__main__.build_driver", lambda *a, **k: MagicMock())
    monkeypatch.setattr("real_world_validation.__main__.open_session", _fake_session)
    monkeypatch.setattr("real_world_validation.__main__.capture_actual_facts", lambda *a, **k: [])
    monkeypatch.setattr("real_world_validation.__main__.build_production_service", _build)
    captured = DeploymentFact(
        service="service:rest-fights",
        workload=WORKLOAD,
        status="RESOLVED_CONFIGURED",
        supporting_methods=("RESOLVED_CONFIGURED",),
        candidate_service_ids=("service:rest-fights",),
        resolution_id="aip:deployment-resolution:v1:" + "a" * 64,
    )
    monkeypatch.setattr(
        "real_world_validation.__main__.capture_deployment_facts",
        lambda service, **kwargs: [captured] if service == "service" else [],
    )
    out = tmp_path / "actual.yaml"

    code = main(
        [
            *_CAPTURE_ARGS,
            "--until",
            "2026-09-24T23:59:59+00:00",
            "--database",
            "qualification",
            "--out",
            str(out),
            "--aip-config",
            str(config_path),
        ]
    )

    assert code == EXIT_OK
    assert built["service_aliases"] == {"x": "service:y"}
    assert built["database"] == "qualification"
    assert load_actual_deployments(out) == [captured]


def test_capture_without_aip_config_writes_no_deployments_section(tmp_path, monkeypatch):
    monkeypatch.setattr("real_world_validation.__main__.build_driver", lambda *a, **k: MagicMock())
    monkeypatch.setattr("real_world_validation.__main__.open_session", _fake_session)
    monkeypatch.setattr("real_world_validation.__main__.capture_actual_facts", lambda *a, **k: [])
    out = tmp_path / "actual.yaml"

    assert main([*_CAPTURE_ARGS, "--out", str(out)]) == EXIT_OK
    assert "deployments" not in yaml.safe_load(out.read_text())


def test_production_service_kwargs_mirror_the_app_configuration():
    config = AppConfig.model_validate(
        {
            "graph": {"database": "aip"},
            "sources": {"service_workload_mapping": "mapping.yaml"},
            "telemetry": {"service_aliases": {"a": "service:b"}},
        }
    )
    assert production_service_kwargs(config) == {
        "database": "aip",
        "service_workload_mapping_path": Path("mapping.yaml"),
        "configured_kubernetes_sources": [],
        "service_aliases": {"a": "service:b"},
    }


# --- PR #237 review: several candidate groups on one (Service, Workload) key -------------------


def _unresolved(resolution_id: str, candidates=("service:rest-fights",)) -> DeploymentFact:
    return DeploymentFact(
        service=None,
        workload=None,
        status="UNRESOLVED",
        supporting_methods=(),
        candidate_service_ids=candidates,
        resolution_id=resolution_id,
    )


def test_two_null_null_groups_are_matched_one_to_one_not_collapsed():
    """I3 §13.1: two unmatched Path B mappings for the same Service are two non-resolved groups,
    both with a null Service and Workload. They must not collapse into one."""
    expected_one = DeploymentFact(service=None, workload=None, status="UNRESOLVED")
    two_expected = _document(
        expected_deployments=(
            ExpectedDeployment(id="g1", fact=expected_one),
            ExpectedDeployment(id="g2", fact=expected_one),
        )
    )
    actual = [_unresolved("r1"), _unresolved("r2")]

    assert _classes(compare(two_expected, [], actual)) == {"g1": "CORRECT", "g2": "CORRECT"}
    # one actual group can't satisfy two expected groups
    assert _classes(compare(two_expected, [], actual[:1])) == {
        "g1": "CORRECT",
        "g2": "MISSING_SUPPORTED",
    }
    # and a second actual group is never silently lost
    one_expected = _document(expected_deployments=(ExpectedDeployment(id="g1", fact=expected_one),))
    classes = _classes(compare(one_expected, [], actual))
    assert classes["g1"] == "CORRECT"
    assert [k for k, v in classes.items() if v == "INCORRECT_SUPPORTED"] == [
        "unexpected:DEPLOYED_AS:-:-:r2"
    ]


def test_candidate_context_distinguishes_groups_on_the_same_key():
    alt = ("service:rest-fights", "service:rest-fights-alt")
    document = _document(
        expected_deployments=(
            ExpectedDeployment(
                id="plain",
                fact=DeploymentFact(
                    service=None,
                    workload=None,
                    status="UNRESOLVED",
                    candidate_service_ids=("service:rest-fights",),
                ),
            ),
            ExpectedDeployment(
                id="alt",
                fact=DeploymentFact(
                    service=None, workload=None, status="UNRESOLVED", candidate_service_ids=alt
                ),
            ),
        )
    )
    # the actual order is the reverse of the expected order; matching is by asserted fields
    actual = [_unresolved("r1", alt), _unresolved("r2")]
    assert _classes(compare(document, [], actual)) == {"plain": "CORRECT", "alt": "CORRECT"}


def test_loader_accepts_duplicate_keys_and_validates_candidate_ids(tmp_path):
    group = {"status": "UNRESOLVED", "candidate_service_ids": ["service:rest-fights"]}
    document = load_expected(
        _write(
            tmp_path,
            _expected(expected={"deployments": [{"id": "g1", **group}, {"id": "g2", **group}]}),
        )
    )
    assert len(document.expected_deployments) == 2
    with pytest.raises(ExpectedValidationError, match="sorted and duplicate-free"):
        load_expected(
            _write(
                tmp_path,
                _expected(
                    expected={
                        "deployments": [
                            {
                                "id": "g",
                                "status": "UNRESOLVED",
                                "candidate_service_ids": ["service:b", "service:a"],
                            }
                        ]
                    }
                ),
                "bad.yaml",
            )
        )


@pytest.mark.parametrize(
    ("config_text", "reason"),
    [
        (None, "--aip-config"),  # missing file
        ("architecture_intelligence: [unclosed", "--aip-config"),  # YAML error
        (
            "architecture_intelligence:\n  graph: {database: [not-a-string]}\n",
            "--aip-config",
        ),  # validation error
        (
            "architecture_intelligence:\n  sources: {service_workload_mapping: missing.yaml}\n",
            "mapping artifact",
        ),  # diagnosed mapping artifact
    ],
)
def test_aip_config_failures_are_invalid_configuration_not_tracebacks(
    tmp_path, monkeypatch, capsys, config_text, reason
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    if config_text is not None:
        config_path.write_text(config_text)
    connected = []
    monkeypatch.setattr(
        "real_world_validation.__main__.build_driver", lambda *a, **k: connected.append(1)
    )

    code = main(
        [
            *_CAPTURE_ARGS,
            "--until",
            "2026-09-24T23:59:59+00:00",
            "--out",
            str(tmp_path / "a.yaml"),
            "--aip-config",
            str(config_path),
        ]
    )

    assert code == EXIT_INVALID
    assert reason in capsys.readouterr().err
    assert connected == []  # validated before any connection is opened
