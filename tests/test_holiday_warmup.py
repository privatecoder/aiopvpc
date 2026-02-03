"""Tests for async holiday cache warmup in PVPCData."""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta

import pytest

from aiopvpc.const import KEY_PVPC, UTC_TZ
from aiopvpc.pvpc_data import PVPCData
from aiopvpc.pvpc_tariff import _national_p3_holidays
from tests.conftest import MockAsyncSession


@pytest.fixture(autouse=True)
def _clear_holiday_cache():
    _national_p3_holidays.cache_clear()
    yield
    _national_p3_holidays.cache_clear()


@pytest.mark.asyncio
async def test_holiday_warmup_uses_to_thread_before_period_helpers(monkeypatch):
    now = datetime(2024, 3, 9, 19, tzinfo=UTC_TZ)
    pvpc_data = PVPCData(session=MockAsyncSession(), holiday_source="python-holidays")
    expected_year = now.astimezone(pvpc_data._local_timezone).year
    prewarm_calls: list[tuple[int, str]] = []

    async def _fake_update_prices_series(
        _self, _sensor_key, current_prices, _url_now, _url_next, _local_ref_now
    ):
        return {**current_prices, now.replace(minute=0, second=0, microsecond=0): 0.123}

    async def _fake_to_thread(func, year, source):
        assert func is _national_p3_holidays
        prewarm_calls.append((year, source))
        return {date(year, 1, 1)}

    def _fake_price_period(*_args, **_kwargs):
        assert pvpc_data._warmed_holiday_years == {expected_year}
        return "P2", "P3", timedelta(hours=1)

    def _fake_power_period(*_args, **_kwargs):
        assert pvpc_data._warmed_holiday_years == {expected_year}
        return "P1", "P3", timedelta(hours=1)

    monkeypatch.setattr(PVPCData, "_update_prices_series", _fake_update_prices_series)
    monkeypatch.setattr("aiopvpc.pvpc_data.asyncio.to_thread", _fake_to_thread)
    monkeypatch.setattr(
        "aiopvpc.pvpc_data.get_current_and_next_price_periods", _fake_price_period
    )
    monkeypatch.setattr(
        "aiopvpc.pvpc_data.get_current_and_next_power_periods", _fake_power_period
    )

    await pvpc_data.async_update_all(None, now)
    assert prewarm_calls == [(expected_year, "python-holidays")]


@pytest.mark.asyncio
async def test_holiday_warmup_not_repeated_in_same_year(monkeypatch):
    now = datetime(2024, 3, 9, 19, tzinfo=UTC_TZ)
    pvpc_data = PVPCData(session=MockAsyncSession(), holiday_source="python-holidays")
    expected_year = now.astimezone(pvpc_data._local_timezone).year
    prewarm_calls: list[int] = []

    async def _fake_update_prices_series(
        _self, _sensor_key, current_prices, _url_now, _url_next, _local_ref_now
    ):
        return {**current_prices, now.replace(minute=0, second=0, microsecond=0): 0.123}

    async def _fake_to_thread(_func, year, _source):
        prewarm_calls.append(year)
        return {date(year, 1, 1)}

    monkeypatch.setattr(PVPCData, "_update_prices_series", _fake_update_prices_series)
    monkeypatch.setattr("aiopvpc.pvpc_data.asyncio.to_thread", _fake_to_thread)

    api_data = await pvpc_data.async_update_all(None, now)
    await pvpc_data.async_update_all(api_data, now + timedelta(hours=1))

    assert prewarm_calls == [expected_year]


@pytest.mark.asyncio
async def test_holiday_warmup_rollover_fetches_new_year_on_new_year(monkeypatch):
    dec31_22 = datetime(2024, 12, 31, 22, tzinfo=UTC_TZ)
    dec31_23 = datetime(2024, 12, 31, 23, tzinfo=UTC_TZ)
    main_thread_id = threading.get_ident()
    calls: list[tuple[int, int]] = []

    pvpc_data = PVPCData(session=MockAsyncSession(), holiday_source="python-holidays")

    async def _fake_update_prices_series(
        _self, _sensor_key, current_prices, _url_now, _url_next, _local_ref_now
    ):
        return {
            **current_prices,
            dec31_22: 0.111,
            dec31_23: 0.222,
        }

    def _fake_get_pvpc_holidays(year, **_kwargs):
        calls.append((year, threading.get_ident()))
        return [date(year, 1, 1)]

    monkeypatch.setattr(PVPCData, "_update_prices_series", _fake_update_prices_series)
    monkeypatch.setattr(
        "aiopvpc.pvpc_tariff.get_pvpc_holidays", _fake_get_pvpc_holidays
    )

    api_data = await pvpc_data.async_update_all(None, dec31_22)
    assert [year for year, _thread_id in calls] == [2024]
    assert all(thread_id != main_thread_id for _, thread_id in calls)

    api_data = await pvpc_data.async_update_all(api_data, dec31_23)
    assert [year for year, _thread_id in calls] == [2024, 2025]

    state_ok = pvpc_data.process_state_and_attributes(api_data, KEY_PVPC, dec31_23)
    assert state_ok
    assert len(calls) == 2
