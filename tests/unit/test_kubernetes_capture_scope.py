"""The capture a Kubernetes envelope describes, carried from discoverer to importer (v0.6.0 I2.2d,
decision record D5). Only a fully accepted envelope carries one; it never appears in a dump."""

import pytest

from app.ingestion.kubernetes_discoverer import KubernetesSourceDiscoverer
from app.sources.model import KubernetesCaptureScope, SourceDescriptor, SourceKind
from tests.unit.test_ingestion_kubernetes_discoverer import (
    _config,
    _resource_yaml,
    _write_bundle,
)


def _scope(**overrides) -> KubernetesCaptureScope:
    fields = {
        "namespaces": ("a", "b"),
        "cluster_uid": "cluster-1",
        "revision": "rev-1",
        "evidence_mode": "CAPTURED_RESOURCE",
        "captured_at": "2026-09-15T10:00:00Z",
    }
    fields.update(overrides)
    return KubernetesCaptureScope(**fields)


def _descriptor(**overrides) -> SourceDescriptor:
    fields = {
        "source_instance_id": "urn:aip:source:kubernetes:x",
        "source_kind": SourceKind.KUBERNETES,
        "locator": "l",
        "discovery_scope_id": "s",
        "scope_definition_digest": "d",
        "content_sha256": "c",
        "semantic_input_digest": "x",
        "mapping_context_digest": "m",
        "adapter_identity": "a",
        "mapping_rule_id": "r",
        "mapping_rule_version": "1",
    }
    fields.update(overrides)
    return SourceDescriptor(**fields)


def test_a_descriptor_has_no_capture_by_default():
    assert _descriptor().capture_scope is None


def test_the_capture_is_never_part_of_a_dump_so_discovery_output_keeps_its_shape():
    descriptor = _descriptor(capture_scope=_scope())

    assert "capture_scope" not in descriptor.model_dump()
    assert "capture_scope" not in descriptor.model_dump(mode="json")
    assert "capture_scope" not in descriptor.model_dump_json()
    assert descriptor.model_dump() == _descriptor().model_dump()


def test_the_orchestrators_enrichment_copy_keeps_the_capture():
    enriched = _descriptor(capture_scope=_scope()).model_copy(
        update={"adapter_identity": "kubernetes", "semantic_input_digest": "abc"}
    )

    assert enriched.capture_scope == _scope()
    assert enriched.adapter_identity == "kubernetes"


def test_a_capture_is_immutable():
    with pytest.raises(ValueError):
        _scope().cluster_uid = "other"  # pyright: ignore[reportAttributeAccessIssue]


def test_an_accepted_envelope_carries_exactly_what_it_declares(tmp_path):
    _write_bundle(tmp_path, files={"resources.yaml": _resource_yaml("example", uid="ns-uid")})

    [loaded] = KubernetesSourceDiscoverer(_config(tmp_path)).discover().loaded_sources

    assert loaded.descriptor.capture_scope == KubernetesCaptureScope(
        namespaces=("example",),
        cluster_uid="independently-established-cluster-identity",
        revision="snapshot-revision",
        evidence_mode="CAPTURED_RESOURCE",
        captured_at="2026-09-15T10:00:00Z",
    )


def _scope_with_namespaces(namespaces: list[str]) -> dict:
    from tests.unit.test_ingestion_kubernetes_discoverer import _valid_envelope_dict

    return {**_valid_envelope_dict()["scope"], "namespaces": namespaces}


def test_a_multi_namespace_scope_is_carried_in_its_declared_sorted_order(tmp_path):
    _write_bundle(
        tmp_path, envelope_overrides={"scope": _scope_with_namespaces(["alpha", "mid", "zeta"])}
    )

    [loaded] = KubernetesSourceDiscoverer(_config(tmp_path)).discover().loaded_sources

    assert loaded.descriptor.capture_scope is not None
    assert loaded.descriptor.capture_scope.namespaces == ("alpha", "mid", "zeta")


def test_an_unsorted_namespace_list_is_rejected_and_carries_no_capture(tmp_path):
    _write_bundle(tmp_path, envelope_overrides={"scope": _scope_with_namespaces(["zeta", "alpha"])})

    [loaded] = KubernetesSourceDiscoverer(_config(tmp_path)).discover().loaded_sources

    assert loaded.diagnostics
    assert loaded.descriptor.capture_scope is None


@pytest.mark.parametrize(
    "case",
    ["missing envelope", "invalid shape", "not complete", "no capturedAt", "wrong cluster"],
)
def test_a_rejected_envelope_carries_no_capture(tmp_path, case):
    if case == "invalid shape":
        _write_bundle(tmp_path, envelope_overrides={"kind": "NotASnapshot"})
    elif case == "not complete":
        from tests.unit.test_ingestion_kubernetes_discoverer import _valid_envelope_dict

        completeness = {**_valid_envelope_dict()["completeness"], "status": "PARTIAL"}
        _write_bundle(tmp_path, envelope_overrides={"completeness": completeness})
    elif case == "no capturedAt":
        from tests.unit.test_ingestion_kubernetes_discoverer import _valid_envelope_dict

        metadata = {
            k: v for k, v in _valid_envelope_dict()["metadata"].items() if k != "capturedAt"
        }
        _write_bundle(tmp_path, envelope_overrides={"metadata": metadata})
    elif case == "wrong cluster":
        _write_bundle(tmp_path)
        config = _config(tmp_path, cluster_uid="a-different-cluster")
        [loaded] = KubernetesSourceDiscoverer(config).discover().loaded_sources
        assert loaded.descriptor.capture_scope is None
        return
    outcome = KubernetesSourceDiscoverer(_config(tmp_path)).discover()

    [loaded] = outcome.loaded_sources
    assert loaded.diagnostics, "the case must actually be a rejection"
    assert loaded.descriptor.capture_scope is None
