"""Tests for aiopvpc."""

import asyncio
import io
import logging
import zipfile
from asyncio import TimeoutError
from datetime import date, datetime, timedelta
from typing import cast

import pytest
from aiohttp import ClientError

from aiopvpc.const import (
    ALL_SENSORS,
    ATTRIBUTIONS,
    DataSource,
    ESIOS_PVPC,
    KEY_INJECTION,
    KEY_OMIE,
    KEY_PVPC,
    REFERENCE_TZ,
    UTC_TZ,
)
from aiopvpc.parser import get_daily_urls_to_download
from aiopvpc.pvpc_data import BadApiTokenAuthError, PVPCData
from tests.conftest import (
    check_num_datapoints,
    load_fixture,
    MockAsyncSession,
    run_h_step,
    TEST_EXAMPLES_PATH,
    TZ_TEST,
)


@pytest.mark.parametrize(
    "data_source, api_token, day_str, num_log_msgs, status, exception",
    (
        ("esios_public", None, "2032-10-26", 0, 200, None),
        ("esios_public", None, "2032-10-26", 1, 500, None),
        ("esios", "bad-token", "2032-10-26", 1, 403, None),
        ("esios", "bad-token", "2032-10-26", 1, 401, None),
        ("esios_public", None, "2032-10-26", 1, 200, TimeoutError),
        ("esios_public", None, "2032-10-26", 1, 200, ClientError),
    ),
)
@pytest.mark.asyncio
async def test_bad_downloads(
    data_source,
    api_token,
    day_str,
    num_log_msgs,
    status,
    exception,
    caplog,
):
    """Test data parsing of official API files."""
    day = datetime.fromisoformat(day_str).astimezone(REFERENCE_TZ)
    mock_session = MockAsyncSession(status=status, exc=exception)
    with caplog.at_level(logging.INFO):
        pvpc_data = PVPCData(
            session=mock_session,
            data_source=cast(DataSource, data_source),
            api_token=api_token,
        )
        if status == 401:
            with pytest.raises(BadApiTokenAuthError):
                await pvpc_data.async_update_all(None, day)
            assert mock_session.call_count == 1
            return

        api_data = await pvpc_data.async_update_all(None, day)
        assert not api_data.sensors[KEY_PVPC]
        assert not pvpc_data.process_state_and_attributes(api_data, KEY_PVPC, day)
        # Count only aiopvpc's own log records, ignoring dependency loggers
        # (e.g. pvpc_holidays emits INFO warmup messages of its own).
        own_log_records = [
            record for record in caplog.records if record.name.startswith("aiopvpc")
        ]
        assert len(own_log_records) == num_log_msgs
    assert mock_session.call_count == 1
    check_num_datapoints(api_data, (KEY_PVPC,), 0)


_PUBLIC_FIXTURE_2021_06_01 = "PVPC_CURV_DD_2021_06_01.json"


def _make_zip(member_name: str | None, payload: bytes = b"") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        if member_name is not None:
            zf.writestr(member_name, payload)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_public_download_with_bad_content_type_header():
    """Issue #13: 200 responses with `Content-Type: json` must still parse."""
    day = datetime(2021, 6, 1, 9, tzinfo=REFERENCE_TZ)
    mock_session = MockAsyncSession(content_type="json")
    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        data_source=cast(DataSource, "esios_public"),
    )

    api_data = await pvpc_data.async_update_all(None, day)
    assert len(api_data.sensors[KEY_PVPC]) == 24
    assert pvpc_data.process_state_and_attributes(api_data, KEY_PVPC, day)
    assert api_data.availability[KEY_PVPC]


@pytest.mark.asyncio
async def test_public_download_zip_wrapped_payload_keeps_dia_timestamps():
    """Issue #13: ZIP-wrapped payloads parse with timestamps from inner `Dia`.

    Pins the no-shift decision: the member is dated 2021-06-01 and the inner
    `Dia` field is 01/06/2021, so prices must land on 2021-06-01 exactly,
    never on `Dia` + 1 day.
    """
    day = datetime(2021, 6, 1, 9, tzinfo=REFERENCE_TZ)
    raw_payload = (TEST_EXAMPLES_PATH / _PUBLIC_FIXTURE_2021_06_01).read_bytes()
    mock_session = MockAsyncSession(content_type="application/zip")
    mock_session.responses_public[date(2021, 6, 1)] = _make_zip(
        "PVPC_CURV_DD_20210601", raw_payload
    )
    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        data_source=cast(DataSource, "esios_public"),
    )

    api_data = await pvpc_data.async_update_all(None, day)
    prices = api_data.sensors[KEY_PVPC]
    assert len(prices) == 24

    inner = load_fixture(_PUBLIC_FIXTURE_2021_06_01)
    assert inner["PVPC"][0]["Dia"] == "01/06/2021"
    ts_first = datetime(2021, 6, 1, 0, tzinfo=REFERENCE_TZ).astimezone(UTC_TZ)
    expected_first = round(
        float(inner["PVPC"][0]["PCB"].replace(",", ".")) / 1000.0, 5
    )
    assert min(prices) == ts_first
    assert max(prices) == ts_first + timedelta(hours=23)
    assert prices[ts_first] == expected_first
    assert pvpc_data.process_state_and_attributes(api_data, KEY_PVPC, day)


