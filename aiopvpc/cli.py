"""Small CLI to inspect current PVPC tariff periods."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from aiopvpc.const import REFERENCE_TZ
from aiopvpc.pvpc_tariff import (
    HolidaySource,
    get_current_and_next_power_periods,
    get_current_and_next_price_periods,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiopvpc-tariff",
        description="Print current and next PVPC tariff periods.",
    )
    parser.add_argument(
        "--source",
        choices=("csv", "python-holidays"),
        default="csv",
        help="Holiday data source (default: csv).",
    )
    parser.add_argument(
        "--timestamp",
        help=(
            "Local timestamp in ISO format. If omitted, current local time is used. "
            "If timezone is missing, --timezone is applied."
        ),
    )
    parser.add_argument(
        "--timezone",
        default=str(REFERENCE_TZ),
        help="Timezone for --timestamp and now() (default: Europe/Madrid).",
    )
    parser.add_argument(
        "--ceuta-melilla",
        action="store_true",
        help="Use Ceuta/Melilla zone instead of peninsula/balearic/canary.",
    )
    return parser


def _parse_local_timestamp(timestamp: str | None, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    if timestamp is None:
        return datetime.now(tz)

    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def main(argv: Sequence[str] | None = None) -> int:
    """Run CLI command."""
    args = _build_parser().parse_args(argv)
    holiday_source = cast(HolidaySource, args.source)
    local_ts = _parse_local_timestamp(args.timestamp, args.timezone)

    current_period, next_period, price_delta = get_current_and_next_price_periods(
        local_ts,
        zone_ceuta_melilla=args.ceuta_melilla,
        holiday_source=holiday_source,
    )
    power_period, next_power_period, power_delta = get_current_and_next_power_periods(
        local_ts,
        zone_ceuta_melilla=args.ceuta_melilla,
        holiday_source=holiday_source,
    )

    print(f"timestamp={local_ts.isoformat()}")
    print(f"source={holiday_source}")
    print(
        f"price_period={current_period} next_price_period={next_period} "
        f"hours_to_next_price_period={int(price_delta.total_seconds()) // 3600}"
    )
    print(
        f"power_period={power_period} next_power_period={next_power_period} "
        f"hours_to_next_power_period={int(power_delta.total_seconds()) // 3600}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
