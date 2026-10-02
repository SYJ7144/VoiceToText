(() => {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const modelSelect = document.getElementById("model-select");
  const languageSelect = document.getElementById("language-select");
  const recordBtn = document.getElementById("record-btn");
  const progressEl = document.getElementById("progress");
  const statusLine = document.getElementById("status-line");
  const player = document.getElementById("player");
  const segmentsEl = document.getElementById("segments");
  const actionRow = document.getElementById("action-row");
  const saveBtn = document.getElementById("save-history-btn");
  const exportTxt = document.getElementById("export-txt");
  const exportSrt = document.getElementById("export-srt");
  const exportVtt = document.getElementById("export-vtt");
  const authArea = document.getElementById("auth-area");
  const modelInfo = document.getElementById("model-info");

  let currentJobId = null;
  let currentSegments = [];
  let mediaRecorder = null;
  let recordedChunks = [];
  let isLoggedIn = false;

  // ---- 인증 상태 표시 -------------------------------------------------
  async function loadAuth() {
    try {
      const res = await fetch("/api/me");
      const data = await res.json();
      isLoggedIn = data.logged_in;
      renderAuthArea(data);
    } catch (e) {
      renderAuthArea({ logged_in: false, auth: { google: false, kakao: false } });
    }
  }

  function renderAuthArea(data) {
    authArea.innerHTML = "";
    if (data.logged_in) {
      const span = document.createElement("span");
      span.textContent = data.user.display_name || data.user.email || "";
      span.style.marginRight = "6px";
      span.style.fontSize = "13px";
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.textContent = t("nav_logout");
      btn.onclick = async () => {
        await fetch("/auth/logout", { method: "POST" });
        location.reload();
      };
      authArea.append(span, btn);
    } else {
      const btn = document.createElement("a");
      btn.className = "btn";
      btn.href = "#";
      btn.textContent = t("nav_login");
      btn.onclick = (e) => {
        e.preventDefault();
        if (data.auth.google) location.href = "/auth/google/login";
        else if (data.auth.kakao) location.href = "/auth/kakao/login";
        else alert("로그인 기능이 아직 설정되지 않았습니다 (서버에 OAuth 키 필요).");
      };
      authArea.appendChild(btn);
    }
  }

  // ---- 모델별 차이점 설명 ------------------------------------------------
  function updateModelInfo() {
    const key = `model_info_${modelSelect.value.replace(/-/g, "_")}`;
    modelInfo.textContent = t(key);
  }
  modelSelect.addEventListener("change", updateModelInfo);
  document.addEventListener("langchange", updateModelInfo);
  updateModelInfo();

  // ---- 업로드 / 드래그앤드롭 -------------------------------------------
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") fileInput.click();
  });
  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) startUpload(file);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) startUpload(fileInput.files[0]);
  });

  function startUpload(file) {
    player.src = URL.createObjectURL(file);
    player.classList.remove("hidden");
    uploadAndTranscribe(file);
  }

  async function uploadAndTranscribe(file) {
    resetResult();
    statusLine.textContent = t("status_uploading");
    progressEl.classList.remove("hidden");
    progressEl.value = 0;

    const form = new FormData();
    form.append("file", file, file.name || "recording.webm");
    form.append("model", modelSelect.value);
    form.append("language", languageSelect.value);

    try {
      const res = await fetch("/api/jobs", { method: "POST", body: form });
      if (!res.ok) throw new Error(await res.text());
      const { job_id } = await res.json();
      currentJobId = job_id;
      pollJob(job_id);
    } catch (e) {
      statusLine.textContent = t("error_prefix") + e.message;
    }
  }

  function pollJob(jobId) {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        progressEl.value = data.progress || 0;
        statusLine.textContent = data.message || "";

        if (data.status === "done") {
          clearInterval(interval);
          renderResult(data.result, jobId);
        } else if (data.status === "error") {
          clearInterval(interval);
          statusLine.textContent = t("error_prefix") + (data.error || "unknown");
        }
      } catch (e) {
        clearInterval(interval);
        statusLine.textContent = t("error_prefix") + e.message;
      }
    }, 700);
  }

  function resetResult() {
    segmentsEl.innerHTML = "";
    actionRow.classList.add("hidden");
    currentSegments = [];
    currentJobId = null;
  }

  function renderResult(result, jobId) {
    currentSegments = result.segments;
    segmentsEl.innerHTML = "";
    result.segments.forEach((seg, idx) => {
      const row = document.createElement("div");
      row.className = "segment";
      row.dataset.index = idx;
      const ts = document.createElement("span");
      ts.className = "ts";
      ts.textContent = formatTs(seg.start);
      const text = document.createElement("span");
      text.textContent = seg.text;
      row.append(ts, text);
      row.addEventListener("click", () => seekTo(seg.start));
      segmentsEl.appendChild(row);
    });

    actionRow.classList.remove("hidden");
    exportTxt.href = `/api/jobs/${jobId}/export?fmt=txt`;
    exportSrt.href = `/api/jobs/${jobId}/export?fmt=srt`;
    exportVtt.href = `/api/jobs/${jobId}/export?fmt=vtt`;
    saveBtn.disabled = false;
    saveBtn.onclick = () => saveToHistory(jobId);
  }

  function formatTs(seconds) {
    const s = Math.floor(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const mm = String(m).padStart(h ? 2 : 1, "0");
    const ss = String(sec).padStart(2, "0");
    return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
  }

  function seekTo(start) {
    if (!player.src) return;
    player.currentTime = start;
    player.play();
  }

  // 재생 중인 구간을 자동으로 하이라이트
  player.addEventListener("timeupdate", () => {
    if (!currentSegments.length) return;
    const t0 = player.currentTime;
    let activeIdx = -1;
    for (let i = 0; i < currentSegments.length; i++) {
      if (t0 >= currentSegments[i].start && t0 <= currentSegments[i].end) {
        activeIdx = i;
        break;
      }
    }
    segmentsEl.querySelectorAll(".segment").forEach((el) => {
      el.classList.toggle("active", Number(el.dataset.index) === activeIdx);
    });
  });

  async function saveToHistory(jobId) {
    if (!isLoggedIn) {
      alert(t("save_history_need_login"));
      return;
    }
    try {
      const res = await fetch(`/api/jobs/${jobId}/save`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      alert(t("save_history_done"));
    } catch (e) {
      alert(t("error_prefix") + e.message);
    }
  }

  // ---- 브라우저 녹음 ----------------------------------------------------
  recordBtn.addEventListener("click", async () => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordedChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => recordedChunks.push(e.data);
      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        const blob = new Blob(recordedChunks, { type: "audio/webm" });
        const file = new File([blob], `recording-${Date.now()}.webm`, { type: "audio/webm" });
        recordBtn.querySelector("span").textContent = t("record_start");
        recordBtn.classList.remove("btn-primary");
        startUpload(file);
      };
      mediaRecorder.start();
      recordBtn.querySelector("span").textContent = t("record_stop");
      recordBtn.classList.add("btn-primary");
    } catch (e) {
      alert(t("error_prefix") + e.message);
    }
  });

  document.addEventListener("langchange", () => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      recordBtn.querySelector("span").textContent = t("record_stop");
    }
  });

  loadAuth();
})();
