"""faster-whisper를 감싸는 공용 전사 엔진 (웹/데스크탑에서 공유)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

MODELS = ["tiny", "base", "small", "medium", "large-v3"]
DEFAULT_MODEL = "small"

# 언어 표시 코드 -> Whisper 언어 코드 (None 이면 자동 감지)
LANGUAGES = {
    "auto": None,
    "ko": "ko",
    "en": "en",
    "ja": "ja",
    "zh": "zh",
}
DEFAULT_LANGUAGE = "auto"


def fmt_timestamp(seconds: float) -> str:
    """초를 (0:42) / (1:03:07) 형태의 문자열로 변환한다."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    segments: list[Segment]
    detected_language: Optional[str]

    @property
    def text(self) -> str:
        return "\n".join(f"({fmt_timestamp(s.start)}) {s.text}" for s in self.segments)


class Transcriber:
    """faster-whisper 모델을 감싼다. 모델은 한 번 로드하면 재사용한다."""

    def __init__(self) -> None:
        self._model = None
        self._model_size: Optional[str] = None

    def _ensure_model(self, model_size: str, log: Callable[[str], None]):
        if self._model is not None and self._model_size == model_size:
            return self._model

        from faster_whisper import WhisperModel

        log(f"모델 로딩 중: {model_size} (최초 실행 시 다운로드가 필요합니다)…")
        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self._model_size = model_size
        log("모델 준비 완료.")
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        model_size: str,
        language: Optional[str],
        log: Callable[[str], None],
        progress: Callable[[float], None],
    ) -> TranscriptResult:
        model = self._ensure_model(model_size, log)

        log(f"분석 시작: {audio_path.name}")
        raw_segments, info = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            beam_size=5,
        )

        detected = getattr(info, "language", None)
        if language is None and detected:
            log(f"감지된 언어: {detected} (신뢰도 {getattr(info, 'language_probability', 0):.0%})")

        total = getattr(info, "duration", 0) or 0
        segments: list[Segment] = []
        for seg in raw_segments:
            text = seg.text.strip()
            if text:
                segments.append(Segment(start=seg.start, end=seg.end, text=text))
            if total:
                progress(min(100.0, seg.end / total * 100.0))
        progress(100.0)

        return TranscriptResult(segments=segments, detected_language=detected)


# 프로세스 전역에서 모델을 재사용 (요청마다 새로 로드하면 매우 느림)
shared_transcriber = Transcriber()
