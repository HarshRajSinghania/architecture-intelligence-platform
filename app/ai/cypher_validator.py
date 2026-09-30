import re

from app.graph.labels import NODE_LABELS
from app.graph_schema.registry import RELATIONS

DEFAULT_MAX_DEPTH = 5
DEFAULT_MAX_RESULT_ROWS = 100

KNOWN_NODE_LABELS = set(NODE_LABELS.values())
KNOWN_RELATION_TYPES = frozenset(RELATIONS)

# Spec §15.3 explicit forbidden list, plus other Cypher clause/admin keywords not in the §15.2
# allowlist (MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT) - together these give
# allowlist-equivalent coverage for realistic Cypher without a full grammar/AST parser.
FORBIDDEN_KEYWORDS = {
    "CREATE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "MERGE",
    "DROP",
    "LOAD",
    "CALL",
    "UNWIND",
    "FOREACH",
    "UNION",
    "START",
    "USE",
    "SHOW",
    "EXPLAIN",
    "PROFILE",
    "GRANT",
    "DENY",
    "REVOKE",
    "TERMINATE",
    "INDEX",
    "CONSTRAINT",
    "ALTER",
    "RENAME",
    "DBMS",
}

# String literals, comments and backtick-quoted names, lexed together leftmost-first: none of them
# is code, and each can contain the others' delimiters (an apostrophe inside `it's`, a backtick
# inside a string). A doubled backtick escapes a backtick inside a quoted name. Neo4j ends a `//`
# comment at a carriage return as well as a newline (checked on Neo4j 5.26), so this must too, or
# a clause after `\r` would be hidden from these checks but still run.
_STRING_OR_COMMENT_RE = re.compile(
    r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:``|[^`])*`|//[^\r\n]*|/\*.*?\*/",
    re.DOTALL,
)
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NODE_LABEL_RE = re.compile(r"\(\s*\w*\s*:\s*([A-Za-z_][A-Za-z0-9_:]*)")
_REL_TYPE_RE = re.compile(r"\[\s*\w*\s*:\s*([A-Za-z_][A-Za-z0-9_|]*)")
_VAR_LENGTH_RE = re.compile(r"\[[^\]]*\]")
_STAR_DEPTH_RE = re.compile(r"\*\s*(\d+)?\s*(\.\.)?\s*(\d+)?")
_LIMIT_KEYWORD_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)
_RETURN_KEYWORD_RE = re.compile(r"\bRETURN\b", re.IGNORECASE)
# A LIMIT's argument must be one integer literal: digits ending at a word boundary, followed only
# by the end of the query, a closing bracket, or the next clause - never an operator, a parameter
# or a function call, whose value the validator can't bound.
_LIMIT_LITERAL_RE = re.compile(r"\s+(\d+)\b(?=\s*(?:$|[A-Za-z_)\]}]))")


class CypherValidationError(ValueError):
    pass


def _strip_strings_and_comments(cypher: str) -> str:
    """Blanks out string literals, comments and backtick-quoted names with same-length whitespace,
    so every position in the stripped code still maps to the same position in the original query."""
    return _STRING_OR_COMMENT_RE.sub(lambda match: " " * len(match.group(0)), cypher)


def _check_forbidden_keywords(code_only: str) -> None:
    tokens = {t.upper() for t in _TOKEN_RE.findall(code_only)}
    forbidden_found = tokens & FORBIDDEN_KEYWORDS
    if forbidden_found:
        raise CypherValidationError(
            f"forbidden Cypher construct(s): {', '.join(sorted(forbidden_found))}"
        )


def _check_requires_return(code_only: str) -> None:
    if "RETURN" not in {t.upper() for t in _TOKEN_RE.findall(code_only)}:
        raise CypherValidationError("query must contain a RETURN clause")


def _check_known_labels_and_relation_types(code_only: str) -> None:
    for match in _NODE_LABEL_RE.finditer(code_only):
        for label in match.group(1).split(":"):
            if label and label not in KNOWN_NODE_LABELS:
                raise CypherValidationError(f"unknown node label: {label}")
    for match in _REL_TYPE_RE.finditer(code_only):
        for rel_type in match.group(1).split("|"):
            if rel_type and rel_type not in KNOWN_RELATION_TYPES:
                raise CypherValidationError(f"unknown relationship type: {rel_type}")


