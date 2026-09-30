"""Pure claim-planning helpers for the source-scoped import (`app.graph.importer`): the node ids and
relation keys a model claims, who owns a claim once a whole discovery run commits, and the canonical
effect sets reported per source. No Neo4j access.

Moved verbatim out of `importer.py`.
"""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet

from app.canonical.model import ArchitectureModel, relation_key
from app.common.encoding import length_delimited, sha256_hex, utf8
from app.sources.import_stats import (
    ClaimEffectSet,
)
from app.sources.model import (
    SourceInstanceId,
)


def infrastructure_claim_contribution_id(claim_id: str, source_instance_id: str) -> str:
    """Not spec-named (§7.2 describes the per-source contribution *concept* in prose, not a schema
    - the same discipline as every other id formula this PR's own layer invents). Length-delimited
    like every other identity hash in this codebase; deliberately a different literal prefix from
    `InfrastructureClaim.id`'s own `urn:aip:infra-claim:` so `_recompute_infrastructure_claim_evidence`
    can distinguish "a claim id" from "a claim-contribution id" by a plain string prefix check,
    without needing a Neo4j label lookup.
    """
    key = length_delimited(utf8(claim_id), utf8(source_instance_id))
    return f"urn:aip:infra-claim-support:{sha256_hex(key)}"


def model_node_ids(model: ArchitectureModel, *, source_instance_id: str) -> set[str]:
    return {
        *(s.id for s in model.services),
        *(o.id for o in model.operations),
        *(q.id for q in model.queues),
        *(m.id for m in model.messages),
        *(sc.id for sc in model.schemas),
        *(p.id for p in model.provenance),
        # v0.5.0 I4: Topic/Subscription plus their internal source-owned carriers, through the same
        # ownership/reconciliation path (§11: no parallel lifecycle engine).
        *(t.id for t in model.topics),
        *(s.id for s in model.subscriptions),
        *(d.id for d in model.pubsub_declarations),
        *(c.id for c in model.subscription_dead_letter_configurations),
        # I2 Draft 0.2 §3 item 6: infrastructure facts go through the *same* ownership and
        # reconciliation path as every other canonical fact - including them here is what makes
        # `plan_source_claim_reconciliation`'s claim-key diff, `_EXPIRE_NODES_QUERY`'s
        # last-owner-wins deletion, and `_EXPIRE_NODES_QUERY`'s shared-ownership retirement
        # apply to them unchanged.
        *(e.id for e in model.infrastructure_entities),
        *(c.id for c in model.infrastructure_contributions),
        *(c.id for c in model.infrastructure_claims),
        # The per-source claim-contribution row (see _write_infrastructure_nodes) is its own owned
        # node, keyed per (claim, THIS source), so it must participate in ownership reconciliation
        # the same way `InfrastructureContribution` already does.
        *(
            infrastructure_claim_contribution_id(claim.id, source_instance_id)
            for claim in model.infrastructure_claims
        ),
    }


def model_relation_keys(model: ArchitectureModel) -> set[str]:
    return {relation_key(r) for r in model.relations}


def owners_after_run(
    committed_owners: AbstractSet[str],
    key: str,
    *,
    run_source_ids: AbstractSet[str],
    run_emitters: Mapping[str, AbstractSet[str]],
) -> set[str]:
    """Who owns a claim once the whole run has committed: its committed owners outside this run,
    plus the run's sources that still emit it. Independent of the order the run's sources are
    reconciled in, so a claim two sources of one run both stop emitting expires for both."""
    return {owner for owner in committed_owners if owner not in run_source_ids} | set(
        run_emitters.get(key, ())
    )


def dropped_claim_owners(
    owned: Mapping[str, AbstractSet[str]],
    *,
    source_instance_id: str,
    run_source_ids: AbstractSet[str],
    run_emitters: Mapping[str, AbstractSet[str]],
) -> dict[str, set[SourceInstanceId]]:
    """`committed_claim_owners` for `plan_source_claim_reconciliation`: this source plus every owner
    the claim will have after the run, so a dropped claim is `expired` only when nobody else will
    own it, and `ownership_removed` otherwise. Owner ids are stored as plain strings, and
    `SourceInstanceId` is a typing-only NewType, so wrapping them changes no value."""
    return {
        key: {
            SourceInstanceId(owner)
            for owner in {source_instance_id}
            | owners_after_run(
                owners, key, run_source_ids=run_source_ids, run_emitters=run_emitters
            )
        }
        for key, owners in owned.items()
    }


def effect_set(
    node_ids: AbstractSet[str], relation_keys: AbstractSet[str], public: AbstractSet[str]
) -> ClaimEffectSet:
    return ClaimEffectSet(
        public_node_ids=tuple(sorted(node_ids & public)),
        relation_keys=tuple(sorted(relation_keys)),
        internal_count=len(node_ids - public),
    )


def without_owners(props: dict | None) -> dict | None:
    if props is None:
        return None
    return {key: value for key, value in props.items() if key != "owner_source_ids"}
