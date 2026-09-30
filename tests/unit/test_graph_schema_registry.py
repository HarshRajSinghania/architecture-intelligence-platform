from app.graph.importer import KNOWN_RELATION_TYPES
from app.graph_schema.registry import RELATIONS


def test_registry_keys_exactly_match_known_relation_types():
    # Drift-safety net (AC-H2-1): every relation type the security validator/importer knows about
    # must have a domain/range definition here, and vice versa.
    assert set(RELATIONS.keys()) == KNOWN_RELATION_TYPES


def test_registry_name_matches_key():
    for key, definition in RELATIONS.items():
        assert definition.name == key


def test_registry_domain_range_matches_spec_table():
    expected = {
        "PROVIDES": ({"Service"}, {"Operation"}),
        "CALLS": ({"Service"}, {"Operation"}),
        "REQUEST_SCHEMA": ({"Operation"}, {"Schema"}),
        "RESPONSE_SCHEMA": ({"Operation"}, {"Schema"}),
        "SENDS": ({"Service"}, {"Queue"}),
        "RECEIVES_FROM": ({"Service"}, {"Queue", "Subscription"}),
        "CARRIES": ({"Queue", "Topic"}, {"Message"}),
        "CONFORMS_TO": ({"Message"}, {"Schema"}),
        "DEAD_LETTERS_TO": ({"Queue"}, {"Queue"}),
        # v0.5.0 I4 spec §6.3
        "PUBLISHES_TO": ({"Service"}, {"Topic"}),
        "SUBSCRIPTION_OF": ({"Subscription"}, {"Topic"}),
    }
    assert set(expected) == set(RELATIONS)
    for name, (source, target) in expected.items():
        definition = RELATIONS[name]
        assert definition.source_labels == frozenset(source)
        assert definition.target_labels == frozenset(target)


def test_every_consumer_of_the_relation_vocabulary_derives_from_the_registry():
    # Phase 1b: `graph_schema.RELATIONS` is the single definition; the importer's write-time
    # allowlist and the Cypher validator's read-time allowlist are its name set, not copies.
    from app.ai.cypher_validator import KNOWN_RELATION_TYPES as VALIDATOR_TYPES

    assert frozenset(RELATIONS) == KNOWN_RELATION_TYPES == VALIDATOR_TYPES


def test_relation_vocabulary_is_pinned_so_a_change_is_deliberate():
    assert frozenset(RELATIONS) == {
        "PROVIDES",
        "CALLS",
        "REQUEST_SCHEMA",
        "RESPONSE_SCHEMA",
        "SENDS",
        "RECEIVES_FROM",
        "CARRIES",
        "CONFORMS_TO",
        "DEAD_LETTERS_TO",
        "PUBLISHES_TO",
        "SUBSCRIPTION_OF",
    }


def test_relation_key_is_the_one_type_source_target_form():
    from app.canonical.model import Relation, relation_key
    from app.graph import importer

    relation = Relation(type="CALLS", source_id="service:a", target_id="operation:b")
    assert relation_key(relation) == "CALLS:service:a:operation:b"
    assert importer.relation_key is relation_key