def test_input_validation_raises():
    """New ValueError contracts (former asserts)."""
    with pytest.raises(ValueError, match="Unknown tariff"):
        PVPCData(session=MockAsyncSession(), tariff="3.0TD")
    with pytest.raises(ValueError, match="requires an API token"):
        PVPCData(session=MockAsyncSession(), data_source="esios")
    pvpc_data = PVPCData(session=MockAsyncSession())
    with pytest.raises(ValueError, match="Unknown sensor"):
        pvpc_data.update_active_sensors("BOGUS", enabled=True)

    day = datetime(2021, 6, 1, tzinfo=REFERENCE_TZ)
    with pytest.raises(ValueError, match="Public API only supports"):
        get_daily_urls_to_download(
            cast(DataSource, "esios_public"), [KEY_PVPC, KEY_OMIE], day, day
        )
    with pytest.raises(ValueError, match="Unknown data source"):
        get_daily_urls_to_download(cast(DataSource, "bogus"), [KEY_PVPC], day, day)


@pytest.mark.parametrize(
    "payload, expected_log",
    (
        ("under maintenance", "Unexpected JSON payload type"),
        (
            {
                "PVPC": [
                    {"Dia": "not-a-date", "Hora": "00-01", "PCB": "116,33", "CYM": "116,33"}
                ]
            },
            "Malformed response",
        ),
        (
            {
                "PVPC": [
                    {"Dia": "01/06/2021", "Hora": "00-01", "PCB": "not-a-price", "CYM": "x"}
                ]
            },
            "Malformed response",
        ),
    ),
)
@pytest.mark.asyncio
async def test_malformed_public_payload_degrades(payload, expected_log, caplog):
    """Valid-JSON-wrong-shape payloads degrade to warn+None, never crash."""
    day = datetime(2021, 6, 1, 9, tzinfo=REFERENCE_TZ)
    mock_session = MockAsyncSession()
    mock_session.responses_public[date(2021, 6, 1)] = payload
    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        data_source=cast(DataSource, "esios_public"),
    )
    with caplog.at_level(logging.WARNING, logger="aiopvpc"):
        api_data = await pvpc_data.async_update_all(None, day)
    assert not api_data.sensors[KEY_PVPC]
    assert expected_log in caplog.text
    assert not pvpc_data.process_state_and_attributes(api_data, KEY_PVPC, day)


@pytest.mark.asyncio
async def test_malformed_sensor_does_not_affect_others(monkeypatch, caplog):
    """A malformed payload for one sensor must not kill the whole update."""
    start = datetime(2021, 10, 30, 15, tzinfo=UTC_TZ)
    mock_session = MockAsyncSession()
    mock_session.responses_token[ESIOS_PVPC][date(2021, 10, 30)] = "gone fishing"

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)  # skip first-load retry delay
    pvpc_data = PVPCData(
        session=mock_session,
        data_source=cast(DataSource, "esios"),
        api_token="test-token",
        sensor_keys=(KEY_PVPC, KEY_INJECTION),
    )
    with caplog.at_level(logging.WARNING, logger="aiopvpc"):
        api_data = await pvpc_data.async_update_all(None, start)

    assert len(api_data.sensors[KEY_INJECTION]) == 24
    assert api_data.availability[KEY_INJECTION]
    assert not api_data.sensors[KEY_PVPC]
    assert not api_data.availability[KEY_PVPC]
    assert "Unexpected JSON payload type" in caplog.text


@pytest.mark.asyncio
async def test_failed_refetch_keeps_cached_prices_and_last_update():
    """A failed re-download must not refresh last_update or availability."""
    day1 = datetime(2021, 6, 1, 9, tzinfo=REFERENCE_TZ)
    day2 = datetime(2021, 6, 2, 9, tzinfo=REFERENCE_TZ)
    mock_session = MockAsyncSession()
    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        data_source=cast(DataSource, "esios_public"),
    )
    api_data = await pvpc_data.async_update_all(None, day1)
    assert len(api_data.sensors[KEY_PVPC]) == 24
    assert api_data.availability[KEY_PVPC]
    first_update = api_data.last_update

    # no data published for 2021-06-02 in the mock -> failed fetch
    api_data = await pvpc_data.async_update_all(api_data, day2)
    assert api_data.last_update == first_update
    assert len(api_data.sensors[KEY_PVPC]) == 24  # cached prices kept
    assert not api_data.availability[KEY_PVPC]  # but no price for current hour


