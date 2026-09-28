import re
from dataclasses import dataclass

from app.graph_schema.registry import RELATIONS

# Same string/comment-stripping technique as cypher_validator.py's private helper, deliberately
# duplicated (not imported) so the two validators remain independently correct (spec §5.8).
_STRING_OR_COMMENT_RE = re.compile(
    r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|//[^\n]*|/\*.*?\*/", re.DOTALL
)

_NODE_HEAD_RE = re.compile(
    r"^\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)?(?P<labels>(?:\s*:\s*[A-Za-z_][A-Za-z0-9_]*)*)"
)
_LABEL_FINDALL_RE = re.compile(r":\s*([A-Za-z_][A-Za-z0-9_]*)")
_REL_HEAD_RE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*(?P<types>[A-Za-z_][A-Za-z0-9_|]*)"
)


class SemanticValidationError(ValueError):
    """Raised when generated Cypher's relationship direction/labels violate the graph schema
    registry's domain/range (spec §5.2/§5.10)."""

    def __init__(
        self,
        message: str,
        *,
        relation: str,
        expected_source: frozenset[str],
        expected_target: frozenset[str],
        actual_source: frozenset[str] | None = None,
        actual_target: frozenset[str] | None = None,
    ):
        super().__init__(message)
        self.relation = relation
        self.expected_source = frozenset(expected_source)
        self.expected_target = frozenset(expected_target)
        self.actual_source = frozenset(actual_source) if actual_source else None
        self.actual_target = frozenset(actual_target) if actual_target else None


@dataclass
class NodeToken:
    var: str | None
    labels: frozenset[str]
    start: int
    end: int


@dataclass
class RelToken:
    types: list[str]
    direction: str  # "incoming" | "outgoing" | "undirected"
    start: int
    end: int


def _strip_strings_and_comments(cypher: str) -> str:
    return _STRING_OR_COMMENT_RE.sub(" ", cypher)


def _match_bracket(code: str, open_pos: int, open_ch: str, close_ch: str) -> int | None:
    """`open_pos` points at `open_ch`. Returns the index just past the matching `close_ch`
    (depth-counted, so a nested open/close pair - e.g. a function call inside a property map -
    doesn't confuse the boundary), or None if unterminated."""
    n = len(code)
    depth = 1
    j = open_pos + 1
    while j < n and depth > 0:
        if code[j] == open_ch:
            depth += 1
        elif code[j] == close_ch:
            depth -= 1
        j += 1
    return j if depth == 0 else None


def _parse_node(body: str, start: int, end: int) -> NodeToken:
    match = _NODE_HEAD_RE.match(body)
    assert (
        match is not None
    )  # every group in the anchored pattern is optional, so it always matches
    var = match.group("var")
    labels = frozenset(_LABEL_FINDALL_RE.findall(match.group("labels") or ""))
    return NodeToken(var=var, labels=labels, start=start, end=end)


def _extract_rel_types(body: str) -> list[str]:
    match = _REL_HEAD_RE.match(body)
    if match is None:
        return []
    return [t for t in match.group("types").split("|") if t]


def _match_rel(code: str, i: int, *, incoming: bool) -> RelToken | None:
    n = len(code)
    j = i + 2 if incoming else i + 1
    while j < n and code[j].isspace():
        j += 1
    if j >= n or code[j] != "[":
        return None
    close = _match_bracket(code, j, "[", "]")
    if close is None:
        return None
    body = code[j + 1 : close - 1]
    m = close
    while m < n and code[m].isspace():
        m += 1
    if incoming:
        if m < n and code[m] == "-":
            end, direction = m + 1, "incoming"
        else:
            return None
    else:
        if code.startswith("->", m):
            end, direction = m + 2, "outgoing"
        elif m < n and code[m] == "-":
            end, direction = m + 1, "undirected"
        else:
            return None
    return RelToken(types=_extract_rel_types(body), direction=direction, start=i, end=end)


def _tokenize(code: str) -> list[NodeToken | RelToken]:
    """Depth-counting scan for node patterns `(...)` and relationship patterns `-[...]->` /
    `<-[...]-` / `-[...]-`, in order of occurrence. Everything else (keywords, WHERE conditions,
    property values) is skipped char-by-char - it never becomes a token, but its presence still
    breaks adjacency between the tokens on either side of it (see `_extract_chains`)."""
    tokens: list[NodeToken | RelToken] = []
    n = len(code)
    i = 0
    while i < n:
        ch = code[i]
        if ch == "(":
            close = _match_bracket(code, i, "(", ")")
            if close is None:
                break
            tokens.append(_parse_node(code[i + 1 : close - 1], i, close))
            i = close
            continue
        if code.startswith("<-", i):
            rel = _match_rel(code, i, incoming=True)
            if rel is not None:
                tokens.append(rel)
                i = rel.end
                continue
            i += 1
            continue
        if ch == "-":
            rel = _match_rel(code, i, incoming=False)
            if rel is not None:
                tokens.append(rel)
                i = rel.end
                continue
            i += 1
            continue
        i += 1
    return tokens


