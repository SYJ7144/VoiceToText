"""업로드된 음성 파일을 백그라운드에서 순차 전사하는 간단한 작업 관리자.

무료/저사양 서버 배포를 가정해 동시 작업 수를 1개로 제한한다(faster-whisper는
CPU/메모리를 많이 쓰므로 여러 개를 동시에 돌리면 쉽게 과부하가 걸린다).
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .transcriber import Segment, TranscriptResult, shared_transcriber

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, "Job"] = {}
_lock = threading.Lock()

JOB_TTL_SECONDS = 60 * 60  # 완료 후 1시간이 지나면 메모리에서 정리


@dataclass
class Job:
    id: str
    filename: str
    model: str
    language: Optional[str]
    status: str = "queued"  # queued | processing | done | error
    progress: float = 0.0
    message: str = "대기 중"
    result: Optional[TranscriptResult] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)


def create_job(audio_path: Path, filename: str, model: str, language: Optional[str]) -> Job:
    job = Job(id=uuid.uuid4().hex, filename=filename, model=model, language=language)
    with _lock:
        _jobs[job.id] = job
    _executor.submit(_run_job, job, audio_path)
    return job


def get_job(job_id: str) -> Optional[Job]:
    _cleanup()
    with _lock:
        return _jobs.get(job_id)


def _cleanup() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with _lock:
        expired = [jid for jid, j in _jobs.items() if j.created_at < cutoff]
        for jid in expired:
            del _jobs[jid]


def _run_job(job: Job, audio_path: Path) -> None:
    job.status = "processing"

    def log(msg: str) -> None:
        job.message = msg

    def progress(value: float) -> None:
        job.progress = value

    try:
        result = shared_transcriber.transcribe(
            audio_path, job.model, job.language, log=log, progress=progress
        )
        job.result = result
        job.status = "done"
        job.message = "완료"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)
        job.message = f"오류: {exc}"
    finally:
        # 전사가 끝나면 원본 음성 파일은 즉시 삭제한다 (프라이버시 정책).
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            pass


def segments_to_dicts(segments: list[Segment]) -> list[dict]:
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