@pytest.mark.parametrize(
    "body, expected_log",
    (
        (b"<html><body>Under maintenance</body></html>", "Non-JSON payload"),
        (b"PK\x03\x04 this is not really a zipfile", "Corrupt ZIP payload"),
        (_make_zip("OTHER_FILE.txt", b"not json at all"), "Non-JSON payload"),
        # an empty ZIP archive starts with PK\x05\x06, so it is not
        # sniffed as ZIP and fails the JSON decode instead
        (_make_zip(None), "Non-JSON payload"),
    ),
)
@pytest.mark.asyncio
async def test_public_download_garbage_payload(body, expected_log, caplog):
    """Issue #13: malformed 200 payloads degrade to None + warning, no raise."""
    day = datetime(2021, 6, 1, 9, tzinfo=REFERENCE_TZ)
    mock_session = MockAsyncSession()
    mock_session.responses_public[date(2021, 6, 1)] = body
    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        data_source=cast(DataSource, "esios_public"),
    )

    with caplog.at_level(logging.WARNING, logger="aiopvpc"):
        api_data = await pvpc_data.async_update_all(None, day)
    assert not api_data.sensors[KEY_PVPC]
    assert expected_log in caplog.text
    assert not pvpc_data.process_state_and_attributes(api_data, KEY_PVPC, day)


# TODO review download schedule for Canary Islands TZ
@pytest.mark.parametrize(
    "local_tz, data_source, sensor_keys",
    (
        (TZ_TEST, "esios_public", (KEY_PVPC,)),
        (REFERENCE_TZ, "esios_public", (KEY_PVPC,)),
        (TZ_TEST, "esios", (KEY_PVPC, KEY_INJECTION, KEY_OMIE)),
        (REFERENCE_TZ, "esios", (KEY_PVPC, KEY_INJECTION, KEY_OMIE)),
    ),
)
@pytest.mark.asyncio
async def test_reduced_api_download_rate_dst_change(local_tz, data_source, sensor_keys):
    """Test time evolution and number of API calls."""
    start = datetime(2021, 10, 30, 15, tzinfo=UTC_TZ)
    mock_session = MockAsyncSession()
    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        local_timezone=local_tz,
        data_source=cast(DataSource, data_source),
        api_token="test-token" if data_source == "esios" else None,
        sensor_keys=sensor_keys,
    )
    assert pvpc_data.attribution == ATTRIBUTIONS[data_source]

    # avoid extra calls at day if already got all today prices
    api_data = None
    for _ in range(4):
        start, api_data = await run_h_step(mock_session, pvpc_data, api_data, start)
        assert mock_session.call_count == len(sensor_keys)
        check_num_datapoints(api_data, sensor_keys, 24)
    assert all(api_data.availability.values())

    # first call for next-day prices (20:20 Madrid threshold, first whole hour is 21:00)
    assert start == datetime(2021, 10, 30, 19, tzinfo=UTC_TZ)
    start, api_data = await run_h_step(mock_session, pvpc_data, api_data, start)
    assert mock_session.call_count == 2 * len(sensor_keys)
    check_num_datapoints(api_data, sensor_keys, 49)

    # avoid calls at evening if already got all today+tomorrow prices
    for _ in range(2):
        start, api_data = await run_h_step(mock_session, pvpc_data, api_data, start)
        assert mock_session.call_count == 2 * len(sensor_keys)
        check_num_datapoints(api_data, sensor_keys, 49)

    # avoid calls at day if already got all today prices
    for _ in range(21):
        start, api_data = await run_h_step(mock_session, pvpc_data, api_data, start)
        assert mock_session.call_count == 2 * len(sensor_keys)
        assert all(api_data.availability.values())
        # check_num_datapoints(api_data, sensor_keys, 25)

    # call for next-day prices (no more available)
    assert start == datetime(2021, 10, 31, 19, tzinfo=UTC_TZ)
    call_count_before = mock_session.call_count
    while start.astimezone(local_tz) <= datetime(2021, 10, 31, 23, tzinfo=local_tz):
        start, api_data = await run_h_step(mock_session, pvpc_data, api_data, start)
    assert mock_session.call_count > call_count_before

    # assert mock_session.call_count == 6
    assert pvpc_data.states.get(KEY_PVPC)
    assert all(api_data.availability.values())
    assert start.astimezone(local_tz) == datetime(2021, 11, 1, tzinfo=local_tz)
    assert not pvpc_data.process_state_and_attributes(api_data, KEY_PVPC, start)

    # After known prices are exausted, the state is flagged as unavailable
    with pytest.raises(AssertionError):
        start, api_data = await run_h_step(mock_session, pvpc_data, api_data, start)
    assert not any(api_data.availability.values())
    start += timedelta(hours=1)
    assert not pvpc_data.process_state_and_attributes(api_data, KEY_PVPC, start)


