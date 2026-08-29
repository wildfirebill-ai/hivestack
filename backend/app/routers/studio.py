"""Studio endpoints — documents, analytics, media, publishing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from .. import security
from ..config import settings
from ..studio import analytics, docs, media, publish

router = APIRouter(prefix="/api", tags=["studio"])
_auth = Depends(security.require_token)


def _require(name: str) -> None:
    if not settings.module_enabled(name):
        raise HTTPException(status_code=403, detail=f"{name} module is disabled")


# ------------------------------------------------------------------ docs
class WordIn(BaseModel):
    title: str
    name: str | None = None
    sections: list[dict] = []
    table_rows: list[list] | None = None
    merge_data: dict | None = None


class SheetIn(BaseModel):
    name: str
    rows: list[list] = []
    width: int = 16


class WorkbookIn(BaseModel):
    sheets: list[SheetIn]


class SlidesIn(BaseModel):
    title: str
    name: str | None = None
    slides: list[dict] = []


class DiffIn(BaseModel):
    a: str
    b: str


class GenerateIn(BaseModel):
    prompt: str
    width: int = 512
    height: int = 512
    steps: int = 20
    seed: int | None = None


class OcrIn(BaseModel):
    image_b64: str


class LogsIn(BaseModel):
    lines: list[str]


class AnalyzeIn(BaseModel):
    content: str
    name: str = "data"


class AnomalySeriesIn(BaseModel):
    name: str
    points: list[float]


class AnomalyIn(BaseModel):
    series: list[AnomalySeriesIn]
    method: str = "hybrid"


@router.post("/docs/word")
def word_doc(body: WordIn, _: str = _auth) -> dict:
    _require("docs")
    try:
        return docs.build_word(body.title, body.sections, body.table_rows, body.merge_data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"word build failed: {exc}") from None


@router.post("/docs/spreadsheet")
def spreadsheet(base: WorkbookIn, _: str = _auth) -> dict:
    _require("docs")
    try:
        return docs.build_spreadsheet([s.model_dump() for s in base.sheets])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"spreadsheet build failed: {exc}") from None


@router.post("/docs/slides")
def slides(base: SlidesIn, _: str = _auth) -> dict:
    _require("docs")
    try:
        return docs.build_slides(base.title, base.slides)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"slides build failed: {exc}") from None


@router.get("/docs")
def list_docs(_: str = _auth) -> dict:
    return {"documents": docs.list_docs()}


@router.get("/docs/{doc_id}/preview")
def preview(doc_id: str, _: str = _auth) -> dict:
    d = docs.get_doc(doc_id)
    if d is None:
        raise HTTPException(status_code=404, detail="document not found")
    return docs.preview(docs._path(d["path"]))


@router.get("/docs/{doc_id}/audit")
def audit(doc_id: str, _: str = _auth) -> dict:
    d = docs.get_doc(doc_id)
    if d is None:
        raise HTTPException(status_code=404, detail="document not found")
    return docs.audit(docs._path(d["path"]))


@router.post("/docs/diff")
def diff_docs(body: DiffIn, _: str = _auth) -> dict:
    a, b = docs.get_doc(body.a), docs.get_doc(body.b)
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="document not found")
    return docs.diff(docs._path(a["path"]), docs._path(b["path"]))


# ------------------------------------------------------------------ analytics
@router.post("/data/analyze")
def analyze(body: AnalyzeIn, _: str = _auth) -> dict:
    _require("docs")
    return analytics.analyze(body.content, body.name)


@router.post("/data/logs/normalize")
def normalize(body: LogsIn, _: str = _auth) -> dict:
    _require("docs")
    return analytics.normalize_logs(body.lines)


@router.post("/data/anomalies")
def anomalies(base: AnomalyIn, _: str = _auth) -> dict:
    _require("docs")
    series = {s.name: s.points for s in base.series}
    return analytics.anomalies(series, base.method)


# ------------------------------------------------------------------ media
@router.post("/media/generate")
def generate(body: GenerateIn, _: str = _auth) -> dict:
    _require("media")
    try:
        return media.generate(body.prompt, body.width, body.height, body.steps, body.seed)
    except media.MediaUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from None


@router.get("/media")
def list_media(_: str = _auth) -> dict:
    return {"media": media.list_media()}


@router.post("/media/ocr")
def ocr(body: OcrIn, _: str = _auth) -> dict:
    _require("media")
    try:
        return media.ocr(media.decode_b64(body.image_b64))
    except media.MediaUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from None


# ------------------------------------------------------------------ publishing
class PublishIn(BaseModel):
    title: str
    body: str = ""
    targets: list[str] | None = None


@router.post("/publish/jobs")
def publish_job(body: PublishIn, _: str = _auth) -> dict:
    _require("docs")
    return {"job": publish.create_job(body.title, body.body, body.targets)}


@router.get("/publish/jobs")
def publish_jobs(_: str = _auth) -> dict:
    return {"jobs": publish.list_jobs()}


class DecideIn(BaseModel):
    approve: bool


@router.post("/publish/jobs/{job_id}/approve")
def approve_job(job_id: str, body: DecideIn, user: str = _auth) -> dict:
    try:
        result = publish.decide(job_id, body.approve)
        from .. import governance

        governance.audit(user, "publish.approve", job_id, {"approve": body.approve})
        return {"job": result}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/publish/jobs/{job_id}/execute")
def execute_job(job_id: str, user: str = _auth) -> dict:
    try:
        result = publish.execute(job_id)
        from .. import governance

        governance.audit(user, "publish.execute", job_id, {"path": result.get("path")})
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None