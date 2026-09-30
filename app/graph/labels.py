"""The graph label vocabulary the import write path uses: the public canonical node labels (keyed by
`ArchitectureModel` field), the internal-only infrastructure labels, and the accepted relation types.

Moved verbatim out of `importer.py`, which re-exports `NODE_LABELS` and `KNOWN_RELATION_TYPES` for
existing importers.
"""

from app.graph_schema.registry import RELATIONS

NODE_LABELS = {
    "services": "Service",
    "operations": "Operation",
    "queues": "Queue",
    "messages": "Message",
    "schemas": "Schema",
    "provenance": "Evidence",
    # v0.5.0 I4 spec §6.2/§11: persisted from the same slice (2b) that bumps snapshot
    # canonicalization to v3 with dedicated Topic/Subscription node queries.
    "topics": "Topic",
    "subscriptions": "Subscription",
}

# I2 Draft 0.2 §3 item 6 / §7: internal-only infrastructure labels, deliberately NOT in
# `NODE_LABELS` above - that mapping is keyed by `ArchitectureModel` field name and assumes
# `model_dump(exclude={"id"})` yields Neo4j-storable primitives, which is not true for an entity's
# nested `ports` nor for contributions/claims whose `id` is a computed property rather than a field.
# `_write_infrastructure_nodes` handles them explicitly, using the same MERGE template.
INFRASTRUCTURE_ENTITY_LABEL = "InfrastructureEntity"

INFRASTRUCTURE_CONTRIBUTION_LABEL = "InfrastructureContribution"

INFRASTRUCTURE_CLAIM_LABEL = "InfrastructureClaim"

# I2 Draft 0.2 §7.2: "Claim contributions use the same source ownership, evidence-mode retention,
# deterministic evidence union... as entity contributions." A claim node is shared by every source
# asserting the same (kind, subject, object) - §7.2's own identity rule - so its own `evidence_refs`
# can never be written directly from any one source's model (a real bug found in PR review, twice:
# a plain overwrite made the stored evidence depend on which source wrote last, and a reduce-based
# union could accumulate refs forever - neither let a RETAINED source correctly REPLACE its own
# evidence on reimport, since nothing ever ran for a claim whose ownership hadn't changed). Instead,
# each source's own view of a claim is persisted as its own `InfrastructureClaimContribution` row -
# id-scoped per (claim, source) exactly like `InfrastructureContribution`, so a reimport correctly
# *overwrites* (never accumulates) that source's own evidence - and the claim's own `evidence_refs`
# is a derived, recomputed-from-scratch union of whatever contribution rows currently exist,
# computed by `_recompute_infrastructure_claim_evidence` after every source's own write+reconcile
# step. This is the same "one shared fact, several sources' own evidence" shape `InfrastructureEntity`
# /`InfrastructureContribution` already solve correctly; a claim needed its own contribution layer
# because §7.2 (unlike §7.1) puts `evidence_refs` on the shared claim object itself, with no
# adapter-facing per-source contribution type of its own.
INFRASTRUCTURE_CLAIM_CONTRIBUTION_LABEL = "InfrastructureClaimContribution"

# I1 spec §4/§7: the source-adapter seam's frozen relation vocabulary. `graph_schema.RELATIONS` is
# the single definition (it also carries each type's domain/range); this is its name set.
KNOWN_RELATION_TYPES = frozenset(RELATIONS)
