"""Tests for voice/recorder.py."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from anythink.voice.recorder import VoiceRecorder


class TestVoiceRecorderProperties:
    def test_initial_state(self) -> None:
        r = VoiceRecorder()
        assert not r.is_recording
        assert r._stream is None

    def test_custom_samplerate(self) -> None:
        r = VoiceRecorder(samplerate=8000)
        assert r._samplerate == 8000

    def test_custom_channels(self) -> None:
        r = VoiceRecorder(channels=2)
        assert r._channels == 2


class TestVoiceRecorderNoSDK:
    def test_start_raises_without_sounddevice(self) -> None:
        from anythink.exceptions import VoiceError

        r = VoiceRecorder()
        with patch.dict(sys.modules, {"sounddevice": None}):
            with pytest.raises(VoiceError, match="sounddevice"):
                r.start()

    def test_stop_raises_without_numpy_when_frames_exist(self) -> None:
        from anythink.exceptions import VoiceError

        r = VoiceRecorder()
        r._frames = [object()]  # non-empty to trigger concatenate path
        with patch.dict(sys.modules, {"numpy": None}):
            with pytest.raises(VoiceError, match="numpy"):
                r.stop()


class TestVoiceRecorderWithMockedSDK:
    def test_start_opens_stream(self) -> None:
        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        r = VoiceRecorder()
        with patch.dict(sys.modules, {"sounddevice": mock_sd}):
            r.start()

        assert r.is_recording
        mock_stream.start.assert_called_once()

    def test_stop_closes_stream(self) -> None:
        import numpy as np

        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        r = VoiceRecorder()
        with patch.dict(sys.modules, {"sounddevice": mock_sd}):
            r.start()

        assert r.is_recording
        audio = r.stop()

        assert not r.is_recording
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert r._stream is None
        # No frames were captured, so we get a zero-length array
        assert isinstance(audio, np.ndarray)
        assert audio.shape[0] == 0

    def test_stop_returns_concatenated_frames(self) -> None:
        import numpy as np

        r = VoiceRecorder()
        chunk = np.array([[0.1], [0.2]], dtype="float32")
        r._frames = [chunk, chunk]  # pre-load frames

        audio = r.stop()
        assert isinstance(audio, np.ndarray)
        assert audio.shape[0] == 4  # 2 frames × 2 samples each

    def test_callback_appends_frames_while_recording(self) -> None:
        import numpy as np

        mock_sd = MagicMock()
        captured_callback: list = []

        def mock_input_stream(samplerate, channels, dtype, callback):
            captured_callback.append(callback)
            return MagicMock()

        mock_sd.InputStream.side_effect = mock_input_stream

        r = VoiceRecorder()
        with patch.dict(sys.modules, {"sounddevice": mock_sd, "numpy": __import__("numpy")}):
            r.start()

        # Simulate callback firing during recording
        assert captured_callback
        cb = captured_callback[0]
        fake_data = np.array([[0.5]], dtype="float32")
        cb(fake_data, 1, None, None)
        assert len(r._frames) == 1

        # After stop, callback should not append
        r._recording = False
        cb(fake_data, 1, None, None)
        assert len(r._frames) == 1  # still 1, callback ignored
