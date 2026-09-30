from app.ai.provider import LLMProvider

GRAPH_SCHEMA_DESCRIPTION = """\
Node labels and their key properties:
  Service(id, name, version)
  Operation(id, service_id, operation_id, method, path)
  Queue(id, name, protocol, namespace, queue_type)
  Topic(id, name, protocol, namespace)
  Subscription(id, name, protocol, namespace)
  Message(id, name, version, schema_id)
  Schema(id, name, version, format)
  Evidence(id, source_type, source_file, source_revision, evidence_type)

Relationship types (always Service/Operation/Queue/Topic/Subscription/Message/Schema as documented):
  (Service)-[:PROVIDES]->(Operation)          REST provider
  (Service)-[:CALLS]->(Operation)              REST caller
  (Operation)-[:REQUEST_SCHEMA]->(Schema)      request payload
  (Operation)-[:RESPONSE_SCHEMA]->(Schema)     response payload
  (Service)-[:SENDS]->(Queue)                  async sender
  (Service)-[:RECEIVES_FROM]->(Queue)          async consumer
  (Queue)-[:CARRIES]->(Message)                message type on queue
  (Service)-[:PUBLISHES_TO]->(Topic)           pub/sub publisher
  (Subscription)-[:SUBSCRIPTION_OF]->(Topic)   named subscription of one topic (fan-out)
  (Service)-[:RECEIVES_FROM]->(Subscription)   pub/sub consumer through a subscription
  (Topic)-[:CARRIES]->(Message)                message type on topic
  (Message)-[:CONFORMS_TO]->(Schema)           message payload schema
  (Queue)-[:DEAD_LETTERS_TO]->(Queue)          DLQ relationship

Every relationship above also carries an evidence_ids property: an array of Evidence.id \
values naming which imported spec file(s) declared that fact. There is no direct graph edge \
from a relationship to Evidence - look up r.evidence_ids on the relationship, then \
MATCH (e:Evidence) WHERE e.id IN r.evidence_ids to find the source file(s)/revision(s).

Label every node variable with one of the node labels above, for example \
(s:Service)-[:CALLS]->(o:Operation); a node without a label is rejected.

Only MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, and LIMIT are permitted - the \
query must be read-only.\
"""


def generate_cypher(provider: LLMProvider, question: str) -> str:
    """Maps a question + the fixed graph schema (spec §11) to candidate Cypher via the provider."""
    return provider.generate_cypher(question=question, schema_description=GRAPH_SCHEMA_DESCRIPTION)
