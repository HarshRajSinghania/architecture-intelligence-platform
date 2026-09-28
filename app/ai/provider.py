from typing import Protocol

import openai
from pydantic import BaseModel

MODEL = "gpt-4o-mini"


class LLMProviderError(RuntimeError):
    """Wraps provider-specific failures so callers never depend on a vendor SDK's exception types."""


class LLMProvider(Protocol):
    """Provider abstraction (spec §15.5) so the PoC isn't locked to one LLM vendor."""

    def generate_cypher(self, *, question: str, schema_description: str) -> str:
        """Returns a single candidate Cypher query string for the given question."""
        ...

    def compose_answer(self, *, question: str, cypher: str, rows: list[dict]) -> str:
        """Returns a natural-language answer grounded only in the given rows."""
        ...


class _CypherGenerationResult(BaseModel):
    cypher: str


_CYPHER_SYSTEM_PROMPT = (
    "You translate natural-language questions about a software architecture into a single "
    "read-only Cypher query against the fixed graph schema you are given. Return only the "
    "Cypher query text - no markdown fences, no explanation. If the question cannot be "
    "answered with a read-only query against this schema, return the closest reasonable "
    "read-only query rather than an empty string."
)

_ANSWER_SYSTEM_PROMPT = (
    "You explain Cypher query results about a software architecture to the person who asked "
    "the question. State only what the given result rows show - never invent services, "
    "queues, or relationships that are not present in the rows. If the rows are empty, say "
    "plainly that the graph has no matching data; do not guess at an answer."
)


class OpenAIProvider:
    def __init__(self, api_key: str, *, model: str = MODEL):
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def generate_cypher(self, *, question: str, schema_description: str) -> str:
        user_message = f"Graph schema:\n{schema_description}\n\nQuestion: {question}"
        try:
            response = self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": _CYPHER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format=_CypherGenerationResult,
            )
        except openai.APIError as exc:
            raise LLMProviderError(f"Cypher generation failed: {exc}") from exc
        parsed = response.choices[0].message.parsed
        if parsed is None:  # e.g. a model refusal
            raise LLMProviderError("Cypher generation failed: the model returned no parsed result")
        return parsed.cypher

    def compose_answer(self, *, question: str, cypher: str, rows: list[dict]) -> str:
        user_message = (
            f"Question: {question}\n\nCypher executed:\n{cypher}\n\nResult rows (JSON): {rows}"
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _ANSWER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
        except openai.APIError as exc:
            raise LLMProviderError(f"Answer composition failed: {exc}") from exc
        content = response.choices[0].message.content
        if content is None:  # e.g. a model refusal
            raise LLMProviderError("Answer composition failed: the model returned no content")
        return content
