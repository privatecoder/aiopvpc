"""Tests for aiopvpc CLI."""

from datetime import timedelta

from aiopvpc.cli import main


def test_cli_default_source_csv(monkeypatch, capsys):
    called: dict[str, str] = {}

    def _fake_price(*_args, **kwargs):
        called["price_source"] = kwargs["holiday_source"]
        return "P1", "P2", timedelta(hours=1)

    def _fake_power(*_args, **kwargs):
        called["power_source"] = kwargs["holiday_source"]
        return "P1", "P3", timedelta(hours=2)

    monkeypatch.setattr("aiopvpc.cli.get_current_and_next_price_periods", _fake_price)
    monkeypatch.setattr("aiopvpc.cli.get_current_and_next_power_periods", _fake_power)

    code = main(["--timestamp", "2026-02-03T12:00:00+01:00"])

    assert code == 0
    assert called["price_source"] == "csv"
    assert called["power_source"] == "csv"
    assert "source=csv" in capsys.readouterr().out


def test_cli_explicit_python_holidays(monkeypatch, capsys):
    called: dict[str, str] = {}

    def _fake_price(*_args, **kwargs):
        called["price_source"] = kwargs["holiday_source"]
        return "P2", "P3", timedelta(hours=3)

    def _fake_power(*_args, **kwargs):
        called["power_source"] = kwargs["holiday_source"]
        return "P1", "P3", timedelta(hours=4)

    monkeypatch.setattr("aiopvpc.cli.get_current_and_next_price_periods", _fake_price)
    monkeypatch.setattr("aiopvpc.cli.get_current_and_next_power_periods", _fake_power)

    code = main(["--source", "python-holidays", "--timestamp", "2026-02-03T12:00:00"])

    assert code == 0
    assert called["price_source"] == "python-holidays"
    assert called["power_source"] == "python-holidays"
    assert "source=python-holidays" in capsys.readouterr().out
