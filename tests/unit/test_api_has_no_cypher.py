"""The REST/HTML adapters map results to HTTP; graph queries live in `app.graph.read_models` (and
`app.analysis`). This keeps Cypher from creeping back into `app/api/`."""

import re
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2] / "app" / "api"
_CYPHER = re.compile(r"\bsession\.run\(|\bMATCH\s*\(|\bUNWIND\s+\$|\bRETURN\s+\w+\.")


def test_no_api_module_contains_cypher_or_runs_a_session_query():
    offenders = {
        path.name: match.group(0)
        for path in sorted(API_DIR.glob("*.py"))
        if (match := _CYPHER.search(path.read_text()))
    }
    assert not offenders, f"move these queries into app.graph.read_models: {offenders}"