def _check_traversal_depth(code_only: str, max_depth: int) -> None:
    for bracket_match in _VAR_LENGTH_RE.finditer(code_only):
        pattern = bracket_match.group(0)
        star_match = _STAR_DEPTH_RE.search(pattern)
        if star_match is None:
            continue
        min_str, has_range, max_str = star_match.groups()
        if has_range:
            if not max_str:
                raise CypherValidationError("unbounded variable-length traversal is not allowed")
            depth = int(max_str)
        elif min_str:
            depth = int(min_str)
        else:
            raise CypherValidationError("unbounded variable-length traversal is not allowed")
        if depth > max_depth:
            raise CypherValidationError(f"traversal depth {depth} exceeds max_depth {max_depth}")


def _reject_multiple_statements(code_only: str) -> None:
    if ";" in code_only:
        raise CypherValidationError("multiple statements are not allowed")


def _limit_literal_spans(code_only: str) -> list[tuple[int, int]]:
    """The (start, end) span of every LIMIT's integer literal, found in code only - a LIMIT inside
    a string or comment isn't one."""
    spans = []
    for keyword in _LIMIT_KEYWORD_RE.finditer(code_only):
        literal = _LIMIT_LITERAL_RE.match(code_only, keyword.end())
        if literal is None:
            raise CypherValidationError("LIMIT must be followed by a single integer literal")
        spans.append(literal.span(1))
    return spans


def _bracket_depths(code_only: str) -> list[int]:
    depths, depth = [], 0
    for char in code_only:
        if char in ")]}":
            depth -= 1
        depths.append(depth)
        if char in "([{":
            depth += 1
    return depths


def _final_return_has_limit(code_only: str) -> bool:
    """Whether the query's last top-level RETURN is followed by a top-level LIMIT. A LIMIT inside a
    subquery (COUNT { ... }, EXISTS { ... }) or before the last RETURN doesn't bound the result."""
    depths = _bracket_depths(code_only)
    top_level_returns = [
        match.start()
        for match in _RETURN_KEYWORD_RE.finditer(code_only)
        if depths[match.start()] == 0
    ]
    if not top_level_returns:
        return False
    return any(
        match.start() > top_level_returns[-1] and depths[match.start()] == 0
        for match in _LIMIT_KEYWORD_RE.finditer(code_only)
    )


def _ends_in_line_comment(cypher: str) -> bool:
    end = len(cypher.rstrip())
    return any(
        match.group(0).startswith("//") and match.end() >= end
        for match in _STRING_OR_COMMENT_RE.finditer(cypher)
    )


def _enforce_result_row_limit(cypher: str, code_only: str, max_result_rows: int) -> str:
    """Spec §15.4: clamps every LIMIT literal above max_result_rows and, unless the final top-level
    RETURN already has a LIMIT, appends one - on a new line when the query ends in a `//` comment,
    which would otherwise swallow it."""
    for start, end in reversed(_limit_literal_spans(code_only)):
        if int(cypher[start:end]) > max_result_rows:
            cypher = cypher[:start] + str(max_result_rows) + cypher[end:]
    if _final_return_has_limit(code_only):
        return cypher
    separator = "\n" if _ends_in_line_comment(cypher) else " "
    return f"{cypher.rstrip()}{separator}LIMIT {max_result_rows}"


def validate_cypher(
    cypher: str,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_result_rows: int = DEFAULT_MAX_RESULT_ROWS,
) -> str:
    """Enforces spec §15.2-§15.4: allowlisted read-only constructs, known labels/relation types, bounded traversal depth, and a row limit. Returns the query with LIMIT clamped/appended."""
    cypher = cypher.strip().rstrip(";").strip()
    if not cypher:
        raise CypherValidationError("empty query")

    code_only = _strip_strings_and_comments(cypher)
    _reject_multiple_statements(code_only)
    _check_forbidden_keywords(code_only)
    _check_requires_return(code_only)
    _check_known_labels_and_relation_types(code_only)
    _check_traversal_depth(code_only, max_depth)

    return _enforce_result_row_limit(cypher, code_only, max_result_rows)