@pytest.mark.parametrize(
    "local_tz, data_source, sensor_keys",
    (
        (TZ_TEST, "esios", ALL_SENSORS),
        (REFERENCE_TZ, "esios", ALL_SENSORS),
    ),
)
@pytest.mark.asyncio
async def test_reduced_api_download_rate(local_tz, data_source, sensor_keys):
    """Test time evolution and number of API calls."""
    start = datetime(2024, 3, 9, 2, tzinfo=UTC_TZ)
    mock_session = MockAsyncSession()
    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        local_timezone=local_tz,
        data_source=cast(DataSource, data_source),
        api_token="test-token" if data_source == "esios" else None,
        sensor_keys=sensor_keys,
    )
    assert pvpc_data.attribution == ATTRIBUTIONS[data_source]

    # avoid extra calls at day if already got all today prices
    api_data = None
    for _ in range(18):
        start, api_data = await run_h_step(mock_session, pvpc_data, api_data, start)
        assert mock_session.call_count == len(sensor_keys)
        check_num_datapoints(api_data, sensor_keys, 24)

    # first call for next-day prices (20:20 Madrid threshold, first whole hour is 21:00)
    assert start == datetime(2024, 3, 9, 20, tzinfo=UTC_TZ)
    start, api_data = await run_h_step(mock_session, pvpc_data, api_data, start)
    assert mock_session.call_count == 2 * len(sensor_keys)
    check_num_datapoints(api_data, sensor_keys, 24)

    call_count = mock_session.call_count
    while start.astimezone(local_tz) <= datetime(2024, 3, 9, 23, tzinfo=local_tz):
        start, api_data = await run_h_step(mock_session, pvpc_data, api_data, start)
        call_count += len(sensor_keys)
        assert mock_session.call_count == call_count
        check_num_datapoints(api_data, sensor_keys, 24)


class _RateLimitedPVPCSession(MockAsyncSession):
    """Mock session that fails PVPC on first call, succeeds on retry."""

    def __init__(self):
        super().__init__(status=200)
        self._pvpc_attempts = 0

    def _resolve_url(self, url: str):
        prefix_token = "https://api.esios.ree.es/indicators/"
        if url.startswith(prefix_token):
            indicator = url.removeprefix(prefix_token).split("?")[0]
            if indicator == ESIOS_PVPC:
                self._pvpc_attempts += 1
                if self._pvpc_attempts == 1:
                    # Simulate rate-limit: first PVPC call times out
                    self._counter += 1
                    raise TimeoutError
        super()._resolve_url(url)


@pytest.mark.asyncio
async def test_first_load_retry_on_partial_failure(caplog):
    """Test that first load retries failed sensors after partial success.

    Simulates the scenario where config flow just verified the API token
    (fetching PVPC) and the first coordinator refresh gets rate-limited
    on the PVPC call while the INJECTION call succeeds.
    The retry logic should recover PVPC data on the same update cycle.
    """
    start = datetime(2021, 10, 30, 15, tzinfo=UTC_TZ)
    mock_session = _RateLimitedPVPCSession()
    pvpc_data = PVPCData(
        session=mock_session,
        tariff="2.0TD",
        local_timezone=REFERENCE_TZ,
        data_source=cast(DataSource, "esios"),
        api_token="test-token",
        sensor_keys=(KEY_PVPC, KEY_INJECTION),
    )

    with caplog.at_level(logging.DEBUG):
        api_data = await pvpc_data.async_update_all(None, start)

    # Both sensors should be available after retry
    assert api_data.availability.get(KEY_PVPC, False), (
        "PVPC should be available after retry"
    )
    assert api_data.availability.get(KEY_INJECTION, False), (
        "INJECTION should be available"
    )
    assert len(api_data.sensors[KEY_PVPC]) == 24
    assert len(api_data.sensors[KEY_INJECTION]) == 24

    # PVPC was called twice (first fail + retry), INJECTION once
    assert mock_session._pvpc_attempts == 2
    assert "First load: retrying" in caplog.text
