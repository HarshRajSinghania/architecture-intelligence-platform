"""Fail-closed graph-reachability gate for LLM-generated Cypher (v0.6.0 I2 §6, pre-enablement gate
(f); I2 decision record D2).

`validate_cypher` and `SemanticQueryValidator` check safety and relation direction, but both accept
an unlabeled `MATCH (n)`, a label expression such as `(n:Service|X)` and a backtick label. Any of
these reaches internal nodes, including the v2 scoped evidence that later I2 slices store. This
module adds two independent checks, both of which must pass before a generated query runs:

1. `check_node_patterns`: a syntactic rule over the query text. Every node pattern must
   (a) carry only approved labels in the plain `:A:B` form, (b) reuse a variable bound earlier in
   the query, or (c) be an endpoint of a relationship pattern whose explicit types are all known.
   Internal nodes carry no relationships, so a typed expansion cannot reach them.
2. `check_plan`: the database's own `EXPLAIN` plan. Every leaf operator must be a label scan or
   index seek on an approved label, a relationship-type scan on known types, or `Argument`.
   Any other leaf, including one this module does not recognise, is rejected.

The syntactic rule catches the obvious shapes with a readable error; the plan check is the sound
backstop, since it inspects what Neo4j will actually execute.
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.ai.cypher_validator import CypherValidationError, _strip_strings_and_comments
from app.graph.labels import KNOWN_RELATION_TYPES, NODE_LABELS

# D2: the eight current public schema labels. `Evidence` stays approved because the generator
# prompt directs evidence lookups to `MATCH (e:Evidence)`; internal labels (AipInternalState,
# SourceState, Infrastructure*, RuntimeIdentityObservation, v2 scoped evidence, ...) are excluded.
APPROVED_NL_LABELS = frozenset(NODE_LABELS.values())
_KNOWN_RELATION_TYPES = frozenset(KNOWN_RELATION_TYPES)


class GraphReachabilityError(CypherValidationError):
    """Generated Cypher could reach nodes outside the approved public labels."""


# --- syntactic node-pattern check ------------------------------------------------------------

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_LABELS_INTRO_RE = re.compile(r"\blabels\s*\(", re.IGNORECASE)
_REL_RE = re.compile(r"<?-\s*\[(?P<body>[^\]]*)\]\s*->?|<?-->?")
_REL_BODY_RE = re.compile(
    rf"^\s*(?:{_IDENT})?\s*"
    rf"(?::\s*(?P<types>{_IDENT}(?:\s*\|\s*:?\s*{_IDENT})*))?\s*"
    r"(?:\*[\d\s.]*)?\s*(?:\{.*\})?\s*$",
    re.DOTALL,
)
_NODE_BODY_RE = re.compile(
    rf"^\s*(?P<var>{_IDENT})?\s*(?P<labels>(?::\s*{_IDENT}\s*)*)(?P<rest>.*)$", re.DOTALL
)
_LABEL_NAME_RE = re.compile(rf":\s*({_IDENT})")
_CLAUSE_KEYWORD_RE = re.compile(
    r"\b(MATCH|WHERE|WITH|RETURN|ORDER|SKIP|LIMIT|UNWIND)\b", re.IGNORECASE
)


def _paren_groups(code: str) -> tuple[list[tuple[int, int]], list[int]]:
    """Every balanced `(...)` span, plus the paren depth at each position. Unbalanced input
    (already impossible for a query Neo4j accepts) is rejected fail-closed."""
    groups: list[tuple[int, int]] = []
    stack: list[int] = []
    depth = [0] * (len(code) + 1)
    for index, char in enumerate(code):
        depth[index] = len(stack)
        if char == "(":
            stack.append(index)
        elif char == ")":
            if not stack:
                raise GraphReachabilityError("unbalanced parentheses")
            groups.append((stack.pop(), index))
    if stack:
        raise GraphReachabilityError("unbalanced parentheses")
    depth[len(code)] = 0
    return sorted(groups), depth


def _relationship_tokens(code: str) -> list[tuple[int, int, bool]]:
    """(start, end-exclusive, typed) for each relationship pattern. `typed` means explicit types
    that are all known and written in the plain `:A|B` form - anything else (untyped, `--`,
    `:!A`, `:%`, `:$(...)`) does not bind its endpoints."""
    tokens = []
    for match in _REL_RE.finditer(code):
        body = match.group("body")
        typed = False
        if body is not None:
            parsed = _REL_BODY_RE.match(body)
            if parsed and parsed.group("types"):
                names = re.findall(_IDENT, parsed.group("types"))
                typed = bool(names) and all(name in _KNOWN_RELATION_TYPES for name in names)
        tokens.append((match.start(), match.end(), typed))
    return tokens


def _previous_non_space(code: str, index: int) -> int:
    index -= 1
    while index >= 0 and code[index].isspace():
        index -= 1
    return index


def _next_non_space(code: str, index: int) -> int:
    index += 1
    while index < len(code) and code[index].isspace():
        index += 1
    return index


def _adjacent_relationship(
    code: str, start: int, end: int, tokens: list[tuple[int, int, bool]]
) -> tuple[bool, bool]:
    """(adjacent to any relationship pattern, adjacent to a typed one) for the node at
    `code[start..end]`."""
    before = _previous_non_space(code, start) + 1
    after = _next_non_space(code, end)
    adjacent = typed = False
    for token_start, token_end, token_typed in tokens:
        if token_end == before or token_start == after:
            adjacent = True
            typed = typed or token_typed
    return adjacent, typed


def _in_match_pattern(code: str, start: int, depth: list[int]) -> bool:
    """True when `start` sits in a MATCH clause's pattern part at the clause's own paren depth -
    where every top-level `(...)` is a node pattern, never a function call."""
    last = None
    for match in _CLAUSE_KEYWORD_RE.finditer(code, 0, start):
        # Only keywords at this node's own paren depth: an inline `(n:Service WHERE ...)` must not
        # hide a sibling node pattern that follows it.
        if depth[match.start()] == depth[start]:
            last = match
    return last is not None and last.group(1).upper() == "MATCH"


def _is_node_pattern(
    code: str, start: int, end: int, depth: list[int], adjacent_relationship: bool
) -> bool:
    if adjacent_relationship:
        return True
    previous = _previous_non_space(code, start)
    if previous >= 0 and (code[previous].isalnum() or code[previous] == "_"):
        # `count(`, `toLower(`: a function call - unless the word is MATCH itself (`MATCH(n)`).
        return code[: previous + 1].upper().endswith("MATCH") and _in_match_pattern(
            code, start, depth
        )
    if previous >= 0 and code[previous] in "[{":
        return True  # pattern comprehension `[(a)-->(b) | ...]` or short subquery `{ (a) }`
    return _in_match_pattern(code, start, depth)


def check_node_patterns(cypher: str) -> None:
    """Rejects any node pattern not provably bound to an approved public label (D2 rule 1)."""
    code = _strip_strings_and_comments(cypher)
    if _LABELS_INTRO_RE.search(code):
        raise GraphReachabilityError("label introspection (labels()) is not allowed")
    groups, depth = _paren_groups(code)
    tokens = _relationship_tokens(code)
    bound: set[str] = set()
    for start, end in groups:
        adjacent, typed = _adjacent_relationship(code, start, end, tokens)
        if not _is_node_pattern(code, start, end, depth, adjacent):
            continue
        parsed = _NODE_BODY_RE.match(code[start + 1 : end])
        rest = parsed.group("rest").strip() if parsed else "?"
        if parsed is None or not (
            rest == "" or rest.startswith("{") or re.match(r"WHERE\b", rest, re.IGNORECASE)
        ):
            raise GraphReachabilityError(
                "node pattern must use a plain variable and plain :Label syntax"
            )
        variable = parsed.group("var")
        labels = set(_LABEL_NAME_RE.findall(parsed.group("labels")))
        if labels:
            unapproved = sorted(labels - APPROVED_NL_LABELS)
            if unapproved:
                raise GraphReachabilityError(f"node label not allowed: {unapproved[0]}")
        elif not (variable in bound or typed):
            raise GraphReachabilityError(
                "every node pattern must carry an approved label, reuse a labeled variable, "
                "or be an endpoint of a typed relationship"
            )
        if variable:
            bound.add(variable)


# --- EXPLAIN plan check ----------------------------------------------------------------------

_NODE_LABEL_LEAVES = frozenset({"NodeByLabelScan"})
_NODE_INDEX_LEAVES = frozenset(
    {
        "NodeIndexSeek",
        "NodeUniqueIndexSeek",
        "NodeIndexScan",
        "NodeIndexContainsScan",
        "NodeIndexEndsWithScan",
        "NodeIndexSeekByRange",
        "NodeUniqueIndexSeekByRange",
    }
)
_RELATIONSHIP_TYPE_LEAVES = frozenset(
    {
        "DirectedRelationshipTypeScan",
        "UndirectedRelationshipTypeScan",
        "DirectedUnionRelationshipTypesScan",
        "UndirectedUnionRelationshipTypesScan",
    }
)
_ARGUMENT_LEAVES = frozenset({"Argument"})

_LABEL_SCAN_DETAILS_RE = re.compile(rf"^\s*{_IDENT}\s*:\s*({_IDENT})\s*$")
_INDEX_DETAILS_RE = re.compile(
    rf"^\s*(?:UNIQUE\s+|(?:RANGE|TEXT|POINT|FULLTEXT)\s+INDEX\s+)?{_IDENT}\s*:\s*({_IDENT})\s*\("
)
_REL_SCAN_DETAILS_RE = re.compile(
    rf"^\s*\({_IDENT}\)\s*<?-\s*\[\s*{_IDENT}\s*:\s*({_IDENT}(?:\s*\|\s*{_IDENT})*)\s*\]\s*->?\s*"
    rf"\({_IDENT}\)\s*$"
)


def _operator_name(operator: Mapping[str, Any]) -> str:
    return str(operator.get("operatorType", "")).split("@", 1)[0]


def _details(operator: Mapping[str, Any]) -> str:
    arguments = operator.get("args") or operator.get("arguments") or {}
    return str(arguments.get("Details", ""))


def _leaves(operator: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    children = operator.get("children") or []
    if not children:
        yield operator
        return
    for child in children:
        yield from _leaves(child)


def _check_leaf(leaf: Mapping[str, Any]) -> None:
    name = _operator_name(leaf)
    details = _details(leaf)
    if name in _ARGUMENT_LEAVES:
        return
    if name in _NODE_LABEL_LEAVES or name in _NODE_INDEX_LEAVES:
        pattern = _LABEL_SCAN_DETAILS_RE if name in _NODE_LABEL_LEAVES else _INDEX_DETAILS_RE
        match = pattern.match(details)
        if match and match.group(1) in APPROVED_NL_LABELS:
            return
        raise GraphReachabilityError(f"query plan reads a node label that is not allowed ({name})")
    if name in _RELATIONSHIP_TYPE_LEAVES:
        match = _REL_SCAN_DETAILS_RE.match(details)
        if match and all(t in _KNOWN_RELATION_TYPES for t in re.findall(_IDENT, match.group(1))):
            return
        raise GraphReachabilityError(f"query plan scans an unknown relationship type ({name})")
    raise GraphReachabilityError(f"query plan operator not allowed: {name or 'unknown'}")


def check_plan(plan: Mapping[str, Any] | None) -> None:
    """Rejects a plan whose leaf operators could read nodes outside the approved labels (D2
    rule 2). A missing plan is rejected rather than trusted."""
    if not plan:
        raise GraphReachabilityError("no query plan available to verify graph reachability")
    for leaf in _leaves(plan):
        _check_leaf(leaf)
