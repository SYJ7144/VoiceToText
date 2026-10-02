#!/usr/bin/env python3
"""음성 파일을 텍스트로 변환하는 드래그앤드롭 GUI 프로그램.

로컬 Whisper(faster-whisper)를 사용하므로 인터넷 없이도 동작하며,
음성 파일을 창에 끌어다 놓으면 전사한 뒤 .txt 파일로 저장한다.
"""

from __future__ import annotations

import os
import queue
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

AUDIO_EXTS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus",
    ".wma", ".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi",
}

MODELS = ["tiny", "base", "small", "medium", "large-v3"]
DEFAULT_MODEL = "small"

# 표시 이름 -> Whisper 언어 코드 (None 이면 자동 감지)
LANGUAGES = {
    "자동 감지": None,
    "한국어": "ko",
    "영어": "en",
    "일본어": "ja",
    "중국어": "zh",
}
DEFAULT_LANGUAGE = "자동 감지"


def fmt_timestamp(seconds: float) -> str:
    """초를 (0:42) / (1:03:07) 형태의 문자열로 변환한다."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# 전사 워커
# ---------------------------------------------------------------------------

class Transcriber:
    """faster-whisper 모델을 감싼다. 모델은 한 번 로드하면 재사용한다."""

    def __init__(self) -> None:
        self._model = None
        self._model_size: str | None = None

    def _ensure_model(self, model_size: str, log):
        if self._model is not None and self._model_size == model_size:
            return self._model

        from faster_whisper import WhisperModel

        log(f"모델 로딩 중: {model_size} (최초 실행 시 다운로드가 필요합니다)…")
        # Apple Silicon 에서는 GPU 가속을 지원하지 않아 CPU + int8 을 사용한다.
        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self._model_size = model_size
        log("모델 준비 완료.")
        return self._model

    def transcribe(self, audio_path: Path, model_size: str, language, log, progress):
        """음성을 전사해 전체 텍스트 문자열을 반환한다.

        log(str)         : 상태 메시지 콜백
        progress(float)  : 0~100 진행률 콜백
        """
        model = self._ensure_model(model_size, log)

        log(f"분석 시작: {audio_path.name}")
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            beam_size=5,
        )

        detected = getattr(info, "language", None)
        if language is None and detected:
            log(f"감지된 언어: {detected} (신뢰도 {getattr(info, 'language_probability', 0):.0%})")

        total = getattr(info, "duration", 0) or 0
        parts: list[str] = []
        for seg in segments:
            text = seg.text.strip()
            if text:
                parts.append(f"({fmt_timestamp(seg.start)}) {text}")
            if total:
                progress(min(100.0, seg.end / total * 100.0))
        progress(100.0)

        return "\n".join(parts) + ("\n" if parts else "")


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App:
    def __init__(self, root: TkinterDnD.Tk) -> None:
        self.root = root
        self.transcriber = Transcriber()
        self.jobs: "queue.Queue[Path]" = queue.Queue()
        self.msgs: "queue.Queue[tuple]" = queue.Queue()
        self.busy = False

        root.title("음성 → 텍스트 변환기")
        root.geometry("640x560")
        root.minsize(520, 460)

        # --- 옵션 바 ---
        opts = ttk.Frame(root, padding=(12, 10))
        opts.pack(fill="x")

        ttk.Label(opts, text="모델").pack(side="left")
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        ttk.Combobox(
            opts, textvariable=self.model_var, values=MODELS,
            state="readonly", width=10,
        ).pack(side="left", padx=(4, 16))

        ttk.Label(opts, text="언어").pack(side="left")
        self.lang_var = tk.StringVar(value=DEFAULT_LANGUAGE)
        ttk.Combobox(
            opts, textvariable=self.lang_var, values=list(LANGUAGES),
            state="readonly", width=10,
        ).pack(side="left", padx=(4, 16))

        self.pick_btn = ttk.Button(opts, text="파일 선택…", command=self.pick_files)
        self.pick_btn.pack(side="right")

        # --- 드롭 존 ---
        self.drop = tk.Label(
            root,
            text="여기에 음성 파일을 끌어다 놓으세요\n(mp3, wav, m4a, mp4 …)",
            relief="ridge", borderwidth=2, height=5,
            bg="#f0f0f4", fg="#555",
        )
        self.drop.pack(fill="x", padx=12, pady=(0, 8))
        self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind("<<Drop>>", self.on_drop)

        # --- 진행률 ---
        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=12)

        self.status = ttk.Label(root, text="대기 중", padding=(12, 6), anchor="w")
        self.status.pack(fill="x")

        # --- 결과 텍스트 ---
        wrap = ttk.Frame(root, padding=(12, 0, 12, 12))
        wrap.pack(fill="both", expand=True)
        self.text = tk.Text(wrap, wrap="word", font=("Menlo", 12), undo=True)
        scroll = ttk.Scrollbar(wrap, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        self.root.after(100, self._pump)

    # -- 파일 입력 ---------------------------------------------------------

    def pick_files(self) -> None:
        paths = filedialog.askopenfilenames(title="음성 파일 선택")
        self._enqueue([Path(p) for p in paths])

    def on_drop(self, event) -> None:
        # TkinterDnD 는 공백 포함 경로를 {} 로 감싸서 넘긴다.
        paths = [Path(p) for p in self.root.tk.splitlist(event.data)]
        self._enqueue(paths)

    def _enqueue(self, paths: list[Path]) -> None:
        added = 0
        for p in paths:
            if p.is_dir():
                for child in sorted(p.iterdir()):
                    if child.suffix.lower() in AUDIO_EXTS:
                        self.jobs.put(child)
                        added += 1
            elif p.suffix.lower() in AUDIO_EXTS:
                self.jobs.put(p)
                added += 1
            else:
                self._log(f"건너뜀 (지원하지 않는 형식): {p.name}")
        if added:
            self._log(f"{added}개 파일을 대기열에 추가했습니다.")
            self._maybe_start()

    # -- 워커 실행 -------------------------------------------------------

    def _maybe_start(self) -> None:
        if self.busy:
            return
        try:
            job = self.jobs.get_nowait()
        except queue.Empty:
            self.status.configure(text="대기 중")
            return

        self.busy = True
        self._set_controls(False)
        self.progress.configure(value=0)
        threading.Thread(target=self._run_job, args=(job,), daemon=True).start()

    def _run_job(self, audio_path: Path) -> None:
        model_size = self.model_var.get()
        language = LANGUAGES[self.lang_var.get()]
        try:
            text = self.transcriber.transcribe(
                audio_path, model_size, language,
                log=lambda m: self.msgs.put(("log", m)),
                progress=lambda v: self.msgs.put(("progress", v)),
            )
            out_path = audio_path.with_suffix(".txt")
            out_path.write_text(text, encoding="utf-8")
            self.msgs.put(("done", (audio_path, out_path, text)))
        except Exception:
            self.msgs.put(("error", (audio_path, traceback.format_exc())))

    # -- 메인 스레드 이벤트 펌프 ----------------------------------------

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.msgs.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "progress":
                    self.progress.configure(value=payload)
                elif kind == "done":
                    audio_path, out_path, text = payload
                    self.text.delete("1.0", "end")
                    self.text.insert("1.0", text)
                    self._log(f"완료 → {out_path}")
                    self._finish_job()
                elif kind == "error":
                    audio_path, tb = payload
                    self._log(f"오류 ({audio_path.name}):\n{tb}")
                    self._finish_job()
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _finish_job(self) -> None:
        self.busy = False
        self._set_controls(True)
        self._maybe_start()

    # -- 유틸 -----------------------------------------------------------

    def _set_controls(self, enabled: bool) -> None:
        state = ["!disabled"] if enabled else ["disabled"]
        self.pick_btn.state(state)

    def _log(self, message: str) -> None:
        self.status.configure(text=message.splitlines()[0][:120])
        print(message)


def main() -> None:
    root = TkinterDnD.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
