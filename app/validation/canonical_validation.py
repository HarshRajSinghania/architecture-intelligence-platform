from collections import defaultdict
from dataclasses import dataclass

from app.canonical.infrastructure import KUBERNETES_SOURCE_TYPE, UNARY_CLAIM_KINDS
from app.canonical.model import ArchitectureModel, relation_key

SCHEMA_RELATION_TYPES = {"REQUEST_SCHEMA", "RESPONSE_SCHEMA", "CONFORMS_TO"}


class CanonicalValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class CanonicalValidationIssue:
    """One canonical-model invariant violation, with the elements it implicates: the ids of the
    offending entities and the `TYPE:source_id:target_id` keys of the offending relations. A
    discovery run uses them to attribute the issue to the sources that emitted those elements
    (v0.5.0 I5 finding F1)."""

    message: str
    element_ids: tuple[str, ...]


def _issue(message: str, *element_ids: str) -> CanonicalValidationIssue:
    return CanonicalValidationIssue(message=message, element_ids=tuple(element_ids))


def _check_unique(
    entity_ids: list[str], label: str, errors: list[CanonicalValidationIssue]
) -> None:
    seen: set[str] = set()
    for entity_id in entity_ids:
        if entity_id in seen:
            errors.append(_issue(f"{label} id is not unique: {entity_id}", entity_id))
        seen.add(entity_id)


def validate_canonical_model(model: ArchitectureModel) -> None:
    """Enforces V1-V8 (spec §10) against a fully merged ArchitectureModel."""
    issues = canonical_validation_issues(model)
    if issues:
        raise CanonicalValidationError([issue.message for issue in issues])


def canonical_validation_issues(model: ArchitectureModel) -> list[CanonicalValidationIssue]:
    """Every V1-V8 (spec §10) violation in a merged ArchitectureModel, in a deterministic order.
    Empty when the model is valid."""
    errors: list[CanonicalValidationIssue] = []

    service_ids = {s.id for s in model.services}
    queue_ids = {q.id for q in model.queues}
    message_ids = {m.id for m in model.messages}
    schema_ids = {s.id for s in model.schemas}
    operation_ids = {o.id for o in model.operations}
    topic_ids = {t.id for t in model.topics}
    subscription_ids = {s.id for s in model.subscriptions}

    _check_unique_ids(model, errors)
    _check_operation_providers(model, errors)
    _check_calls_targets(model, operation_ids=operation_ids, errors=errors)
    _check_schema_references(model, schema_ids=schema_ids, errors=errors)
    _check_dead_letter_targets(model, errors)
    known_ids = (
        service_ids | operation_ids | queue_ids | message_ids | schema_ids | topic_ids
    ) | subscription_ids
    _check_relation_endpoints(model, known_ids=known_ids, errors=errors)

    _validate_pubsub(
        model,
        service_ids=service_ids,
        topic_ids=topic_ids,
        subscription_ids=subscription_ids,
        errors=errors,
    )

    _check_relation_evidence(model, errors)

    provenance_by_id = {p.id: p for p in model.provenance}
    _validate_infrastructure(model, provenance_by_id=provenance_by_id, errors=errors)

    return errors


def _check_unique_ids(model: ArchitectureModel, errors: list[CanonicalValidationIssue]) -> None:
    """V1 / V3 / V4: unique stable ids."""
    _check_unique([s.id for s in model.services], "Service", errors)
    _check_unique([q.id for q in model.queues], "Queue", errors)
    _check_unique([m.id for m in model.messages], "Message", errors)
    _check_unique([t.id for t in model.topics], "Topic", errors)
    _check_unique([s.id for s in model.subscriptions], "Subscription", errors)


def _check_operation_providers(
    model: ArchitectureModel, errors: list[CanonicalValidationIssue]
) -> None:
    """V2: every operation has exactly one provider, matching its own service_id."""
    provides_sources_by_target: dict[str, list[str]] = defaultdict(list)
    for relation in model.relations:
        if relation.type == "PROVIDES":
            provides_sources_by_target[relation.target_id].append(relation.source_id)
    for operation in model.operations:
        providers = provides_sources_by_target.get(operation.id, [])
        provides_ids = [f"PROVIDES:{provider}:{operation.id}" for provider in providers]
        if len(providers) != 1:
            errors.append(
                _issue(
                    f"Operation {operation.id} must have exactly one PROVIDES relation, found "
                    f"{len(providers)}",
                    operation.id,
                    *provides_ids,
                )
            )
        elif providers[0] != operation.service_id:
            errors.append(
                _issue(
                    f"Operation {operation.id} is provided by {providers[0]} but declares "
                    f"service_id {operation.service_id}",
                    operation.id,
                    *provides_ids,
                )
            )


def _check_calls_targets(
    model: ArchitectureModel, *, operation_ids: set[str], errors: list[CanonicalValidationIssue]
) -> None:
    """V5: every CALLS relation references an existing operation."""
    for relation in model.relations:
        if relation.type == "CALLS" and relation.target_id not in operation_ids:
            errors.append(
                _issue(
                    f"CALLS {relation.source_id} -> {relation.target_id} references unknown "
                    "operation",
                    relation_key(relation),
                )
            )


