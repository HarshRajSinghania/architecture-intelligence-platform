"""Pins the deployment reconciliation rule version that two modules each keep as a local constant.

`deployment_projection._RECONCILIATION_RULE_VERSION` stamps every `DeploymentResolution` (and so
feeds `resolution_id`/`claim_id`), while `repository._DEPLOYMENT_RECONCILIATION_RULE_VERSION` is
bound into the snapshot fingerprint (and so every `snapshot_id`). Their source comments say they
"must move together"; nothing enforced it. A drift would silently change one set of ids and not
the other. These tests make a bump - or a one-sided edit - fail loudly and deliberately.

If the rule version is bumped on purpose (a reviewed spec change), update `PINNED_RULE_VERSION`
here in the same PR.
"""

from app.architecture_intelligence import deployment_projection as projection
from app.architecture_intelligence import repository as repo
from app.architecture_intelligence.contracts import DEPLOYMENT_RECONCILIATION_RULE_ID

PINNED_RULE_ID = "service-workload-reconciliation"
PINNED_RULE_VERSION = 1


class _EmptySession:
    def run(self, _query: str, **_params):
        return []


def _state():
    return repo.canonical_snapshot_state(_EmptySession(), coverage_qualification_enabled=True)


def test_both_modules_carry_the_same_rule_version():
    assert projection._RECONCILIATION_RULE_VERSION == repo._DEPLOYMENT_RECONCILIATION_RULE_VERSION


def test_rule_version_and_id_are_pinned():
    assert repo._DEPLOYMENT_RECONCILIATION_RULE_VERSION == PINNED_RULE_VERSION
    assert projection._RECONCILIATION_RULE_VERSION == PINNED_RULE_VERSION
    assert DEPLOYMENT_RECONCILIATION_RULE_ID == PINNED_RULE_ID


def test_snapshot_state_binds_the_rule_id_and_version():
    assert _state()["deployment_reconciliation_rule"] == {
        "rule_id": PINNED_RULE_ID,
        "rule_version": PINNED_RULE_VERSION,
    }


def test_bumping_the_repository_rule_version_changes_the_snapshot_id(monkeypatch):
    before, _ = repo.snapshot_fingerprint(_state())
    monkeypatch.setattr(repo, "_DEPLOYMENT_RECONCILIATION_RULE_VERSION", PINNED_RULE_VERSION + 1)
    after, _ = repo.snapshot_fingerprint(_state())
    assert before != after
