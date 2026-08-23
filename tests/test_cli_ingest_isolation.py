"""One flaky source must not take out the rest of the ingest.

A GBIF timeout aborted a full run this session, losing thirteen unrelated
sources — including the FMZ boundary layer the run had been started for. The
sources that would have succeeded were never attempted, and the run reported
only a traceback rather than what had landed.
"""

import logging

import pytest

from src.cli.main import _print_ingest_summary, _run_source


def test_a_failing_source_does_not_stop_the_others():
    results: list = []
    order: list[str] = []

    def ok(name):
        order.append(name)
        return 5

    def boom():
        order.append("boom")
        raise TimeoutError("read timed out")

    _run_source(results, "First", "fetching first…", ok, "first")
    _run_source(results, "Flaky", "fetching flaky…", boom)
    _run_source(results, "Third", "fetching third…", ok, "third")

    assert order == ["first", "boom", "third"], "sources after the failure must still run"
    assert [r.ok for r in results] == [True, False, True]


def test_the_failure_is_recorded_with_its_cause():
    results: list = []
    _run_source(results, "GBIF", "fetching…", lambda: (_ for _ in ()).throw(TimeoutError("slow")))
    failed = results[0]
    assert failed.ok is False
    assert "TimeoutError" in failed.error
    assert "slow" in failed.error


def test_a_failing_source_returns_none_rather_than_raising():
    results: list = []
    value = _run_source(results, "X", "…", lambda: 1 / 0)
    assert value is None


def test_a_successful_source_returns_its_value_through():
    results: list = []
    assert _run_source(results, "X", "…", lambda: 42) == 42
    assert _run_source(results, "Y", "…", lambda: (3, 4)) == (3, 4)
    assert results[1].detail == "3, 4", "tuple results summarise both counts"


def test_keyboard_interrupt_is_never_swallowed():
    """Ctrl-C must abort the run, not be recorded as a failed source."""
    results: list = []
    with pytest.raises(KeyboardInterrupt):
        _run_source(results, "X", "…", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert results == []


def test_failure_is_logged_at_error_level(caplog):
    results: list = []
    with caplog.at_level(logging.ERROR):
        _run_source(results, "GBIF", "…", lambda: (_ for _ in ()).throw(TimeoutError("x")))
    # LogRecord.message only exists once a Formatter has run; getMessage()
    # interpolates the args itself.
    messages = [r.getMessage() for r in caplog.records]
    assert any("GBIF failed" in m and "TimeoutError" in m for m in messages), messages


def test_summary_names_the_failed_sources(capsys):
    results: list = []
    _run_source(results, "Good", "…", lambda: 1)
    _run_source(results, "Bad", "…", lambda: (_ for _ in ()).throw(ValueError("nope")))
    capsys.readouterr()

    _print_ingest_summary(results)
    out = capsys.readouterr().out
    assert "Bad" in out
    assert "1 of 2 sources failed" in out


def test_summary_says_so_when_everything_worked(capsys):
    results: list = []
    _run_source(results, "Good", "…", lambda: 1)
    capsys.readouterr()

    _print_ingest_summary(results)
    assert "All 1 sources succeeded" in capsys.readouterr().out