def _check_schema_references(
    model: ArchitectureModel, *, schema_ids: set[str], errors: list[CanonicalValidationIssue]
) -> None:
    """V6: schema references point to an existing schema."""
    for relation in model.relations:
        if relation.type in SCHEMA_RELATION_TYPES and relation.target_id not in schema_ids:
            errors.append(
                _issue(
                    f"{relation.type} {relation.source_id} -> {relation.target_id} references "
                    "unknown schema",
                    relation_key(relation),
                )
            )
    for operation in model.operations:
        for schema_id in (*operation.request_schema_ids, *operation.response_schema_ids):
            if schema_id not in schema_ids:
                errors.append(
                    _issue(
                        f"Operation {operation.id} references unknown schema {schema_id}",
                        operation.id,
                    )
                )
    for message in model.messages:
        if message.schema_id and message.schema_id not in schema_ids:
            errors.append(
                _issue(
                    f"Message {message.id} references unknown schema {message.schema_id}",
                    message.id,
                )
            )


def _check_dead_letter_targets(
    model: ArchitectureModel, errors: list[CanonicalValidationIssue]
) -> None:
    """V7: a DLQ must not point to itself."""
    for relation in model.relations:
        if relation.type == "DEAD_LETTERS_TO" and relation.source_id == relation.target_id:
            errors.append(
                _issue(
                    f"Queue {relation.source_id} cannot be its own DLQ",
                    relation_key(relation),
                )
            )


def _check_relation_endpoints(
    model: ArchitectureModel, *, known_ids: set[str], errors: list[CanonicalValidationIssue]
) -> None:
    """V8: relations only reference existing source/target entities."""
    for relation in model.relations:
        if relation.source_id not in known_ids:
            errors.append(
                _issue(
                    f"Relation {relation.type} has unknown source {relation.source_id}",
                    relation_key(relation),
                )
            )
        if relation.target_id not in known_ids:
            errors.append(
                _issue(
                    f"Relation {relation.type} has unknown target {relation.target_id}",
                    relation_key(relation),
                )
            )


def _check_relation_evidence(
    model: ArchitectureModel, errors: list[CanonicalValidationIssue]
) -> None:
    """Every relation's evidence_ids must reference a Provenance record in this model."""
    evidence_ids = {p.id for p in model.provenance}
    for relation in model.relations:
        for evidence_id in relation.evidence_ids:
            if evidence_id not in evidence_ids:
                errors.append(
                    _issue(
                        f"Relation {relation.type} {relation.source_id} -> {relation.target_id} "
                        f"references unknown evidence {evidence_id}",
                        relation_key(relation),
                    )
                )


# v0.5.0 I4 spec §6.3: the only generic Pub/Sub relation triples. RECEIVES_FROM/CARRIES keep their
# pre-I4 Queue endpoints and additionally admit the Subscription/Topic endpoints respectively.
_PUBSUB_TRIPLES = {
    "PUBLISHES_TO": ("service", "topic"),
    "SUBSCRIPTION_OF": ("subscription", "topic"),
}


def _validate_pubsub(
    model: ArchitectureModel,
    *,
    service_ids: set[str],
    topic_ids: set[str],
    subscription_ids: set[str],
    errors: list[CanonicalValidationIssue],
) -> None:
    ids_by_kind = {"service": service_ids, "topic": topic_ids, "subscription": subscription_ids}
    topics_by_subscription: dict[str, set[str]] = defaultdict(set)
    for relation in model.relations:
        if relation.type in _PUBSUB_TRIPLES:
            source_kind, target_kind = _PUBSUB_TRIPLES[relation.type]
            if relation.source_id not in ids_by_kind[source_kind]:
                errors.append(
                    _issue(
                        f"{relation.type} source {relation.source_id} is not a {source_kind}",
                        relation_key(relation),
                    )
                )
            if relation.target_id not in ids_by_kind[target_kind]:
                errors.append(
                    _issue(
                        f"{relation.type} target {relation.target_id} is not a {target_kind}",
                        relation_key(relation),
                    )
                )
            if relation.type == "SUBSCRIPTION_OF":
                topics_by_subscription[relation.source_id].add(relation.target_id)
        elif relation.type == "RECEIVES_FROM" and relation.target_id in topic_ids:
            errors.append(
                _issue(
                    f"RECEIVES_FROM target {relation.target_id} is a Topic, not a Subscription",
                    relation_key(relation),
                )
            )
        elif relation.type == "CARRIES" and relation.source_id in subscription_ids:
            errors.append(
                _issue(
                    f"CARRIES source {relation.source_id} is a Subscription, not a Topic",
                    relation_key(relation),
                )
            )

    # §4.2/§6.2: a Subscription is associated with exactly one Topic.
    for subscription_id in sorted(subscription_ids):
        bound = topics_by_subscription.get(subscription_id, set())
        if len(bound) != 1:
            errors.append(
                _issue(
                    f"Subscription {subscription_id} must be SUBSCRIPTION_OF exactly one Topic, "
                    f"found {sorted(bound)!r}",
                    subscription_id,
                    *(f"SUBSCRIPTION_OF:{subscription_id}:{topic}" for topic in sorted(bound)),
                )
            )

    for declaration in model.pubsub_declarations:
        expected = topic_ids if declaration.entity_kind == "TOPIC" else subscription_ids
        if declaration.entity_id not in expected:
            errors.append(
                _issue(
                    f"PubSubDeclaration {declaration.id} references unknown "
                    f"{declaration.entity_kind} {declaration.entity_id}",
                    declaration.id,
                )
            )
    for configuration in model.subscription_dead_letter_configurations:
        if configuration.subscription_id not in subscription_ids:
            errors.append(
                _issue(
                    f"SubscriptionDeadLetterConfiguration {configuration.id} references unknown "
                    f"Subscription {configuration.subscription_id}",
                    configuration.id,
                )
            )


