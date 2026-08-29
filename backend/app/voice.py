"""Voice stack — STT (faster-whisper), TTS (piper), wake-word activation.
Backends are optional: endpoints fail cleanly (501) when missing, and the
activate loop accepts a text transcript fallback so the full
hotword → understand → reply cycle is verifiable offline."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from .config import settings


class VoiceUnavailable(Exception):
    pass


def audio_dir() -> Path:
    p = settings.data_dir / "audio"
    p.mkdir(parents=True, exist_ok=True)
    return p


def hotword(transcript: str, phrase: str = "hivestack") -> bool:
    t = re.sub(r"[^a-zA-Z0-9 ]", "", (transcript or "").lower()).strip()
    words = t.split()
    if not words:
        return False
    first = words[0]
    if first == phrase.lower():
        return True
    if first in ("hey", "ok", "hello", "hi") and len(words) > 1 and words[1] == phrase.lower():
        return True
    return t.startswith(phrase.lower() + " ") or t.startswith(phrase.lower() + "?")


def transcribe(audio_bytes: bytes) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise VoiceUnavailable(
            "STT requires 'faster-whisper' (optional dep) + a model pull. Not installed."
        ) from exc
    path = audio_dir() / f"{uuid.uuid4().hex}.wav"
    path.write_bytes(audio_bytes)
    model = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=str(settings.models_dir / "whisper"))
    segments, info = model.transcribe(str(path))
    text = " ".join(seg.text.strip() for seg in segments)
    return {"text": text, "language": info.language}


def speak(text: str) -> dict:
    try:
        from piper import PiperVoice  # type: ignore
    except ImportError as exc:
        raise VoiceUnavailable(
            "TTS requires 'piper-tts' (optional dep) + a voice model. Not installed."
        ) from exc
    model = settings.models_dir / "piper" / "en_US-lessac-medium.onnx"
    if not model.exists():
        raise VoiceUnavailable("piper voice model missing — place onnx(+json) under models/piper")
    voice = PiperVoice.load(str(model))
    path = audio_dir() / f"{uuid.uuid4().hex}.wav"
    with open(path, "wb") as f:
        voice.synthesize(text, f)
    return {"wav_path": str(path.relative_to(settings.data_dir)), "bytes": path.stat().st_size}


def activate(transcript: str | None, audio_bytes: bytes | None = None) -> dict:
    """hotword → understand → reply. For verification without STT models,
    pass `transcript` (already transcribed text) and it runs the same loop."""
    used_stt = False
    if transcript is None:
        if audio_bytes is None:
            raise ValueError("provide transcript or audio")
        used_stt = True
        result = transcribe(audio_bytes)
        transcript = result["text"]
    transcript = (transcript or "").strip()
    if not transcript:
        return {"activated": False, "transcript": "", "reply": ""}
    activated = hotword(transcript)
    if not activated:
        return {"activated": False, "transcript": transcript, "reply": "(no wake word)"}
    query = re.sub(r"^\s*(hivestack|hey\s+hivestack|ok\s+hivestack)[,!\s]*", "", transcript, flags=re.I)
    from .channels.base import reply_to

    res = reply_to(query or transcript, from_id="voice")
    return {"activated": True, "transcript": transcript, "query": query or transcript,
            "reply": res["reply"], "source": res["source"], "stt": used_stt}