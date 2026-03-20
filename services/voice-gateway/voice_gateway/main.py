"""
Voice Gateway Service

Local voice pipeline for Computer assistant.
Runs on Raspberry Pi 5 (or any Linux with audio).

Endpoints:
  POST /voice/process  — Accept audio bytes, return transcription and response
  POST /voice/text     — Text-only mode (for testing)
  GET  /health
  WS   /voice/stream   — WebSocket streaming voice session

Integration:
  - Calls assistant-api /chat with mode=VOICE
  - Fully local: Porcupine wake word, Whisper STT, Piper TTS
  - No audio data leaves the site
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .pipeline import VoicePipeline, VoicePipelineState

logger = structlog.get_logger(__name__)

DEVICE_ID = os.getenv("VOICE_DEVICE_ID", "voice-node-001")

_pipeline = VoicePipeline()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("voice_gateway_starting", device_id=DEVICE_ID)
    yield
    logger.info("voice_gateway_stopped")


app = FastAPI(
    title="Voice Gateway",
    description="Local voice pipeline — wake word, STT, TTS, assistant routing",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "service": "voice-gateway",
        "version": "0.1.0",
        "device_id": DEVICE_ID,
        "pipeline_state": _pipeline.state,
    }


class TextInput(BaseModel):
    text: str
    mode: str = "PERSONAL"


@app.post("/voice/text", tags=["voice"])
async def process_text(payload: TextInput) -> dict[str, Any]:
    """Text-only pipeline for testing and family-web integration."""
    if _pipeline.state != VoicePipelineState.IDLE:
        raise HTTPException(status_code=409, detail="Pipeline busy")

    result = _pipeline.process_audio_stub(payload.text)
    # Also call assistant-api
    response = await _pipeline._call_assistant(payload.text)
    return {
        "transcript": payload.text,
        "response": response,
        "pipeline_state": _pipeline.state,
        "surface": "voice",
    }


@app.post("/voice/process", tags=["voice"])
async def process_audio(audio: UploadFile = File(...)) -> dict[str, Any]:
    """Process audio file through full STT → chat → TTS pipeline."""
    if _pipeline.state != VoicePipelineState.IDLE:
        raise HTTPException(status_code=409, detail="Pipeline busy")

    audio_bytes = await audio.read()
    result = await _pipeline.process_audio(audio_bytes)

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return result


@app.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket):
    """
    WebSocket voice streaming session.
    Accepts audio chunks, streams text back to client.
    """
    await websocket.accept()
    logger.info("voice_ws_connected")
    try:
        while True:
            data = await websocket.receive_bytes()
            if data == b"PING":
                await websocket.send_text("PONG")
                continue
            result = await _pipeline.process_audio(data)
            await websocket.send_json(result)
    except Exception as e:
        logger.info("voice_ws_disconnected", reason=str(e))
    finally:
        await websocket.close()
