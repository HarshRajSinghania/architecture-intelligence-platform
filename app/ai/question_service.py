from dataclasses import dataclass
from itertools import islice

import neo4j

from app.ai.answer_composer import compose_answer
from app.ai.cypher_generator import generate_cypher
from app.ai.cypher_validator import DEFAULT_MAX_DEPTH, DEFAULT_MAX_RESULT_ROWS, validate_cypher
from app.ai.graph_reachability import check_node_patterns, check_plan
from app.ai.provider import LLMProvider
from app.ai.semantic_query_validator import SemanticQueryValidator
from app.graph.repository import open_session


@dataclass(frozen=True)
class AnswerResult:
    question: str
    cypher: str
    rows: list[dict]
    answer: str


class ArchitectureQuestionService:
    """Orchestrates generate -> security-validate -> semantic-validate -> reachability-check ->
    read-only execute -> compose (spec §15, hardening spec §5.4; v0.6.0 I2 decision record D2)."""

    def __init__(
        self,
        *,
        driver: neo4j.Driver,
        database: str,
        provider: LLMProvider,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_result_rows: int = DEFAULT_MAX_RESULT_ROWS,
    ):
        self._driver = driver
        self._database = database
        self._provider = provider
        self._max_depth = max_depth
        self._max_result_rows = max_result_rows
        self._semantic_validator = SemanticQueryValidator()

    def ask(self, question: str) -> AnswerResult:
        candidate_cypher = generate_cypher(self._provider, question)
        cypher = validate_cypher(
            candidate_cypher, max_depth=self._max_depth, max_result_rows=self._max_result_rows
        )
        self._semantic_validator.validate(cypher)
        check_node_patterns(cypher)

        with open_session(self._driver, database=self._database, read_only=True) as session:
            # D2 rule 2: the database's own plan for the final query must only read approved
            # labels. EXPLAIN plans without executing, so a rejected query never runs.
            plan = session.run("EXPLAIN " + cypher).consume().plan  # pyright: ignore[reportArgumentType]
            check_plan(plan)
            # neo4j's type hints declare Session.run's query as LiteralString to discourage
            # dynamic Cypher; generated Cypher is dynamic by design, gated by validate_cypher, the
            # semantic validator and the reachability gate above, and runs in a read-only session.
            result = session.run(cypher)  # pyright: ignore[reportArgumentType]
            # validate_cypher bounds the query's own LIMIT; reading at most max_result_rows records
            # keeps the bound even for a Cypher form its text analysis doesn't understand.
            rows = [record.data() for record in islice(result, self._max_result_rows)]

        answer = compose_answer(self._provider, question=question, cypher=cypher, rows=rows)
        return AnswerResult(question=question, cypher=cypher, rows=rows, answer=answer)
