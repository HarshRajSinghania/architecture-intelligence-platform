"""v0.5.0 I4 internal, source-owned Pub/Sub carriers - never canonical entities, relations, or public
properties, and never snapshot inputs.

- `PubSubDeclaration` (I4 spec §11): "Every declared Pub/Sub artifact SHALL retain source
  instance/revision/locator/pointer, semantic digest, adapter/version, broker/namespace evidence,
  kind evidence, identity inputs, and mapping-rule identity/version." The Queue path records only one
  document-level `Provenance`; this per-(entity, source, pointer) node is where the per-artifact
  retention lives (a slice-2 design decision, disclosed in its PR), modeled on I2's
  `InfrastructureContribution`.
- `SubscriptionDeadLetterConfiguration` (I4 spec §10): the Subscription-scoped declared dead-letter
  target, retained as exact tokens only - no generic target entity or relation is ever minted from
  it.

Both are written by the importer with the same MERGE-with-`owner_source_ids` template as every
other canonical node, so they inherit the existing ownership/replay/expiry engine unchanged (§11:
"No parallel lifecycle engine is permitted"). Every field is a Neo4j-storable primitive or list.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.common.encoding import length_delimited, sha256_hex, utf8

PUBSUB_DECLARATION_LABEL = "PubSubDeclaration"
SUBSCRIPTION_DEAD_LETTER_CONFIGURATION_LABEL = "SubscriptionDeadLetterConfiguration"

PubSubEntityKind = Literal["TOPIC", "SUBSCRIPTION"]
IdentityMethod = Literal["CONFIGURED", "DERIVED"]


class PubSubDeclaration(BaseModel):
    entity_id: str = Field(min_length=1)
    entity_kind: PubSubEntityKind
    source_instance_id: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    source_revision: str | None = None
    # The exact RFC 6901 pointer of the declaring construct: the Channel for a Topic, the subscribe
    # operation for a Subscription.
    source_pointer: str
    semantic_input_digest: str = Field(min_length=1)
    adapter_identity: str = Field(min_length=1)
    mapping_rule_id: str = Field(min_length=1)
    mapping_rule_version: str = Field(min_length=1)
    broker_id: str | None = None
    namespace: str | None = None
    # Sorted evidence-path names that established kind (Topic) or identity (Subscription), e.g.
    # `topicMappings`, `x-aip-destination-kind`, `subscriptionMappings`, `x-aip-subscription-name`.
    kind_evidence: list[str] = Field(min_length=1)
    identity_methods: list[IdentityMethod] = Field(min_length=1)
    # Identity inputs (§7.1/§7.2), flattened to primitives. `topic_address` is the exact
    # NFC-normalized Channel address; `topic_id`/`subscription_name` are set for a Subscription.
    topic_address: str | None = None
    topic_id: str | None = None
    subscription_name: str | None = None

    @property
    def id(self) -> str:
        key = length_delimited(
            utf8(self.entity_id), utf8(self.source_instance_id), utf8(self.source_pointer)
        )
        return f"urn:aip:pubsub-declaration:{sha256_hex(key)}"


class SubscriptionDeadLetterConfiguration(BaseModel):
    subscription_id: str = Field(min_length=1)
    source_instance_id: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    source_revision: str | None = None
    source_pointer: str
    # Exact declared tokens, NFC-normalized without trimming/case folding. Never resolved into an
    # entity id: broker dead-letter semantics differ materially (I4 spec §10).
    target_token: str = Field(min_length=1)
    target_kind_token: str | None = None

    @property
    def id(self) -> str:
        key = length_delimited(utf8(self.subscription_id), utf8(self.source_instance_id))
        return f"urn:aip:subscription-dlq:{sha256_hex(key)}"
