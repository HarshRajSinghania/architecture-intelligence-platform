"""The v2 reader's page bound is enforced before any query runs (I2 decision record D3)."""

import pytest

from app.architecture_intelligence.scoped_evidence_repository import (
    DEFAULT_PAGE_SIZE,
    read_scoped_observed_calls,
)


class _ExplodingRunner:
    """Fails if the reader ever reaches the database."""

    def run(self, *args, **kwargs):
        raise AssertionError("the reader queried despite an out-of-bound limit")


@pytest.mark.parametrize("limit", [0, -1, DEFAULT_PAGE_SIZE + 1, 1_000_000])
def test_an_out_of_bound_limit_is_rejected_before_any_query(limit):
    with pytest.raises(ValueError, match="between 1 and 500"):
        read_scoped_observed_calls(_ExplodingRunner(), subject_id="service:x", limit=limit)  # pyright: ignore[reportArgumentType]


class _RecordingRunner:
    def __init__(self):
        self.limits = []

    def run(self, query, **params):
        self.limits.append(params["limit"])
        return iter(())


@pytest.mark.parametrize("limit", [1, 2, DEFAULT_PAGE_SIZE])
def test_an_in_bound_limit_queries_one_extra_row_to_decide_truncation(limit):
    runner = _RecordingRunner()

    page = read_scoped_observed_calls(runner, subject_id="service:x", limit=limit)  # pyright: ignore[reportArgumentType]

    assert runner.limits == [limit + 1]
    assert page.records == () and page.truncated is False


def test_the_default_limit_is_the_frozen_page_size():
    runner = _RecordingRunner()

    read_scoped_observed_calls(runner, subject_id="service:x")  # pyright: ignore[reportArgumentType]

    assert runner.limits == [DEFAULT_PAGE_SIZE + 1]
