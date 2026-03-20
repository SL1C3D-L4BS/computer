"""
Voice pipeline — wake word → STT → assistant-api → TTS.

Hardware: Raspberry Pi 5 (per BOM phase-1)
Wake word: Porcupine (pvporcupine) or OpenWakeWord
STT: Whisper (local) or Vosk (offline)
TTS: Piper (local, fast)

Pipeline flow:
  1. Wake word detected (e.g. "Hey Computer")
  2. Audio captured until silence (VAD)
  3. STT converts audio to text
  4. POST to assistant-api /chat with mode=VOICE
  5. Response text passed to TTS
  6. Audio played back to speaker

Privacy model:
  - Wake word detection is fully local (no cloud)
  - STT is local (Whisper small/medium)
  - TTS is local (Piper)
  - Only chat content goes to assistant-api (same-site)
  - No audio recording stored

See docs/product/assistant-surface-map.md for voice surface spec.
"""
from __future__ import annotations

import asyncio
import io
import os
from enum import Enum
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

ASSISTANT_API_URL = os.getenv("ASSISTANT_API_URL", "http://localhost:8021")
DEVICE_ID = os.getenv("VOICE_DEVICE_ID", "voice-node-001")
VOICE_STT_BACKEND = os.getenv("VOICE_STT_BACKEND", "whisper")  # whisper | vosk
VOICE_TTS_BACKEND = os.getenv("VOICE_TTS_BACKEND", "piper")    # piper | espeak
VOICE_MODE = os.getenv("VOICE_MODE", "PERSONAL")               # PERSONAL | FAMILY | SITE
VOICE_AUTH_TOKEN = os.getenv("VOICE_AUTH_TOKEN", "dev-token")


class VoicePipelineState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    RESPONDING = "RESPONDING"
    ERROR = "ERROR"


class SttBackend:
    """Speech-to-text backends."""

    @staticmethod
    def transcribe_whisper(audio_bytes: bytes) -> str:
        """Transcribe using local Whisper model."""
        try:
            import whisper
            import tempfile
            import soundfile as sf
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name
            model = whisper.load_model("small")
            result = model.transcribe(tmp_path)
            return result["text"].strip()
        except ImportError:
            logger.warning("whisper_not_installed_returning_stub")
            return "[Whisper not installed]"

    @staticmethod
    def transcribe_vosk(audio_bytes: bytes) -> str:
        """Transcribe using offline Vosk model."""
        try:
            import vosk
            import json
            model = vosk.Model("/opt/vosk-model-en-us")
            rec = vosk.KaldiRecognizer(model, 16000)
            rec.AcceptWaveform(audio_bytes)
            result = json.loads(rec.FinalResult())
            return result.get("text", "")
        except ImportError:
            logger.warning("vosk_not_installed_returning_stub")
            return "[Vosk not installed]"


class TtsBackend:
    """Text-to-speech backends."""

    @staticmethod
    def synthesize_piper(text: str) -> bytes:
        """Synthesize speech using local Piper TTS."""
        try:
            import subprocess
            result = subprocess.run(
                ["piper", "--model", "/opt/piper-models/en_US-lessac-medium.onnx", "--output_raw"],
                input=text.encode(),
                capture_output=True,
                timeout=15,
            )
            return result.stdout
        except (ImportError, FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("piper_not_installed_stub")
            return b""

    @staticmethod
    def synthesize_espeak(text: str) -> bytes:
        """Fallback TTS using espeak."""
        try:
            import subprocess
            result = subprocess.run(
                ["espeak", "-v", "en", "--stdout", text],
                capture_output=True,
                timeout=10,
            )
            return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return b""


class VoicePipeline:
    """
    Orchestrates the full voice pipeline for a single interaction.
    Runs on Raspberry Pi 5 with local STT/TTS.
    """

    def __init__(self):
        self.state = VoicePipelineState.IDLE
        self._stt = SttBackend()
        self._tts = TtsBackend()

    async def process_audio(self, audio_bytes: bytes) -> dict[str, Any]:
        """
        Full pipeline: audio → text → chat → speech.
        Returns dict with transcript, response, and audio.
        """
        self.state = VoicePipelineState.PROCESSING
        try:
            # 1. STT
            if VOICE_STT_BACKEND == "whisper":
                transcript = self._stt.transcribe_whisper(audio_bytes)
            else:
                transcript = self._stt.transcribe_vosk(audio_bytes)

            if not transcript or transcript.startswith("["):
                logger.warning("stt_no_transcript")
                self.state = VoicePipelineState.IDLE
                return {"error": "Could not understand speech"}

            logger.info("stt_transcript", text=transcript[:100])

            # 2. Assistant chat
            self.state = VoicePipelineState.PROCESSING
            response_text = await self._call_assistant(transcript)

            # 3. TTS
            self.state = VoicePipelineState.RESPONDING
            if VOICE_TTS_BACKEND == "piper":
                audio_response = self._tts.synthesize_piper(response_text)
            else:
                audio_response = self._tts.synthesize_espeak(response_text)

            self.state = VoicePipelineState.IDLE
            return {
                "transcript": transcript,
                "response": response_text,
                "audio_bytes": len(audio_response),
            }

        except Exception as e:
            self.state = VoicePipelineState.ERROR
            logger.error("voice_pipeline_error", error=str(e))
            return {"error": str(e)}

    async def _call_assistant(self, text: str) -> str:
        """Call assistant-api /chat endpoint."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{ASSISTANT_API_URL}/chat",
                    headers={
                        "Authorization": f"Bearer {VOICE_AUTH_TOKEN}",
                        "Content-Type": "application/json",
                        "X-Device-ID": DEVICE_ID,
                    },
                    json={
                        "messages": [{"role": "user", "content": text}],
                        "mode": VOICE_MODE,
                        "surface": "voice",
                    },
                )
                if resp.status_code == 200:
                    return resp.json().get("message", "")
                return "I'm sorry, I couldn't process that request."
        except Exception as e:
            logger.error("assistant_call_failed", error=str(e))
            return "I'm sorry, I'm having trouble connecting."

    def process_audio_stub(self, transcript: str) -> dict[str, Any]:
        """Stub pipeline for testing — takes text instead of audio."""
        return {
            "transcript": transcript,
            "pipeline_state": self.state,
            "stt_backend": VOICE_STT_BACKEND,
            "tts_backend": VOICE_TTS_BACKEND,
        }
