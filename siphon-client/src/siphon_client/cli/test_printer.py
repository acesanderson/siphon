"""Tests for the Printer utility class."""
from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import patch

import pytest

from siphon_client.cli.printer import Printer


def test_printer_in_tty_mode_has_ui_enabled() -> None:
    """Printer should enable UI when in TTY mode without raw flag."""
    with patch("siphon_client.cli.printer.IS_TTY", True):
        printer = Printer()
        assert printer.emit_ui is True
        assert printer.emit_data is False
        assert printer.ui is not None


def test_printer_in_piped_mode_has_data_enabled() -> None:
    """Printer should enable data output when stdout is piped."""
    with patch("siphon_client.cli.printer.IS_TTY", False):
        printer = Printer()
        assert printer.emit_ui is False
        assert printer.emit_data is True
        assert printer.ui is None


def test_printer_with_raw_flag_forces_data_mode() -> None:
    """Printer should force data output when raw=True regardless of TTY."""
    with patch("siphon_client.cli.printer.IS_TTY", True):
        printer = Printer(raw=True)
        assert printer.emit_ui is False
        assert printer.emit_data is True
        assert printer.ui is None


def test_print_raw_writes_to_stdout_when_piped() -> None:
    """print_raw should write to stdout when in piped mode."""
    fake_stdout = StringIO()
    with patch("siphon_client.cli.printer.IS_TTY", False):
        with patch("sys.stdout", fake_stdout):
            printer = Printer()
            printer.print_raw("test output")

    assert fake_stdout.getvalue() == "test output\n"


def test_print_raw_does_not_write_in_tty_mode_without_raw() -> None:
    """print_raw should not write to stdout in TTY mode without raw flag."""
    fake_stdout = StringIO()
    with patch("siphon_client.cli.printer.IS_TTY", True):
        with patch("sys.stdout", fake_stdout):
            printer = Printer()
            printer.print_raw("test output")

    assert fake_stdout.getvalue() == ""


def test_print_raw_writes_in_tty_mode_with_raw_flag() -> None:
    """print_raw should write to stdout when raw=True even in TTY mode."""
    fake_stdout = StringIO()
    with patch("siphon_client.cli.printer.IS_TTY", True):
        with patch("sys.stdout", fake_stdout):
            printer = Printer(raw=True)
            printer.print_raw("test output")

    assert fake_stdout.getvalue() == "test output\n"


def test_print_raw_adds_newline_when_missing() -> None:
    """print_raw should add newline if string doesn't end with one."""
    fake_stdout = StringIO()
    with patch("siphon_client.cli.printer.IS_TTY", False):
        with patch("sys.stdout", fake_stdout):
            printer = Printer()
            printer.print_raw("no newline")

    assert fake_stdout.getvalue() == "no newline\n"


def test_print_raw_preserves_existing_newline() -> None:
    """print_raw should not add extra newline if already present."""
    fake_stdout = StringIO()
    with patch("siphon_client.cli.printer.IS_TTY", False):
        with patch("sys.stdout", fake_stdout):
            printer = Printer()
            printer.print_raw("has newline\n")

    assert fake_stdout.getvalue() == "has newline\n"


def test_print_raw_handles_empty_string() -> None:
    """print_raw should handle empty strings without adding newline."""
    fake_stdout = StringIO()
    with patch("siphon_client.cli.printer.IS_TTY", False):
        with patch("sys.stdout", fake_stdout):
            printer = Printer()
            printer.print_raw("")

    # Empty string doesn't get a newline per the implementation logic
    assert fake_stdout.getvalue() == ""


def test_print_pretty_writes_to_stderr_in_tty_mode() -> None:
    """print_pretty should write to stderr via Rich Console in TTY mode."""
    fake_stderr = StringIO()
    with patch("siphon_client.cli.printer.IS_TTY", True):
        with patch("sys.stderr", fake_stderr):
            printer = Printer()
            printer.print_pretty("hello world")

    # Rich will add ANSI codes, just verify something was written
    output = fake_stderr.getvalue()
    assert "hello world" in output


def test_print_pretty_does_nothing_when_piped() -> None:
    """print_pretty should not write anything when in piped mode."""
    fake_stderr = StringIO()
    with patch("siphon_client.cli.printer.IS_TTY", False):
        with patch("sys.stderr", fake_stderr):
            printer = Printer()
            printer.print_pretty("hello world")

    assert fake_stderr.getvalue() == ""


def test_set_raw_updates_emit_flags() -> None:
    """set_raw should update emit_data and emit_ui flags."""
    with patch("siphon_client.cli.printer.IS_TTY", True):
        printer = Printer()
        assert printer.emit_ui is True
        assert printer.emit_data is False

        printer.set_raw(True)
        assert printer.emit_ui is False
        assert printer.emit_data is True

        printer.set_raw(False)
        assert printer.emit_ui is True
        assert printer.emit_data is False


def test_status_returns_context_manager_in_tty_mode() -> None:
    """status should return a Rich status context manager in TTY mode."""
    with patch("siphon_client.cli.printer.IS_TTY", True):
        printer = Printer()
        ctx = printer.status("Processing...")
        assert ctx is not None
        # Should be able to use as context manager
        with ctx:
            pass


def test_status_returns_nullcontext_when_piped() -> None:
    """status should return a nullcontext when in piped mode."""
    from contextlib import nullcontext

    with patch("siphon_client.cli.printer.IS_TTY", False):
        printer = Printer()
        ctx = printer.status("Processing...")
        # Should be a nullcontext (no-op)
        assert isinstance(ctx, type(nullcontext()))
