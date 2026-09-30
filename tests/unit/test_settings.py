import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.settings import TelemetryConfig, load_config, load_secrets, load_settings
from app.telemetry.adapter import adapt

CONFIG_YAML = """
architecture_intelligence:
  sources:
    directories:
      - id: aip-bundled-examples-v0.5
        root: examples
        stable_target_identity: urn:aip:logical-root:bundled-examples
  graph:
    uri: bolt://localhost:7687
    database: neo4j
    max_traversal_depth: 5
  import:
    openapi: true
    asyncapi: false
    architecture_manifest: true
  llm:
    enabled: true
    max_result_rows: 100
"""


def test_load_config_parses_spec_shape(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)

    config = load_config(config_path)

    assert len(config.sources.directories) == 1
    source = config.sources.directories[0]
    assert source.id == "aip-bundled-examples-v0.5"
    assert source.root == Path("examples")
    assert source.resolved_scope_id == "aip-bundled-examples-v0.5"
    assert source.resolved_stable_target_identity == "urn:aip:logical-root:bundled-examples"
    assert config.graph.uri == "bolt://localhost:7687"
    assert config.graph.database == "neo4j"
    assert config.graph.max_traversal_depth == 5
    assert config.import_.openapi is True
    assert config.import_.asyncapi is False
    assert config.llm.max_result_rows == 100


def test_sources_directories_rejects_bare_string_entry(tmp_path):
    # A bare directory path can no longer serve as a source's stable identity (I1 spec §6) - this
    # must fail clearly rather than silently deriving an id from the path.
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "architecture_intelligence:\n  sources:\n    directories:\n      - examples\n"
    )

    with pytest.raises(ValidationError, match="stable identity"):
        load_config(config_path)


def test_sources_directories_defaults_scope_id_and_target_identity_from_id(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "architecture_intelligence:\n"
        "  sources:\n"
        "    directories:\n"
        "      - id: my-repos\n"
        "        root: ./repositories\n"
    )

    config = load_config(config_path)

    source = config.sources.directories[0]
    assert source.resolved_scope_id == "my-repos"
    assert source.resolved_stable_target_identity == "urn:aip:logical-root:my-repos"


def test_sources_clusters_defaults_to_empty_list(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)

    config = load_config(config_path)

    assert config.sources.clusters == []


def test_sources_clusters_parses_a_configured_kubernetes_source(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "architecture_intelligence:\n"
        "  sources:\n"
        "    clusters:\n"
        "      - id: checkout-cluster\n"
        "        root: tests/fixtures/kubernetes/i2\n"
        "        envelope_relative_path: envelope.yaml\n"
        "        configured_scope_id: checkout-cluster-namespaces\n"
        "        cluster_uid: d3adbeef-0000-4000-8000-000000000001\n"
        "        evidence_mode: CAPTURED_RESOURCE\n"
        "        authorized_producer: aip-kubernetes-capture-agent\n"
        "        authority_record: checkout-cluster-capture-authority\n"
    )

    config = load_config(config_path)

    assert len(config.sources.clusters) == 1
    cluster = config.sources.clusters[0]
    assert cluster.id == "checkout-cluster"
    assert cluster.root == Path("tests/fixtures/kubernetes/i2")
    assert cluster.resolved_scope_id == "checkout-cluster-namespaces"
    assert (
        cluster.resolved_stable_target_identity
        == "urn:aip:k8s-cluster:d3adbeef-0000-4000-8000-000000000001"
    )


def test_sources_migrations_defaults_to_empty_list(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)

    config = load_config(config_path)

    assert config.sources.migrations == []


def test_sources_migrations_parses_configured_paths(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "architecture_intelligence:\n"
        "  sources:\n"
        "    directories:\n"
        "      - id: my-repos\n"
        "        root: ./repositories\n"
        "    migrations:\n"
        "      - config/migrations/v0.5.0-bundled-example-identities.yaml\n"
    )

    config = load_config(config_path)

    assert config.sources.migrations == [
        Path("config/migrations/v0.5.0-bundled-example-identities.yaml")
    ]


def test_load_config_defaults_on_empty_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("architecture_intelligence: {}\n")

    config = load_config(config_path)

    assert config.graph.database == "neo4j"
    assert config.import_.openapi is True
    assert config.telemetry.http_correlation.ttl_seconds == 60
    assert config.telemetry.http_correlation.max_pending_spans == 10000


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("ttl-seconds", 0),
        ("ttl-seconds", -1),
        ("max-pending-spans", 0),
        ("max-pending-spans", -1),
    ],
)
def test_http_correlation_limits_must_be_positive(tmp_path, field_name, value):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "architecture_intelligence:\n"
        "  telemetry:\n"
        "    http-correlation:\n"
        f"      {field_name}: {value}\n"
    )

    with pytest.raises(ValidationError) as exc_info:
        load_config(config_path)

    error = exc_info.value.errors()[0]
    assert error["loc"][-1] == field_name
    assert error["type"] == "greater_than"
    assert error["ctx"] == {"gt": 0}


def test_neo4j_uri_env_var_overrides_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")

    config = load_config(config_path)

    assert config.graph.uri == "bolt://neo4j:7687"


def test_load_secrets_reads_environment(monkeypatch):
    monkeypatch.setenv("NEO4J_USER", "custom-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    secrets = load_secrets()

    assert secrets.neo4j_user == "custom-user"
    assert secrets.neo4j_password == "secret"
    assert secrets.openai_api_key is not None
    assert secrets.openai_api_key.get_secret_value() == "sk-test"


def test_openai_api_key_is_hidden_from_the_settings_repr(monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    assert "sk-test" not in repr(load_secrets())


def test_load_secrets_defaults_neo4j_user(monkeypatch):
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    secrets = load_secrets()

    assert secrets.neo4j_user == "neo4j"
    assert secrets.openai_api_key is None


def test_load_secrets_raises_without_password(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD"):
        load_secrets()


def test_coverage_qualification_enabled_defaults_true_when_absent(tmp_path):
    # 11H-E/spec §22 - the app must still start with this new config section entirely absent,
    # defaulting to qualification enabled.
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)

    config = load_config(config_path)

    assert config.telemetry.coverage.qualification_enabled is True


def test_coverage_qualification_enabled_can_be_disabled(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "architecture_intelligence:\n"
        "  telemetry:\n"
        "    coverage:\n"
        "      qualification-enabled: false\n"
    )

    config = load_config(config_path)

    assert config.telemetry.coverage.qualification_enabled is False


def test_load_settings_combines_config_and_secrets(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    settings = load_settings(config_path)

    assert settings.config.graph.database == "neo4j"
    assert settings.secrets.neo4j_password == "secret"


def test_no_subscription_alias_input_is_admitted():
    """v0.5.0 I4 spec §9/§13.2: Topic aliases are admitted, Subscription aliases are not - pinned
    structurally, since neither the telemetry config nor the adapter has anywhere to accept one."""
    fields = set(TelemetryConfig.model_fields)
    assert {"queue_aliases", "topic_aliases"} <= fields
    assert not {name for name in fields if "subscription" in name}
    parameters = set(inspect.signature(adapt).parameters)
    assert "topic_aliases" in parameters
    assert not {name for name in parameters if "subscription" in name and "alias" in name}
