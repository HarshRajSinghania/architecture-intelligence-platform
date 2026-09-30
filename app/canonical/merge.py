"""Combining the partial models several sources/adapters produce into one `ArchitectureModel`. A
pure canonical-model operation: no I/O, no source-adapter or graph dependency."""

from collections.abc import Sequence

from app.canonical.infrastructure import (
    InfrastructureClaim,
    InfrastructureContribution,
    InfrastructureEntity,
)
from app.canonical.model import (
    ArchitectureModel,
    Message,
    Operation,
    Queue,
    Schema,
    Service,
    Subscription,
    Topic,
)
from app.canonical.pubsub import PubSubDeclaration, SubscriptionDeadLetterConfiguration
from app.provenance.model import Provenance


def merge_models(models: Sequence[ArchitectureModel]) -> ArchitectureModel:
    """Combines partial models from multiple adapters/sources, deduping entities by id (first
    wins) - unchanged from the old `app.ingestion.pipeline.merge_models`, just relocated: owner-
    scoped ids are already the correct merge key, so this needed no behavior change.
    """
    services: dict[str, Service] = {}
    operations: dict[str, Operation] = {}
    queues: dict[str, Queue] = {}
    messages: dict[str, Message] = {}
    schemas: dict[str, Schema] = {}
    relations = []
    seen_relations: set[tuple[str, str, str]] = set()
    provenance: list[Provenance] = []
    # I2 Draft 0.2 §3 prerequisite slice (PR B), §7.1: dedup keys are this PR's own choice, matching
    # the pattern `relations`' own (type, source_id, target_id) key already establishes - not
    # literally named by the spec text, which describes the merge/conflict *rule*, not an in-memory
    # dict key. First-wins here, exactly like every other entity kind above: the real per-source
    # evidence union (§7.1: "equal semantic digests merge contributions and union evidence") is a
    # later slice's graph-write concern, once a real adapter and persistence path exist - nothing
    # populates these fields yet.
    infrastructure_entities: dict[str, InfrastructureEntity] = {}
    infrastructure_contributions: dict[tuple[str, str], InfrastructureContribution] = {}
    infrastructure_claims: dict[tuple[str, str, str | None], InfrastructureClaim] = {}
    # v0.5.0 I4: first-wins by id, exactly like Queue. The two internal carriers' ids are
    # source-scoped (see app.canonical.pubsub), so they never collide across sources.
    topics: dict[str, Topic] = {}
    subscriptions: dict[str, Subscription] = {}
    pubsub_declarations: dict[str, PubSubDeclaration] = {}
    dead_letter_configurations: dict[str, SubscriptionDeadLetterConfiguration] = {}

    for model in models:
        for service in model.services:
            services.setdefault(service.id, service)
        for operation in model.operations:
            operations.setdefault(operation.id, operation)
        for queue in model.queues:
            queues.setdefault(queue.id, queue)
        for message in model.messages:
            messages.setdefault(message.id, message)
        for schema in model.schemas:
            schemas.setdefault(schema.id, schema)
        for relation in model.relations:
            key = (relation.type, relation.source_id, relation.target_id)
            if key not in seen_relations:
                seen_relations.add(key)
                relations.append(relation)
        provenance.extend(model.provenance)
        for topic in model.topics:
            topics.setdefault(topic.id, topic)
        for subscription in model.subscriptions:
            subscriptions.setdefault(subscription.id, subscription)
        for declaration in model.pubsub_declarations:
            pubsub_declarations.setdefault(declaration.id, declaration)
        for configuration in model.subscription_dead_letter_configurations:
            dead_letter_configurations.setdefault(configuration.id, configuration)
        for entity in model.infrastructure_entities:
            infrastructure_entities.setdefault(entity.id, entity)
        for contribution in model.infrastructure_contributions:
            infrastructure_contributions.setdefault(
                (contribution.entity_id, contribution.source_instance_id), contribution
            )
        for claim in model.infrastructure_claims:
            # §7.2: a claim's identity is shared across sources (hash of kind/subject/object), and
            # "deterministic evidence union" is required - first-wins would silently discard the
            # second source's evidence here, exactly as `SET n += $props` would overwrite it at the
            # graph layer (a real bug found in PR review). Union and re-sort so the merged claim
            # still satisfies its own sorted/duplicate-free invariant.
            key = (claim.kind, claim.subject_id, claim.object_id)
            existing = infrastructure_claims.get(key)
            if existing is None:
                infrastructure_claims[key] = claim
            elif set(claim.evidence_refs) - set(existing.evidence_refs):
                infrastructure_claims[key] = existing.model_copy(
                    update={
                        "evidence_refs": sorted(
                            set(existing.evidence_refs) | set(claim.evidence_refs)
                        )
                    }
                )

    return ArchitectureModel(
        services=list(services.values()),
        operations=list(operations.values()),
        queues=list(queues.values()),
        messages=list(messages.values()),
        schemas=list(schemas.values()),
        relations=relations,
        provenance=provenance,
        infrastructure_entities=list(infrastructure_entities.values()),
        infrastructure_contributions=list(infrastructure_contributions.values()),
        infrastructure_claims=list(infrastructure_claims.values()),
        topics=list(topics.values()),
        subscriptions=list(subscriptions.values()),
        pubsub_declarations=list(pubsub_declarations.values()),
        subscription_dead_letter_configurations=list(dead_letter_configurations.values()),
    )
