"""Behaviour-preservation baseline for structural refactorings of `app/`.

Each scenario runs a real discovery (adapters, identity minting, merge, canonical validation,
inventory snapshot) over committed inputs - no Neo4j - and compares the complete result to a
committed golden JSON: merged model, per-source outcome (result, diagnostics in order,
semantic-input digest, provenance/evidence ids), descriptors and the inventory snapshot.

A refactoring that is meant to be behaviour-preserving must leave these files untouched. If a
change is deliberate, regenerate with `AIP_UPDATE_GOLDEN=1 uv run pytest
tests/unit/test_refactor_golden_baseline.py` and review the golden diff in the PR.

Scrubbed, because they vary run-to-run or clone-to-clone:
- per-capture: `capture_time`, `inventory_capture_id`;
- derived from the absolute scan root (verified by running from a relocated copy):
  `scope_definition_digest` and `inventory_revision`, which folds it in.
The checkout location is also normalized to `<repo>` in locators. Every other field, including
all element, evidence and semantic-input-digest values, is compared, so a wall-clock or path leak
into those fingerprints fails the run.
"""

import dataclasses
import json
import os
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.ingestion.orchestrator import run_filesystem_discovery, run_kubernetes_discovery
from app.sources.model import (
    FilesystemSourceConfig,
    KubernetesEvidenceMode,
    KubernetesSourceConfig,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "tests" / "snapshots" / "refactor_baseline"
_VOLATILE_KEYS = frozenset(
    {"capture_time", "inventory_capture_id", "scope_definition_digest", "inventory_revision"}
)


def _encode(value):
    if isinstance(value, BaseModel):
        return _encode(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: ("<scrubbed>" if f.name in _VOLATILE_KEYS else _encode(getattr(value, f.name)))
            for f in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): ("<scrubbed>" if key in _VOLATILE_KEYS else _encode(item))
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_encode(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _render(run) -> str:
    text = json.dumps(_encode(run), indent=2, sort_keys=True, default=str) + "\n"
    return text.replace(str(REPO_ROOT), "<repo>")


def _filesystem(scenario_id: str, root: str):
    return run_filesystem_discovery(FilesystemSourceConfig(id=scenario_id, root=REPO_ROOT / root))


def _kubernetes():
    return run_kubernetes_discovery(
        KubernetesSourceConfig(
            id="checkout-cluster",
            root=REPO_ROOT / "tests/fixtures/kubernetes/i2",
            envelope_relative_path="envelope.yaml",
            configured_scope_id="checkout-cluster-namespaces",
            cluster_uid="d3adbeef-0000-4000-8000-000000000001",
            evidence_mode=KubernetesEvidenceMode.CAPTURED_RESOURCE,
            authorized_producer="aip-kubernetes-capture-agent",
            authority_record="checkout-cluster-capture-authority",
        )
    )


SCENARIOS = {
    "examples-filesystem": lambda: _filesystem("golden-examples", "examples"),
    "pubsub-kafka": lambda: _filesystem(
        "golden-pubsub-kafka", "tests/fixtures/pubsub/kafka/declarations"
    ),
    "pubsub-google": lambda: _filesystem(
        "golden-pubsub-google", "tests/fixtures/pubsub/google-pubsub/declarations"
    ),
    "pubsub-azure": lambda: _filesystem(
        "golden-pubsub-azure", "tests/fixtures/pubsub/azure-service-bus/declarations"
    ),
    "kubernetes-i2": _kubernetes,
}


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_discovery_result_matches_committed_golden(scenario):
    rendered = _render(SCENARIOS[scenario]())
    golden_path = GOLDEN_DIR / f"{scenario}.json"
    if os.environ.get("AIP_UPDATE_GOLDEN") == "1":
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(rendered)
    assert golden_path.exists(), (
        f"missing golden {golden_path}; regenerate with AIP_UPDATE_GOLDEN=1"
    )
    assert rendered == golden_path.read_text(), (
        f"{scenario}: discovery output changed. A behaviour-preserving refactoring must not change "
        "ids, digests, diagnostics or their order. If deliberate, regenerate with "
        "AIP_UPDATE_GOLDEN=1 and review the golden diff."
    )


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_discovery_is_deterministic_within_a_process(scenario):
    assert _render(SCENARIOS[scenario]()) == _render(SCENARIOS[scenario]())


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_committed_golden_contains_no_absolute_checkout_path(scenario):
    golden_path = GOLDEN_DIR / f"{scenario}.json"
    assert golden_path.exists(), f"missing golden {golden_path}"
    assert str(REPO_ROOT) not in golden_path.read_text()
