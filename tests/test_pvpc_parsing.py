"""Tests for aiopvpc."""

import logging
import zoneinfo
from datetime import datetime, timedelta
from typing import cast

import pytest

from aiopvpc.const import (
    ALL_SENSORS,
    DataSource,
    EsiosApiData,
    KEY_ADJUSTMENT,
    KEY_INDEXED,
    KEY_INJECTION,
    KEY_MAG,
    KEY_OMIE,
    KEY_PVPC,
    REFERENCE_TZ,
    SENSOR_KEY_TO_DATAID,
    TARIFFS,
    UTC_TZ,
)
from aiopvpc.parser import extract_esios_data
from aiopvpc.prices import (
    _split_today_tomorrow_prices,
    add_composed_price_sensors,
    make_price_sensor_attributes,
)
from aiopvpc.pvpc_data import PVPCData
from tests.conftest import MockAsyncSession, TZ_TEST


def _hourly_prices(day0: datetime, base: float) -> dict[datetime, float]:
    return {
        (day0 + timedelta(hours=i)).astimezone(UTC_TZ): round(base + i / 1000, 5)
        for i in range(24)
    }


def test_tomorrow_price_split_year_boundary():
    """Pin the today/tomorrow split across Dec 31 -> Jan 1 (ISO week 53).

    2026-12-31 is ISO 2026-W53-4 and 2027-01-01 is ISO 2026-W53-5, so
    calendar-date comparison must classify Jan 1 as next-day.
    """
    dec31 = datetime(2026, 12, 31, tzinfo=REFERENCE_TZ)
    jan1 = datetime(2027, 1, 1, tzinfo=REFERENCE_TZ)
    prices = {**_hourly_prices(dec31, 0.1), **_hourly_prices(jan1, 0.2)}
    utc_time = dec31.replace(hour=12).astimezone(UTC_TZ)

    attrs = make_price_sensor_attributes(KEY_PVPC, prices, utc_time, REFERENCE_TZ)
    next_day_tags = {key for key in attrs if key.startswith("price_next_day_")}
    assert len(next_day_tags) == 24
    assert attrs["price_next_day_00h"] == prices[jan1.astimezone(UTC_TZ)]
    assert attrs["price_00h"] == prices[dec31.astimezone(UTC_TZ)]


def test_tomorrow_price_split_sunday_to_monday():
    """Past prices must never be tagged as next-day.

    Regression: the old isocalendar-based comparison classified a Sunday
    (ISO day 7) as 'tomorrow' relative to the following Monday (ISO day 1).
    """
    sunday = datetime(2027, 1, 3, tzinfo=REFERENCE_TZ)  # ISO 2026-W53-7
    monday = datetime(2027, 1, 4, tzinfo=REFERENCE_TZ)  # ISO 2027-W01-1
    prices = {**_hourly_prices(sunday, 0.1), **_hourly_prices(monday, 0.2)}
    utc_time = monday.replace(hour=10).astimezone(UTC_TZ)

    today, tomorrow = _split_today_tomorrow_prices(prices, utc_time, REFERENCE_TZ)
    assert not tomorrow
    assert len(today) == 48


def test_composed_indexed_sensor_cleared_when_sources_unavailable():
    """Stale INDEXED prices are dropped when a source series disappears."""
    ts = datetime(2024, 3, 9, 10, tzinfo=UTC_TZ)
    data = EsiosApiData(
        last_update=ts,
        data_source="esios",
        sensors={
            KEY_PVPC: {ts: 0.2},
            KEY_ADJUSTMENT: {ts: 0.05},
        },
        availability={KEY_PVPC: True, KEY_ADJUSTMENT: True},
    )
    add_composed_price_sensors(data)
    assert data.sensors[KEY_INDEXED] == {ts: 0.15}
    assert data.availability[KEY_INDEXED]

    data.availability[KEY_ADJUSTMENT] = False
    add_composed_price_sensors(data)
    assert data.sensors[KEY_INDEXED] == {}
    assert not data.availability[KEY_INDEXED]


_TOKEN_URL = "https://api.esios.ree.es/indicators/1001?start_date=2024-03-09T00:00"


