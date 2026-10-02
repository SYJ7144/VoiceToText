from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import jobs
from .auth import auth_status, current_user, router as auth_router
from .db import get_session, init_db
from .export import EXPORTERS
from .models import Transcript
from .transcriber import LANGUAGES, MODELS, Segment

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="VoiceToText")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "dev-secret-change-me"),
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.include_router(auth_router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"models": MODELS, "languages": list(LANGUAGES)},
    )


@app.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    return templates.TemplateResponse(request, "history.html", {})


@app.get("/api/me")
def api_me(request: Request):
    user = current_user(request)
    return {"logged_in": user is not None, "user": user, "auth": auth_status()}


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    model: str = Form("small"),
    language: str = Form("auto"),
):
    if model not in MODELS:
        raise HTTPException(400, "지원하지 않는 모델입니다.")
    if language not in LANGUAGES:
        raise HTTPException(400, "지원하지 않는 언어입니다.")

    ext = Path(file.filename or "audio").suffix or ".bin"
    dest = jobs.UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    job = jobs.create_job(dest, file.filename or dest.name, model, LANGUAGES[language])
    return {"job_id": job.id}


def _job_payload(job: jobs.Job) -> dict:
    payload = {
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "filename": job.filename,
    }
    if job.status == "done" and job.result:
        payload["result"] = {
            "text": job.result.text,
            "segments": jobs.segments_to_dicts(job.result.segments),
            "detected_language": job.result.detected_language,
        }
    if job.status == "error":
        payload["error"] = job.error
    return payload


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "존재하지 않거나 만료된 작업입니다.")
    return _job_payload(job)


@app.get("/api/jobs/{job_id}/export")
def export_job(job_id: str, fmt: str = "txt"):
    job = jobs.get_job(job_id)
    if job is None or job.status != "done" or job.result is None:
        raise HTTPException(404, "완료된 작업을 찾을 수 없습니다.")
    return _export_response(job.result.segments, Path(job.filename).stem, fmt)


def _export_response(segments: list[Segment], stem: str, fmt: str) -> PlainTextResponse:
    exporter = EXPORTERS.get(fmt)
    if exporter is None:
        raise HTTPException(400, "지원하지 않는 형식입니다 (txt, srt, vtt).")
    render, media_type = exporter
    content = render(segments)
    headers = {"Content-Disposition": f'attachment; filename="{stem}.{fmt}"'}
    return PlainTextResponse(content, media_type=media_type, headers=headers)


@app.post("/api/jobs/{job_id}/save")
def save_job(job_id: str, request: Request):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "히스토리 저장은 로그인이 필요합니다.")
    job = jobs.get_job(job_id)
    if job is None or job.status != "done" or job.result is None:
        raise HTTPException(404, "완료된 작업을 찾을 수 없습니다.")

    db = get_session()
    try:
        language_label = next(
            (k for k, v in LANGUAGES.items() if v == job.language), "auto"
        )
        record = Transcript(
            user_id=user["id"],
            filename=job.filename,
            model=job.model,
            language=language_label,
            text=job.result.text,
            segments_json=json.dumps(jobs.segments_to_dicts(job.result.segments)),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"id": record.id}
    finally:
        db.close()


@app.get("/api/history")
def list_history(request: Request):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    db = get_session()
    try:
        records = (
            db.query(Transcript)
            .filter_by(user_id=user["id"])
            .order_by(Transcript.created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "filename": r.filename,
                "language": r.language,
                "model": r.model,
                "created_at": r.created_at.isoformat(),
                "snippet": r.text[:120],
            }
            for r in records
        ]
    finally:
        db.close()


def _get_owned_transcript(db, request: Request, transcript_id: int) -> Transcript:
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    record = db.get(Transcript, transcript_id)
    if record is None or record.user_id != user["id"]:
        raise HTTPException(404, "찾을 수 없습니다.")
    return record


@app.get("/api/history/{transcript_id}")
def get_history_item(transcript_id: int, request: Request):
    db = get_session()
    try:
        record = _get_owned_transcript(db, request, transcript_id)
        return {
            "id": record.id,
            "filename": record.filename,
            "language": record.language,
            "model": record.model,
            "created_at": record.created_at.isoformat(),
            "text": record.text,
            "segments": json.loads(record.segments_json),
        }
    finally:
        db.close()


@app.get("/api/history/{transcript_id}/export")
def export_history_item(transcript_id: int, request: Request, fmt: str = "txt"):
    db = get_session()
    try:
        record = _get_owned_transcript(db, request, transcript_id)
        segments = [Segment(**s) for s in json.loads(record.segments_json)]
        return _export_response(segments, Path(record.filename).stem, fmt)
    finally:
        db.close()


@app.delete("/api/history/{transcript_id}")
def delete_history_item(transcript_id: int, request: Request):
    db = get_session()
    try:
        record = _get_owned_transcript(db, request, transcript_id)
        db.delete(record)
        db.commit()
        return {"ok": True}
    finally:
        db.close()
