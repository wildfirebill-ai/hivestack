"""Media — image generation (diffusers/torch, M40-friendly fp32) and OCR
(pytesseract). Backends are optional; endpoints fail cleanly with an explicit
message when the backend isn't installed (verified path is the graceful 501)."""

from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path

from ..config import settings

_pipeline = None
_pipeline_lock = None


class MediaUnavailable(Exception):
    pass


def media_dir() -> Path:
    p = settings.data_dir / "media"
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_media() -> list[dict]:
    out = []
    for f in sorted(media_dir().glob("*.png")):
        out.append({"name": f.name, "bytes": f.stat().st_size})
    return out


def generate(prompt: str, width: int = 512, height: int = 512, steps: int = 20, seed: int | None = None) -> dict:
    global _pipeline, _pipeline_lock
    try:
        import torch  # noqa: F401
        from diffusers import AutoPipelineForText2Image
    except ImportError as exc:
        raise MediaUnavailable(
            "image generation requires 'torch' + 'diffusers' (optional deps not installed). "
            "Install them in the container to enable local fp32 Stable Diffusion on the M40."
        ) from exc

    if _pipeline_lock is None:
        import threading

        _pipeline_lock = threading.Lock()
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = AutoPipelineForText2Image.from_pretrained(
                    "runwayml/stable-diffusion-v1-5", torch_dtype=torch.float32
                )
                if torch.cuda.is_available():
                    _pipeline = _pipeline.to("cuda")
    gen = __import__("torch").Generator("cpu").manual_seed(seed if seed is not None else 0)
    img = _pipeline(prompt, width=int(width), height=int(height), num_inference_steps=int(steps), generator=gen).images[0]
    path = media_dir() / f"{uuid.uuid4().hex[:10]}.png"
    img.save(path)
    return {"name": path.name, "path": str(path.relative_to(settings.data_dir)), "bytes": path.stat().st_size}


def ocr(image_bytes: bytes) -> dict:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise MediaUnavailable(
            "OCR requires 'pytesseract' (Python) + the Tesseract binary (tesseract-ocr). Not installed."
        ) from exc
    img = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(img)
    return {"text": text.strip(), "chars": len(text.strip())}


def decode_b64(data: str) -> bytes:
    return base64.b64decode(data)