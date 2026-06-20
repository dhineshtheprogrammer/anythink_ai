"""Voice recorder: non-blocking mic capture via sounddevice.

Requires ``pip install anythink[voice]`` (sounddevice + numpy).
"""

from __future__ import annotations

from typing import Any

from anythink.exceptions import VoiceError

_SAMPLERATE = 16_000  # Hz — Whisper expects 16 kHz
_CHANNELS = 1
_DTYPE = "float32"


class VoiceRecorder:
    """Captures microphone audio into a float32 NumPy array.

    Call ``start()`` to begin capturing (non-blocking; uses a sounddevice
    callback thread).  Call ``stop()`` to flush and retrieve the array.
    ``stop()`` is blocking but typically returns in milliseconds.
    """

    def __init__(
        self,
        samplerate: int = _SAMPLERATE,
        channels: int = _CHANNELS,
    ) -> None:
        self._samplerate = samplerate
        self._channels = channels
        self._frames: list[Any] = []
        self._recording = False
        self._stream: Any = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        """Open the InputStream and begin buffering audio frames."""
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise VoiceError(
                "sounddevice not installed",
                user_message="Voice capture requires: pip install anythink[voice]",
            ) from exc

        self._frames = []
        self._recording = True

        def _callback(indata: Any, frames: int, time: Any, status: Any) -> None:
            if self._recording:
                import numpy as np

                self._frames.append(np.array(indata))

        self._stream = sd.InputStream(
            samplerate=self._samplerate,
            channels=self._channels,
            dtype=_DTYPE,
            callback=_callback,
        )
        self._stream.start()

    def stop(self) -> Any:
        """Stop the stream and return the concatenated audio array.

        Returns a float32 NumPy array shaped ``(N, channels)``.
        If no frames were captured, returns a zero-length array.
        """
        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        try:
            import numpy as np
        except ImportError as exc:
            raise VoiceError(
                "numpy not installed",
                user_message="Voice capture requires: pip install anythink[voice]",
            ) from exc

        if not self._frames:
            return np.zeros((0, self._channels), dtype=_DTYPE)
        return np.concatenate(self._frames, axis=0)
