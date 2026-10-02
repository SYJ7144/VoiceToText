(() => {
  const authArea = document.getElementById("auth-area");
  const loginRequired = document.getElementById("login-required");
  const loginButtons = document.getElementById("login-buttons");
  const historyList = document.getElementById("history-list");
  const detailView = document.getElementById("history-detail");
  const detailSegments = document.getElementById("detail-segments");
  const detailPlayer = document.getElementById("detail-player");
  const detailBack = document.getElementById("detail-back");

  async function loadAuth() {
    const res = await fetch("/api/me");
    const data = await res.json();
    renderAuthArea(data);
    if (!data.logged_in) {
      loginRequired.classList.remove("hidden");
      renderLoginButtons(data.auth);
    } else {
      loadHistory();
    }
  }

  function renderAuthArea(data) {
    authArea.innerHTML = "";
    if (data.logged_in) {
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.textContent = t("nav_logout");
      btn.onclick = async () => {
        await fetch("/auth/logout", { method: "POST" });
        location.href = "/";
      };
      authArea.appendChild(btn);
    } else {
      const btn = document.createElement("a");
      btn.className = "btn";
      btn.href = "#";
      btn.textContent = t("nav_login");
      authArea.appendChild(btn);
    }
  }

  function renderLoginButtons(auth) {
    loginButtons.innerHTML = "";
    if (auth.google) {
      const a = document.createElement("a");
      a.className = "btn btn-primary";
      a.href = "/auth/google/login";
      a.textContent = t("login_google");
      loginButtons.appendChild(a);
    }
    if (auth.kakao) {
      const a = document.createElement("a");
      a.className = "btn";
      a.href = "/auth/kakao/login";
      a.textContent = t("login_kakao");
      loginButtons.appendChild(a);
    }
    if (!auth.google && !auth.kakao) {
      loginButtons.textContent = "로그인 기능이 아직 설정되지 않았습니다.";
    }
  }

  async function loadHistory() {
    const res = await fetch("/api/history");
    const items = await res.json();
    if (!items.length) {
      historyList.innerHTML = `<div class="empty-state">${t("history_empty")}</div>`;
      return;
    }
    historyList.innerHTML = "";
    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "history-item";
      const left = document.createElement("div");
      left.innerHTML = `<div>${item.filename}</div><div class="history-meta">${new Date(item.created_at).toLocaleString()} · ${item.language} · ${item.model}</div><div class="history-meta">${item.snippet}</div>`;
      left.style.cursor = "pointer";
      left.onclick = () => openDetail(item.id);

      const right = document.createElement("div");
      const delBtn = document.createElement("button");
      delBtn.className = "btn";
      delBtn.textContent = t("history_delete");
      delBtn.onclick = async () => {
        await fetch(`/api/history/${item.id}`, { method: "DELETE" });
        loadHistory();
      };
      right.appendChild(delBtn);

      row.append(left, right);
      historyList.appendChild(row);
    });
  }

  async function openDetail(id) {
    const res = await fetch(`/api/history/${id}`);
    const data = await res.json();
    historyList.classList.add("hidden");
    detailView.classList.remove("hidden");
    detailSegments.innerHTML = "";
    data.segments.forEach((seg) => {
      const row = document.createElement("div");
      row.className = "segment";
      row.style.cursor = "default";
      row.innerHTML = `<span class="ts">${formatTs(seg.start)}</span><span>${seg.text}</span>`;
      detailSegments.appendChild(row);
    });
    // 원본 음성 파일은 전사 완료 즉시 삭제되므로(프라이버시 정책) 히스토리에서는 재생할 수 없다.
    detailPlayer.classList.add("hidden");
    document.getElementById("detail-export-txt").href = `/api/history/${id}/export?fmt=txt`;
    document.getElementById("detail-export-srt").href = `/api/history/${id}/export?fmt=srt`;
    document.getElementById("detail-export-vtt").href = `/api/history/${id}/export?fmt=vtt`;
  }

  detailBack.addEventListener("click", () => {
    detailView.classList.add("hidden");
    historyList.classList.remove("hidden");
  });

  function formatTs(seconds) {
    const s = Math.floor(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const mm = String(m).padStart(h ? 2 : 1, "0");
    const ss = String(sec).padStart(2, "0");
    return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
  }

  loadAuth();
})();