def _token_payload() -> dict:
    return {
        "indicator": {
            "name": "PVPC test",
            "id": 1001,
            "magnitud": [{"name": "Precio"}],
            "tiempo": [{"name": "Hora"}],
            "values": [
                {
                    "geo_id": 8741,  # Península
                    "datetime": "2024-03-09T10:00:00+01:00",
                    "value": 100.0,
                },
                {
                    "geo_id": 8742,  # Canarias
                    "datetime": "2024-03-09T10:00:00+01:00",
                    "value": 200.0,
                },
                {
                    "geo_id": 8744,  # Ceuta
                    "datetime": "2024-03-09T10:00:00+01:00",
                    "value": 300.0,
                },
            ],
        }
    }


def test_token_geo_zone_selection_is_explicit(caplog):
    """Geo zone follows tariff + local timezone; unknown tz -> Península."""
    madrid = zoneinfo.ZoneInfo("Europe/Madrid")
    canary = zoneinfo.ZoneInfo("Atlantic/Canary")

    res = extract_esios_data(
        _token_payload(), _TOKEN_URL, KEY_PVPC, TARIFFS[0], tz=madrid
    )
    assert list(res.series[KEY_PVPC].values()) == [0.1]

    res = extract_esios_data(
        _token_payload(), _TOKEN_URL, KEY_PVPC, TARIFFS[0], tz=canary
    )
    assert list(res.series[KEY_PVPC].values()) == [0.2]

    res = extract_esios_data(
        _token_payload(), _TOKEN_URL, KEY_PVPC, TARIFFS[1], tz=madrid
    )
    assert list(res.series[KEY_PVPC].values()) == [0.3]

    # an unrecognized timezone stays functional: Península is assumed,
    # with a warning
    with caplog.at_level(logging.WARNING, logger="aiopvpc"):
        res = extract_esios_data(
            _token_payload(),
            _TOKEN_URL,
            KEY_PVPC,
            TARIFFS[0],
            tz=zoneinfo.ZoneInfo("Europe/Lisbon"),
        )
    assert list(res.series[KEY_PVPC].values()) == [0.1]
    assert "not a recognized Spanish zone" in caplog.text


@pytest.mark.parametrize(
    "ts, source, timezone, n_prices, n_calls, n_prices_8h, available_8h",
    (
        ("2021-06-01 09:00:00", "esios", REFERENCE_TZ, 24, 1, 24, True),
        ("2021-06-01 09:00:00", "esios", TZ_TEST, 24, 1, 24, True),
        ("2024-03-09 09:00:00", "esios", REFERENCE_TZ, 24, 1, 24, True),
        ("2024-03-09 09:00:00", "esios", TZ_TEST, 24, 1, 24, True),
        ("2021-10-30 00:00:00+08:00", "esios_public", TZ_TEST, 0, 1, 0, False),
        ("2021-10-30 00:00:00", "esios_public", TZ_TEST, 24, 1, 24, True),
        ("2021-10-31 00:00:00", "esios_public", TZ_TEST, 25, 1, 25, True),
        ("2022-03-27 20:00:00", "esios_public", TZ_TEST, 23, 2, 23, False),
        ("2022-03-27 20:00:00+04:00", "esios_public", TZ_TEST, 23, 1, 23, False),
        ("2021-10-30 21:00:00", "esios_public", TZ_TEST, 49, 2, 26, True),
        ("2021-10-30 21:00:00+01:00", "esios_public", TZ_TEST, 49, 2, 26, True),
        ("2021-10-30 00:00:00", "esios_public", REFERENCE_TZ, 24, 1, 24, True),
        ("2021-10-31 00:00:00", "esios_public", REFERENCE_TZ, 25, 1, 25, True),
        ("2022-03-27 20:00:00", "esios_public", REFERENCE_TZ, 23, 2, 23, False),
        ("2021-10-30 21:00:00", "esios_public", REFERENCE_TZ, 49, 2, 25, True),
        ("2021-06-01 09:00:00", "esios_public", REFERENCE_TZ, 24, 1, 24, True),
        ("2021-06-01 09:00:00", "esios_public", TZ_TEST, 24, 1, 24, True),
    ),
)
@pytest.mark.asyncio
async def test_price_extract(
    ts,
    source,
    timezone,
    n_prices,
    n_calls,
    n_prices_8h,
    available_8h,
):
    """Test data parsing of official API files."""
    day = datetime.fromisoformat(ts)
    mock_session = MockAsyncSession()

    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        local_timezone=timezone,
        data_source=cast(DataSource, source),
        api_token="test-token" if source == "esios" else None,
    )

    api_data = await pvpc_data.async_update_all(None, day)
    pvpc_data.process_state_and_attributes(api_data, KEY_PVPC, day)
    assert len(api_data.sensors[KEY_PVPC]) == n_prices
    assert mock_session.call_count == n_calls
    assert len(api_data.sensors) == 1

    has_prices = pvpc_data.process_state_and_attributes(
        api_data, KEY_PVPC, day + timedelta(hours=10)
    )
    assert len(api_data.sensors[KEY_PVPC]) == n_prices_8h
    assert has_prices == available_8h
    if has_prices:
        last_dt, last_p = list(api_data.sensors[KEY_PVPC].items())[-1]
        assert last_dt.astimezone(timezone).hour == 23


