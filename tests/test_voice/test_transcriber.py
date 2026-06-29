"""Tests for voice/transcriber.py."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from anythink.voice.transcriber import VALID_MODELS, VoiceTranscriber


class TestVoiceTranscriberInit:
    def test_valid_model_stored(self) -> None:
        t = VoiceTranscriber(model_name="small")
        assert t.model_name == "small"

    def test_invalid_model_falls_back_to_base(self) -> None:
        t = VoiceTranscriber(model_name="giant")
        assert t.model_name == "base"

    def test_valid_models_set(self) -> None:
        assert "tiny" in VALID_MODELS
        assert "base" in VALID_MODELS
        assert "large" in VALID_MODELS
        assert "turbo" in VALID_MODELS

    def test_language_stored(self) -> None:
        t = VoiceTranscriber(language="en")
        assert t._language == "en"

    def test_model_not_loaded_at_init(self) -> None:
        t = VoiceTranscriber()
        assert t._model is None


class TestVoiceTranscriberNoSDK:
    def test_transcribe_raises_without_whisper(self) -> None:
        import numpy as np

        from anythink.exceptions import VoiceError

        t = VoiceTranscriber()
        audio = np.zeros(1000, dtype="float32")

        with patch.dict(sys.modules, {"whisper": None}):
            with pytest.raises(VoiceError, match="openai-whisper"):
                t.transcribe(audio)


class TestVoiceTranscriberWithMockedWhisper:
    def test_transcribe_happy_path(self) -> None:
        import numpy as np

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "  hello world  "}

        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model

        t = VoiceTranscriber(model_name="base")

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            audio = np.zeros(16000, dtype="float32")
            result = t.transcribe(audio)

        assert result == "hello world"
        mock_whisper.load_model.assert_called_once_with("base")
        mock_model.transcribe.assert_called_once()

    def test_transcribe_with_language(self) -> None:
        import numpy as np

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "hola"}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model

        t = VoiceTranscriber(model_name="base", language="es")

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            audio = np.zeros(16000, dtype="float32")
            result = t.transcribe(audio)

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs.get("language") == "es"
        assert result == "hola"

    def test_transcribe_stereo_converted_to_mono(self) -> None:
        import numpy as np

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "test"}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model

        t = VoiceTranscriber()

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            stereo = np.zeros((16000, 2), dtype="float32")
            t.transcribe(stereo)

        # The array passed to transcribe should be 1-D (mono)
        actual_audio = mock_model.transcribe.call_args[0][0]
        assert actual_audio.ndim == 1

    def test_transcribe_empty_audio_returns_empty(self) -> None:
        import numpy as np

        t = VoiceTranscriber()
        audio = np.zeros(0, dtype="float32")

        mock_whisper = MagicMock()
        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            result = t.transcribe(audio)

        assert result == ""
        # whisper.load_model not called for empty audio
        mock_whisper.load_model.assert_not_called()

    def test_model_cached_after_first_call(self) -> None:
        import numpy as np

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "hi"}
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model

        t = VoiceTranscriber()
        audio = np.zeros(100, dtype="float32")

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            t.transcribe(audio)
            t.transcribe(audio)

        # load_model called only once (model is cached)
        assert mock_whisper.load_model.call_count == 1


class TestTranscriberNumpyImportError:
    def test_transcribe_raises_voice_error_without_numpy(self) -> None:
        from anythink.exceptions import VoiceError

        t = VoiceTranscriber()
        with patch.dict(sys.modules, {"numpy": None}):
            with pytest.raises(VoiceError, match="numpy"):
                t.transcribe([0.0, 0.0])
