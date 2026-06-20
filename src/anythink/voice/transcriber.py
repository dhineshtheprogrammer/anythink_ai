"""Voice transcriber: local OpenAI-Whisper speech-to-text.

Requires ``pip install anythink[voice]`` (openai-whisper).
The Whisper model is downloaded automatically on first use and cached by the
Whisper library; model size is controlled by ``AppConfig.voice_model``.
"""

from __future__ import annotations

from typing import Any

from anythink.exceptions import VoiceError

VALID_MODELS = frozenset({"tiny", "base", "small", "medium", "large", "turbo"})


class VoiceTranscriber:
    """Wraps OpenAI Whisper to transcribe a NumPy audio array to text.

    The model is lazily loaded on the first ``transcribe()`` call.
    Changing ``model_name`` after construction resets the cached model.
    """

    def __init__(
        self,
        model_name: str = "base",
        language: str | None = None,
    ) -> None:
        if model_name not in VALID_MODELS:
            model_name = "base"
        self._model_name = model_name
        self._language = language
        self._model: Any = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            import whisper
        except ImportError as exc:
            raise VoiceError(
                "openai-whisper not installed",
                user_message=(
                    "Voice transcription requires: pip install anythink[voice]\n"
                    "The first run will download the selected Whisper model."
                ),
            ) from exc
        self._model = whisper.load_model(self._model_name)

    def transcribe(self, audio: Any) -> str:
        """Transcribe *audio* (float32 NumPy array, 16 kHz) to plain text.

        Returns an empty string if the audio is silent or too short.
        """
        try:
            import numpy as np
        except ImportError as exc:
            raise VoiceError(
                "numpy not installed",
                user_message="Voice requires: pip install anythink[voice]",
            ) from exc

        arr = np.asarray(audio, dtype=np.float32)

        # Whisper expects mono; average channels if stereo
        if arr.ndim > 1:
            arr = arr.mean(axis=1)

        if arr.size == 0:
            return ""

        self._load_model()

        kwargs: dict[str, str] = {}
        if self._language:
            kwargs["language"] = self._language

        result: dict[str, Any] = self._model.transcribe(arr, **kwargs)
        text = result.get("text", "")
        return str(text).strip()