def _build_symbol_table(tokens: list[NodeToken | RelToken]) -> dict[str, frozenset[str]]:
    """Pass 1: variable -> labels, from every node occurrence anywhere in the query that states
    both - so a later bare reference to an already-bound variable (alias reuse across MATCH
    clauses, or inside a correlated EXISTS {...} subquery) still resolves (spec §5.11)."""
    table: dict[str, frozenset[str]] = {}
    for tok in tokens:
        if isinstance(tok, NodeToken) and tok.var and tok.labels:
            table[tok.var] = table.get(tok.var, frozenset()) | tok.labels
    return table


def _extract_chains(
    tokens: list[NodeToken | RelToken], code: str
) -> list[list[NodeToken | RelToken]]:
    """Pass 2: group tokens into maximal runs that are textually adjacent (only whitespace
    between consecutive tokens) and alternate node/rel/node/.... Any other content in between
    (a keyword, a WHERE condition, an EXISTS{ boundary) breaks the chain - multiple MATCH/
    OPTIONAL MATCH blocks and subqueries fall out of this for free."""
    raw_chains: list[list[NodeToken | RelToken]] = []
    current: list[NodeToken | RelToken] = []
    for tok in tokens:
        if current and code[current[-1].end : tok.start].strip() == "":
            current.append(tok)
        else:
            if current:
                raw_chains.append(current)
            current = [tok]
    if current:
        raw_chains.append(current)

    chains = []
    for chain in raw_chains:
        if len(chain) < 3 or len(chain) % 2 == 0:
            continue
        if all(isinstance(chain[k], NodeToken) for k in range(0, len(chain), 2)) and all(
            isinstance(chain[k], RelToken) for k in range(1, len(chain), 2)
        ):
            chains.append(chain)
    return chains


def _resolve_labels(
    node: NodeToken, symbol_table: dict[str, frozenset[str]]
) -> frozenset[str] | None:
    if node.labels:
        return node.labels
    if node.var and node.var in symbol_table:
        return symbol_table[node.var]
    return None


def _fmt(labels: frozenset[str] | None) -> str:
    return "/".join(sorted(labels)) if labels else "?"


def _orientation_ok(defn, src: frozenset[str] | None, tgt: frozenset[str] | None) -> bool:
    src_ok = src is None or bool(src & defn.source_labels)
    tgt_ok = tgt is None or bool(tgt & defn.target_labels)
    return src_ok and tgt_ok


def _triple_valid_for_def(defn, a_labels, b_labels, direction: str) -> bool:
    if direction == "outgoing":
        return _orientation_ok(defn, a_labels, b_labels)
    if direction == "incoming":
        return _orientation_ok(defn, b_labels, a_labels)
    # undirected: Neo4j matches a stored relationship regardless of which way it was written
    return _orientation_ok(defn, a_labels, b_labels) or _orientation_ok(defn, b_labels, a_labels)


def _check_triple(
    node_a: NodeToken,
    rel: RelToken,
    node_b: NodeToken,
    symbol_table: dict[str, frozenset[str]],
) -> None:
    if not rel.types:
        return  # untyped relationship pattern - nothing to check

    known_defs = []
    for rel_type in rel.types:
        definition = RELATIONS.get(rel_type)
        if definition is None:
            raise SemanticValidationError(
                f"unknown relationship type: {rel_type}",
                relation=rel_type,
                expected_source=frozenset(),
                expected_target=frozenset(),
            )
        known_defs.append(definition)

    a_labels = _resolve_labels(node_a, symbol_table)
    b_labels = _resolve_labels(node_b, symbol_table)

    if any(_triple_valid_for_def(d, a_labels, b_labels, rel.direction) for d in known_defs):
        return

    primary = known_defs[0]
    actual_source, actual_target = (
        (b_labels, a_labels) if rel.direction == "incoming" else (a_labels, b_labels)
    )
    raise SemanticValidationError(
        f"Relation {primary.name} expects {_fmt(primary.source_labels)} -> "
        f"{_fmt(primary.target_labels)} but query contains {_fmt(actual_source)} -> "
        f"{_fmt(actual_target)}",
        relation=primary.name,
        expected_source=primary.source_labels,
        expected_target=primary.target_labels,
        actual_source=actual_source,
        actual_target=actual_target,
    )


class SemanticQueryValidator:
    """Checks generated Cypher's relationship domain/range against the graph schema registry -
    e.g. rejects `(q:Queue)-[:SENDS]->(s:Service)` since SENDS is only valid Service -> Queue
    (spec §5.2/§5.9). Complements, and runs after, the security/read-only cypher_validator."""

    def validate(self, cypher: str) -> None:
        code = _strip_strings_and_comments(cypher)
        tokens = _tokenize(code)
        symbol_table = _build_symbol_table(tokens)
        for chain in _extract_chains(tokens, code):
            for idx in range(0, len(chain) - 2, 2):
                node_a, rel, node_b = chain[idx], chain[idx + 1], chain[idx + 2]
                # _extract_chains only returns chains alternating NodeToken/RelToken/NodeToken...
                assert isinstance(node_a, NodeToken) and isinstance(node_b, NodeToken)
                assert isinstance(rel, RelToken)
                _check_triple(node_a, rel, node_b, symbol_table)
