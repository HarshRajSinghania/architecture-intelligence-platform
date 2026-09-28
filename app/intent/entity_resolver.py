import re
from dataclasses import dataclass
from typing import Literal, LiteralString

import neo4j

_NORMALIZE_RE = re.compile(r"[\s_-]+")

_CANDIDATES_QUERY: dict[str, LiteralString] = {
    "Service": "MATCH (n:Service) RETURN n.id AS id, n.name AS name",
    "Queue": "MATCH (n:Queue) RETURN n.id AS id, n.name AS name",
}


@dataclass(frozen=True)
class ResolvedEntity:
    id: str
    name: str


def _normalize(text: str) -> str:
    return _NORMALIZE_RE.sub("", text.lower())


def resolve(candidates: list[tuple[str, str]], raw_text: str) -> ResolvedEntity | None:
    """Resolves a natural-language entity mention to a unique candidate, or None if there's no
    match or more than one (an ambiguous mention must never be guessed - spec §6.10)."""
    needle = _normalize(raw_text)

    exact = [c for c in candidates if _normalize(c[1]) == needle]
    if len(exact) == 1:
        return ResolvedEntity(*exact[0])
    if len(exact) > 1:
        return None

    partial = [c for c in candidates if needle in _normalize(c[1])]
    if len(partial) == 1:
        return ResolvedEntity(*partial[0])
    return None


def fetch_candidates(
    session: neo4j.Session, label: Literal["Service", "Queue"]
) -> list[tuple[str, str]]:
    return [(record["id"], record["name"]) for record in session.run(_CANDIDATES_QUERY[label])]
