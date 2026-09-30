from app.graph import read_models


class _Result:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def __iter__(self):
        return iter(_Record(row) for row in self._rows)

    def single(self):
        return _Record(self._rows[0]) if self._rows else None

    def data(self):
        return [dict(row) for row in self._rows]


class _Record(dict):
    def data(self):
        return dict(self)


class _Session:
    """Returns canned rows keyed by the exact query text and records every call."""

    def __init__(self, rows_by_query: dict[str, list[dict]]):
        self._rows_by_query = rows_by_query
        self.calls: list[tuple[str, dict]] = []

    def run(self, query, **params):
        self.calls.append((query, params))
        return _Result(self._rows_by_query.get(query, []))


def test_get_returns_the_row_or_none():
    row = {"id": "service:a", "name": "A", "version": "1"}
    assert read_models.get_service(_Session({read_models._SERVICE_GET_QUERY: [row]}), "x") == row
    assert read_models.get_service(_Session({}), "service:missing") is None
    assert read_models.get_queue(_Session({}), "queue:missing") is None
    assert read_models.get_message(_Session({}), "message:missing") is None


def test_lists_return_plain_row_dicts():
    rows = [{"id": "queue:a", "name": "a"}]
    assert read_models.list_queues(_Session({read_models._QUEUE_LIST_QUERY: rows})) == rows
    assert read_models.list_services(_Session({})) == []


def test_incident_evidence_queries_differ_only_by_label():
    assert read_models._SERVICE_EVIDENCE_QUERY.replace("Service", "Queue") == (
        read_models._QUEUE_EVIDENCE_QUERY
    )
    assert "(:Service {id: $id})-[r]-()" in read_models._SERVICE_EVIDENCE_QUERY


def test_service_exists_reads_the_count():
    assert read_models.service_exists(
        _Session({read_models._SERVICE_EXISTS_QUERY: [{"c": 1}]}), "service:a"
    )
    assert not read_models.service_exists(
        _Session({read_models._SERVICE_EXISTS_QUERY: [{"c": 0}]}), "service:a"
    )


def test_attach_evidence_resolves_ids_in_one_batch_and_drops_unknown_ones():
    evidence = [{"id": "e1", "source_type": "OPENAPI"}]
    session = _Session({read_models._EVIDENCE_BY_IDS_QUERY: evidence})
    rows = [{"evidence_ids": ["e1", "gone"]}, {"evidence_ids": None}, {}]
    result = read_models.attach_evidence(session, rows)
    assert [r["evidence"] for r in result] == [evidence, [], []]
    assert len(session.calls) == 1  # one batch query, not one per row


def test_attach_evidence_runs_no_query_when_there_are_no_ids():
    session = _Session({})
    assert read_models.attach_evidence(session, [{"evidence_ids": []}]) == [
        {"evidence_ids": [], "evidence": []}
    ]
    assert session.calls == []


def test_queue_dead_letter_is_none_without_a_dlq():
    assert read_models.queue_dead_letter(_Session({}), "queue:a") is None
