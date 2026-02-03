"""Tests for aiopvpc."""

from datetime import datetime, timedelta

import pytest

from aiopvpc.const import REFERENCE_TZ
from aiopvpc.pvpc_tariff import get_current_and_next_tariff_periods


@pytest.mark.parametrize(
    "year, days_weekend_p3, extra_days_p3",
    (
        (2021, 104, 6),
        (2022, 105, 6),
        (2023, 105, 8),
        (2024, 104, 6),
        (2025, 104, 6),
    ),
)
def test_number_of_national_holidays(year, days_weekend_p3, extra_days_p3):
    """Calculate days with full P3 valley period."""
    holidays_p3 = weekend_days_p3 = 0
    day = datetime(year, 1, 1, 15, tzinfo=REFERENCE_TZ)
    while day.year == year:
        period, _, _ = get_current_and_next_tariff_periods(
            day, False, holiday_source="python-holidays"
        )
        if period == "P3":
            if day.isoweekday() > 5:
                weekend_days_p3 += 1
            else:
                holidays_p3 += 1
        day += timedelta(days=1)
    assert weekend_days_p3 == days_weekend_p3
    assert holidays_p3 == extra_days_p3


def test_default_holiday_source_is_csv(monkeypatch):
    called: dict[str, str] = {}

    def _fake_get_pvpc_holidays(year, source="csv", **_kwargs):
        called["source"] = source
        return {}

    monkeypatch.setattr(
        "aiopvpc.pvpc_tariff.get_pvpc_holidays", _fake_get_pvpc_holidays
    )
    day = datetime(2031, 2, 3, 15, tzinfo=REFERENCE_TZ)
    get_current_and_next_tariff_periods(day, False)

    assert called["source"] == "csv"
