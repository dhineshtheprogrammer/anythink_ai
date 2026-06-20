"""Tests for notify/backends.py."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from anythink.notify.backends import (
    LinuxBackend,
    MacOSBackend,
    NullBackend,
    WindowsBackend,
    detect_backend,
)


class TestNullBackend:
    def test_always_available(self) -> None:
        assert NullBackend().is_available()

    def test_send_is_silent(self) -> None:
        NullBackend().send("title", "msg")  # must not raise


class TestWindowsBackend:
    def test_available_on_win32(self) -> None:
        with patch("anythink.notify.backends.sys") as mock_sys:
            mock_sys.platform = "win32"
            assert WindowsBackend().is_available()

    def test_unavailable_on_linux(self) -> None:
        with patch("anythink.notify.backends.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert not WindowsBackend().is_available()

    def test_send_calls_powershell(self) -> None:
        mock_subprocess = MagicMock()
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        with (
            patch("anythink.notify.backends.sys") as mock_sys,
            patch.dict(sys.modules, {"subprocess": mock_subprocess}),
        ):
            mock_sys.platform = "win32"
            b = WindowsBackend()
            # Import subprocess is done inside send(), so patch it there
            with patch("subprocess.run") as mock_run:
                b.send("Test Title", "Test message")
                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                assert args[0] == "powershell"

    def test_send_escapes_single_quotes(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            b = WindowsBackend()
            b.send("It's a title", "It's a message")
            call_args = mock_run.call_args[0][0]
            # The PS script should have '' escaped single quotes
            script = call_args[-1]
            assert "It''s" in script


class TestMacOSBackend:
    def test_available_on_darwin_with_osascript(self) -> None:
        with (
            patch("anythink.notify.backends.sys") as mock_sys,
            patch("anythink.notify.backends.shutil.which", return_value="/usr/bin/osascript"),
        ):
            mock_sys.platform = "darwin"
            assert MacOSBackend().is_available()

    def test_unavailable_without_osascript(self) -> None:
        with (
            patch("anythink.notify.backends.sys") as mock_sys,
            patch("anythink.notify.backends.shutil.which", return_value=None),
        ):
            mock_sys.platform = "darwin"
            assert not MacOSBackend().is_available()

    def test_send_calls_osascript(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            b = MacOSBackend()
            b.send("Title", "Message")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "osascript"
            # Script should include title and message
            assert "Title" in args[-1]
            assert "Message" in args[-1]


class TestLinuxBackend:
    def test_available_on_linux_with_notify_send(self) -> None:
        with (
            patch("anythink.notify.backends.sys") as mock_sys,
            patch("anythink.notify.backends.shutil.which", return_value="/usr/bin/notify-send"),
        ):
            mock_sys.platform = "linux"
            assert LinuxBackend().is_available()

    def test_unavailable_without_notify_send(self) -> None:
        with (
            patch("anythink.notify.backends.sys") as mock_sys,
            patch("anythink.notify.backends.shutil.which", return_value=None),
        ):
            mock_sys.platform = "linux"
            assert not LinuxBackend().is_available()

    def test_send_calls_notify_send(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            b = LinuxBackend()
            b.send("My Title", "My Message")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "notify-send" in args[0]
            assert "My Title" in args
            assert "My Message" in args


class TestDetectBackend:
    def test_returns_null_when_nothing_available(self) -> None:
        with (
            patch("anythink.notify.backends.WindowsBackend.is_available", return_value=False),
            patch("anythink.notify.backends.MacOSBackend.is_available", return_value=False),
            patch("anythink.notify.backends.LinuxBackend.is_available", return_value=False),
        ):
            backend = detect_backend()
            assert isinstance(backend, NullBackend)

    def test_returns_first_available(self) -> None:
        with patch("anythink.notify.backends.WindowsBackend.is_available", return_value=True):
            backend = detect_backend()
            assert isinstance(backend, WindowsBackend)
