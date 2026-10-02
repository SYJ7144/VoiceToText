const DICT = {
  en: {
    brand: "VoiceToText",
    nav_history: "My Transcripts",
    nav_login: "Sign in",
    nav_logout: "Sign out",
    model_label: "Model",
    language_label: "Language",
    lang_auto: "Auto-detect",
    lang_ko: "Korean",
    lang_en: "English",
    lang_ja: "Japanese",
    lang_zh: "Chinese",
    dropzone_hint: "Drag an audio file here, or click to choose\n(mp3, wav, m4a, mp4 …)",
    record_start: "Record",
    record_stop: "Stop recording",
    status_idle: "Idle",
    status_uploading: "Uploading…",
    save_history: "Save to My Transcripts",
    save_history_done: "Saved to My Transcripts",
    save_history_need_login: "Sign in to save",
    export_txt: "Download .txt",
    export_srt: "Download .srt",
    export_vtt: "Download .vtt",
    login_prompt: "Sign in to view My Transcripts.",
    login_google: "Continue with Google",
    login_kakao: "Continue with Kakao",
    history_empty: "No saved transcripts yet.",
    history_delete: "Delete",
    back_home: "← Back",
    error_prefix: "Error: ",
    model_info_tiny: "~75 MB download · Very fast · Low accuracy",
    model_info_base: "~145 MB download · Fast · Fair accuracy",
    model_info_small: "~490 MB download · Moderate speed · Good accuracy (recommended)",
    model_info_medium: "~1.5 GB download · Slow · Very good accuracy",
    model_info_large_v3: "~3 GB download · Very slow · Best accuracy",
    model_info_hint: "Larger models are more accurate but slower and take longer to download the first time.",
  },
  ko: {
    brand: "VoiceToText",
    nav_history: "내 기록",
    nav_login: "로그인",
    nav_logout: "로그아웃",
    model_label: "모델",
    language_label: "언어",
    lang_auto: "자동 감지",
    lang_ko: "한국어",
    lang_en: "영어",
    lang_ja: "일본어",
    lang_zh: "중국어",
    dropzone_hint: "여기에 음성 파일을 끌어다 놓으세요, 또는 클릭해서 선택\n(mp3, wav, m4a, mp4 …)",
    record_start: "녹음하기",
    record_stop: "녹음 중지",
    status_idle: "대기 중",
    status_uploading: "업로드 중…",
    save_history: "내 기록에 저장",
    save_history_done: "내 기록에 저장되었습니다",
    save_history_need_login: "내 기록에 저장하려면 로그인이 필요합니다",
    export_txt: ".txt 다운로드",
    export_srt: ".srt 다운로드",
    export_vtt: ".vtt 다운로드",
    login_prompt: "내 기록을 보려면 로그인하세요.",
    login_google: "구글로 계속하기",
    login_kakao: "카카오로 계속하기",
    history_empty: "저장된 전사 기록이 없습니다.",
    history_delete: "삭제",
    back_home: "← 돌아가기",
    error_prefix: "오류: ",
    model_info_tiny: "다운로드 ~75MB · 매우 빠름 · 정확도 낮음",
    model_info_base: "다운로드 ~145MB · 빠름 · 정확도 보통",
    model_info_small: "다운로드 ~490MB · 속도 보통 · 정확도 좋음 (추천)",
    model_info_medium: "다운로드 ~1.5GB · 느림 · 정확도 매우 좋음",
    model_info_large_v3: "다운로드 ~3GB · 매우 느림 · 정확도 최고",
    model_info_hint: "모델이 클수록 정확하지만 느려지고, 처음 선택할 때 다운로드 시간이 더 걸립니다.",
  },
};

function detectLang() {
  const saved = localStorage.getItem("lang");
  if (saved === "en" || saved === "ko") return saved;
  return navigator.language && navigator.language.startsWith("ko") ? "ko" : "en";
}

let currentLang = detectLang();

function t(key) {
  return (DICT[currentLang] && DICT[currentLang][key]) || DICT.en[key] || key;
}

function applyI18n() {
  document.documentElement.lang = currentLang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder")));
  });
  document.querySelectorAll("[data-i18n-option]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n-option"));
  });
  const toggle = document.getElementById("lang-toggle");
  if (toggle) toggle.textContent = currentLang === "ko" ? "EN" : "한국어";
}

function setLang(lang) {
  currentLang = lang;
  try {
    localStorage.setItem("lang", lang);
  } catch (e) {
    /* ignore (private mode) */
  }
  applyI18n();
  document.dispatchEvent(new CustomEvent("langchange", { detail: lang }));
}

function initI18n() {
  applyI18n();
  const toggle = document.getElementById("lang-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => setLang(currentLang === "ko" ? "en" : "ko"));
  }
}

document.addEventListener("DOMContentLoaded", initI18n);