def _check_infrastructure_evidence_ref(
    evidence_ref: str,
    *,
    provenance_by_id: dict,
    owner_description: str,
    owner_id: str,
    errors: list[CanonicalValidationIssue],
) -> None:
    """§7.2: "resolve within the selected snapshot." §9 (as amended): a Kubernetes source's
    evidence is internal-only, exactly like the facts it supports - if it were ever stamped with a
    public `source_type`, the exposure filters in `app.architecture_intelligence.repository`/
    `app.api.evidence` (which key on `source_type`, not on what references the evidence) would not
    know to hide it. Checked here so a mis-stamped adapter fails loudly in validation rather than
    silently leaking through a query filter no code path re-derives this from.
    """
    provenance = provenance_by_id.get(evidence_ref)
    if provenance is None:
        errors.append(
            _issue(f"{owner_description} references unknown evidence {evidence_ref}", owner_id)
        )
    elif provenance.source_type != KUBERNETES_SOURCE_TYPE:
        errors.append(
            _issue(
                f"{owner_description} references evidence {evidence_ref} stamped source_type "
                f"{provenance.source_type!r}, expected {KUBERNETES_SOURCE_TYPE!r} (§9: "
                "infrastructure evidence must be internal-only)",
                owner_id,
                evidence_ref,
            )
        )


def _validate_infrastructure(
    model: ArchitectureModel, *, provenance_by_id: dict, errors: list[CanonicalValidationIssue]
) -> None:
    """I2 Draft 0.2 §3 item 6: infrastructure facts pass through the same *validation* path as every
    other canonical fact. The per-object §7 invariants (arity, sortedness, kind-specific fields) are
    already enforced by `app.canonical.infrastructure`'s own Pydantic validators; what only a whole
    merged model can check is whether the ids those objects reference actually resolve - §7.2's
    "resolve within the selected snapshot" and "both referenced entity IDs must resolve in the
    canonical model" - and, per §9, that the evidence they resolve to is genuinely internal-only.
    """
    entity_ids = {entity.id for entity in model.infrastructure_entities}
    _check_unique(
        [entity.id for entity in model.infrastructure_entities], "Infrastructure entity", errors
    )

    for contribution in model.infrastructure_contributions:
        if contribution.entity_id not in entity_ids:
            errors.append(
                _issue(
                    f"Infrastructure contribution from {contribution.source_instance_id} "
                    f"references unknown entity {contribution.entity_id}",
                    contribution.id,
                )
            )
        for evidence_ref in contribution.evidence_refs:
            _check_infrastructure_evidence_ref(
                evidence_ref,
                provenance_by_id=provenance_by_id,
                owner_description=f"Infrastructure contribution for {contribution.entity_id}",
                owner_id=contribution.id,
                errors=errors,
            )

    for claim in model.infrastructure_claims:
        if claim.subject_id not in entity_ids:
            errors.append(
                _issue(
                    f"Infrastructure claim {claim.kind.value} references unknown subject "
                    f"{claim.subject_id}",
                    claim.id,
                )
            )
        # A unary claim's absent object is validated by the model itself; only a binary claim's
        # object has to resolve here (§7.2: "the other three claim kinds are binary and both
        # referenced entity IDs must resolve in the canonical model").
        if claim.kind not in UNARY_CLAIM_KINDS and claim.object_id not in entity_ids:
            errors.append(
                _issue(
                    f"Infrastructure claim {claim.kind.value} references unknown object "
                    f"{claim.object_id}",
                    claim.id,
                )
            )
        for evidence_ref in claim.evidence_refs:
            _check_infrastructure_evidence_ref(
                evidence_ref,
                provenance_by_id=provenance_by_id,
                owner_description=(
                    f"Infrastructure claim {claim.kind.value} on {claim.subject_id}"
                ),
                owner_id=claim.id,
                errors=errors,
            )