@pytest.mark.asyncio
async def test_price_sensor_attributes():
    """Test data parsing of official API files."""
    day = datetime.fromisoformat("2024-03-09 09:00:00")
    mock_session = MockAsyncSession()

    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        api_token="test-token",
        sensor_keys=ALL_SENSORS,
    )

    api_data = await pvpc_data.async_update_all(None, day)
    for key in ALL_SENSORS:
        pvpc_data.process_state_and_attributes(api_data, key, day)
    assert len(api_data.sensors[KEY_PVPC]) == 24
    assert mock_session.call_count == 5
    assert len(api_data.sensors) == 6

    ref_data = {
        KEY_PVPC: {"hours_to_better_price": 1, "num_better_prices_ahead": 3},
        KEY_INJECTION: {"hours_to_better_price": 6, "num_better_prices_ahead": 6},
        KEY_MAG: {"hours_to_better_price": 1, "num_better_prices_ahead": 11},
        KEY_OMIE: {"hours_to_better_price": 1, "num_better_prices_ahead": 4},
        KEY_ADJUSTMENT: {"hours_to_better_price": 1, "num_better_prices_ahead": 2},
    }

    for key in ALL_SENSORS:
        has_prices = pvpc_data.process_state_and_attributes(
            api_data, key, day + timedelta(hours=2)
        )
        assert has_prices, key
        assert api_data.availability[key]
        last_dt, last_p = list(api_data.sensors[key].items())[-1]
        assert last_dt.astimezone(REFERENCE_TZ).hour == 23

        current_price = pvpc_data.states[key]
        sensor_attrs = pvpc_data.sensor_attributes[key]
        assert sensor_attrs["sensor_id"] == key
        assert sensor_attrs["data_id"] == SENSOR_KEY_TO_DATAID.get(key, "composed")
        assert sensor_attrs["price_12h"] == current_price
        prices_ahead = [sensor_attrs[f"price_{h:02}h"] for h in range(13, 24)]
        assert len(prices_ahead) == 11
        assert sensor_attrs["price_23h"] == last_p
        assert sensor_attrs["min_price"] == min(api_data.sensors[key].values())
        assert sensor_attrs["max_price"] == max(api_data.sensors[key].values())
        key_min_at = f'price_{sensor_attrs["min_price_at"]:02d}h'
        assert sensor_attrs[key_min_at] == min(api_data.sensors[key].values())
        key_max_at = f'price_{sensor_attrs["max_price_at"]:02d}h'
        assert sensor_attrs[key_max_at] == max(api_data.sensors[key].values())
        assert (
            sensor_attrs["hours_to_better_price"]
            == ref_data[key]["hours_to_better_price"]
        )
        assert (
            sensor_attrs["num_better_prices_ahead"]
            == ref_data[key]["num_better_prices_ahead"]
        )
        key_next = f'price_{12 + sensor_attrs["hours_to_better_price"]}h'
        if key == KEY_INJECTION:
            assert sensor_attrs[key_next] > current_price
            num_better = sum(1 for p in prices_ahead if p > current_price)
        else:
            assert sensor_attrs[key_next] < current_price
            num_better = sum(1 for p in prices_ahead if p < current_price)
        assert num_better == sensor_attrs["num_better_prices_ahead"]
