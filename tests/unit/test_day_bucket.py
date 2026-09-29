from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.telemetry.model import day_bucket


def test_day_bucket_utc_input_unchanged() -> None:
    timestamp = datetime(2026, 9, 29, 13, 45, 1, tzinfo=UTC)
    start, end = day_bucket(timestamp)
    assert start == datetime(2026, 9, 29, tzinfo=UTC)
    assert end == datetime(2026, 9, 30, tzinfo=UTC)


def test_day_bucket_offset_near_midnight_uses_utc_day() -> None:
    plus_two = timezone(timedelta(hours=2))
    timestamp = datetime(2026, 9, 29, 1, 30, tzinfo=plus_two)
    start, end = day_bucket(timestamp)
    assert start == datetime(2026, 9, 28, tzinfo=UTC)
    assert end == datetime(2026, 9, 29, tzinfo=UTC)


def test_day_bucket_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        day_bucket(datetime(2026, 9, 29, 12, 0, 0))
