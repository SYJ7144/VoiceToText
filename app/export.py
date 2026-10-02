"""전사 결과를 txt / srt / vtt 형식으로 변환한다."""

from __future__ import annotations

from .transcriber import Segment, fmt_timestamp


def to_txt(segments: list[Segment]) -> str:
    lines = [f"({fmt_timestamp(s.start)}) {s.text}" for s in segments]
    return "\n".join(lines) + ("\n" if lines else "")


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _vtt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def to_srt(segments: list[Segment]) -> str:
    blocks = []
    for i, seg in enumerate(segments, start=1):
        blocks.append(
            f"{i}\n{_srt_time(seg.start)} --> {_srt_time(seg.end)}\n{seg.text}\n"
        )
    return "\n".join(blocks)


def to_vtt(segments: list[Segment]) -> str:
    blocks = ["WEBVTT\n"]
    for seg in segments:
        blocks.append(f"{_vtt_time(seg.start)} --> {_vtt_time(seg.end)}\n{seg.text}\n")
    return "\n".join(blocks)


EXPORTERS = {
    "txt": (to_txt, "text/plain"),
    "srt": (to_srt, "application/x-subrip"),
    "vtt": (to_vtt, "text/vtt"),
}
