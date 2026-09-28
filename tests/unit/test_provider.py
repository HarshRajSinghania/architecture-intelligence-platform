from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import openai
import pytest

from app.ai.provider import LLMProviderError, OpenAIProvider

# These tests mock the OpenAI SDK client directly - no real network call is made and no
# OPENAI_API_KEY is required.


def _dummy_connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(
        request=httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    )


def _completion_with(*, parsed=None, content=None):
    message = SimpleNamespace(parsed=parsed, content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_generate_cypher_returns_parsed_output_and_uses_correct_model():
    provider = OpenAIProvider(api_key="test-key")
    provider._client.chat.completions.parse = MagicMock(
        return_value=_completion_with(
            parsed=SimpleNamespace(cypher="MATCH (n:Service) RETURN n LIMIT 100")
        )
    )

    result = provider.generate_cypher(
        question="who sends payment-q?", schema_description="<schema>"
    )

    assert result == "MATCH (n:Service) RETURN n LIMIT 100"
    call_kwargs = provider._client.chat.completions.parse.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    user_message = call_kwargs["messages"][1]["content"]
    assert "who sends payment-q?" in user_message
    assert "<schema>" in user_message


def test_generate_cypher_wraps_sdk_errors():
    provider = OpenAIProvider(api_key="test-key")
    provider._client.chat.completions.parse = MagicMock(side_effect=_dummy_connection_error())

    with pytest.raises(LLMProviderError, match="Cypher generation failed"):
        provider.generate_cypher(question="x", schema_description="y")


def test_generate_cypher_raises_when_model_returns_no_parsed_result():
    provider = OpenAIProvider(api_key="test-key")
    provider._client.chat.completions.parse = MagicMock(return_value=_completion_with(parsed=None))

    with pytest.raises(LLMProviderError, match="Cypher generation failed"):
        provider.generate_cypher(question="x", schema_description="y")


def test_compose_answer_returns_message_content():
    provider = OpenAIProvider(api_key="test-key")
    provider._client.chat.completions.create = MagicMock(
        return_value=_completion_with(content="OrderService sends payment-q.")
    )

    result = provider.compose_answer(
        question="who sends payment-q?", cypher="MATCH (n) RETURN n", rows=[{"a": 1}]
    )

    assert result == "OrderService sends payment-q."
    call_kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert "payment-q" in call_kwargs["messages"][1]["content"]


def test_compose_answer_wraps_sdk_errors():
    provider = OpenAIProvider(api_key="test-key")
    provider._client.chat.completions.create = MagicMock(side_effect=_dummy_connection_error())

    with pytest.raises(LLMProviderError, match="Answer composition failed"):
        provider.compose_answer(question="x", cypher="MATCH (n) RETURN n", rows=[])


def test_compose_answer_raises_when_model_returns_no_content():
    provider = OpenAIProvider(api_key="test-key")
    provider._client.chat.completions.create = MagicMock(
        return_value=_completion_with(content=None)
    )

    with pytest.raises(LLMProviderError, match="Answer composition failed"):
        provider.compose_answer(question="x", cypher="MATCH (n) RETURN n", rows=[])
