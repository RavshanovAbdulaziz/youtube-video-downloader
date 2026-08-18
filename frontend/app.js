const urlInput = document.getElementById("url-input");
const fetchBtn = document.getElementById("fetch-btn");
const errorMsg = document.getElementById("error-msg");
const errorMsgText = document.getElementById("error-msg-text");
const videoCard = document.getElementById("video-card");
const thumb = document.getElementById("thumb");
const titleEl = document.getElementById("title");
const durationText = document.getElementById("duration-text");
const resolutionSelect = document.getElementById("resolution-select");
const audioToggle = document.getElementById("audio-toggle");
const videoLangLabel = document.getElementById("video-lang-label");
const videoLangSelect = document.getElementById("video-lang-select");
const downloadVideoBtn = document.getElementById("download-video-btn");
const audioLangSelect = document.getElementById("audio-lang-select");
const downloadAudioBtn = document.getElementById("download-audio-btn");
const progressWrap = document.getElementById("progress-wrap");
const progressFill = document.getElementById("progress-fill");
const progressText = document.getElementById("progress-text");
const fileLink = document.getElementById("file-link");
const subtitleLangSelect = document.getElementById("subtitle-lang-select");
const downloadSubtitleBtn = document.getElementById("download-subtitle-btn");
const subtitleProgressWrap = document.getElementById("subtitle-progress-wrap");
const subtitleProgressFill = document.getElementById("subtitle-progress-fill");
const subtitleProgressText = document.getElementById("subtitle-progress-text");
const subtitleFileLink = document.getElementById("subtitle-file-link");
const separateEngineSelect = document.getElementById("separate-engine-select");
const separateLangSelect = document.getElementById("separate-lang-select");
const separateBtn = document.getElementById("separate-btn");
const separateProgressWrap = document.getElementById("separate-progress-wrap");
const separateProgressFill = document.getElementById("separate-progress-fill");
const separateProgressText = document.getElementById("separate-progress-text");
const separateLinks = document.getElementById("separate-links");
const speechFileLink = document.getElementById("speech-file-link");
const backgroundFileLink = document.getElementById("background-file-link");
const clipRangeStart = document.getElementById("clip-range-start");
const clipRangeEnd = document.getElementById("clip-range-end");
const clipStartLabel = document.getElementById("clip-start-label");
const clipEndLabel = document.getElementById("clip-end-label");
const clipSliderFill = document.getElementById("clip-slider-fill");
const computeModal = document.getElementById("compute-modal");
const computeYesBtn = document.getElementById("compute-yes-btn");
const computeNoBtn = document.getElementById("compute-no-btn");
const computeStatus = document.getElementById("compute-status");
const tabsNav = document.getElementById("tabs");
const tabButtons = Array.from(document.querySelectorAll(".tab"));
const tabPanels = Array.from(document.querySelectorAll(".tab-panel"));

let currentInfo = null;

// Progress-poll setInterval'lari ketma-ket shuncha marta muvaffaqiyatsiz
// bo'lsa (fetch/JSON xatosi), to'xtatiladi va xato ko'rsatiladi — aks holda
// (avval) xato hech qayerda ushlanmagani uchun interval jim ravishda abadiy
// ishlayverar, tugma va progress esa "Boshlanmoqda..."da muzlab qolardi.
const POLL_MAX_CONSECUTIVE_FAILURES = 5;

// ---------------------------------------------------------------------------
// Tabs (Video / Audio / Subtitr / AI ajratish)
// ---------------------------------------------------------------------------

function setActiveTab(tabId) {
  tabButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tabId));
  tabPanels.forEach((panel) => {
    const panels = panel.dataset.panel.split(" ");
    panel.classList.toggle("active", panels.includes(tabId));
  });
}

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
});

function updateTabsAvailability(data) {
  const hasAudio = data.audio_tracks.length > 0;
  const hasSubtitles = (data.subtitles || []).length > 0;
  document.querySelector('.tab[data-tab="audio"]').classList.toggle("hidden", !hasAudio);
  document.querySelector('.tab[data-tab="separate"]').classList.toggle("hidden", !hasAudio);
  document.querySelector('.tab[data-tab="subtitle"]').classList.toggle("hidden", !hasSubtitles);
  const visibleCount = tabButtons.filter((btn) => !btn.classList.contains("hidden")).length;
  tabsNav.classList.toggle("hidden", visibleCount <= 1);
  setActiveTab("video");
}

const LOCAL_BASE = "http://127.0.0.1:8000";
const COMPUTE_PREF_KEY = "useLocalCompute";

function getComputePreference() {
  return localStorage.getItem(COMPUTE_PREF_KEY); // "yes" | "no" | null
}

function setComputePreference(value) {
  localStorage.setItem(COMPUTE_PREF_KEY, value);
  updateComputeStatusText();
}

function updateComputeStatusText() {
  const pref = getComputePreference();
  computeStatus.classList.toggle("on", pref === "yes");
  computeStatus.textContent = pref === "yes"
    ? "Kompyuter kuchi: yoqilgan"
    : "Kompyuter kuchi: o'chirilgan";
}

function openComputeModal() {
  computeModal.classList.remove("hidden");
}

function closeComputeModal() {
  computeModal.classList.add("hidden");
}

computeYesBtn.addEventListener("click", () => {
  setComputePreference("yes");
  closeComputeModal();
});

computeNoBtn.addEventListener("click", () => {
  setComputePreference("no");
  closeComputeModal();
});

computeStatus.addEventListener("click", openComputeModal);
computeStatus.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openComputeModal();
  }
});

updateComputeStatusText();
if (getComputePreference() === null) {
  openComputeModal();
}

// Ish (download/separate) boshlanishidan oldin chaqiriladi: agar foydalanuvchi
// ruxsat bergan bo'lsa va mahalliy dastur (start.bat) ishlab turgan bo'lsa,
// shu kompyuter orqali bajaramiz; aks holda server ("") ishlatiladi.
async function apiBase() {
  if (getComputePreference() !== "yes") return "";
  try {
    const res = await fetch(`${LOCAL_BASE}/api/health`, { signal: AbortSignal.timeout(1500) });
    if (res.ok) return LOCAL_BASE;
  } catch (e) {
    // mahalliy dastur ishlamayapti yoki brauzer ruxsat bermadi — serverga o'tamiz
  }
  return "";
}

function showError(msg) {
  errorMsgText.textContent = msg;
  errorMsg.classList.remove("hidden");
}

function clearError() {
  errorMsg.classList.add("hidden");
}

function formatDuration(sec) {
  if (!sec) return "";
  sec = Math.floor(sec);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  }
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function setProgress(fillEl, percent, indeterminate) {
  fillEl.classList.toggle("indeterminate", !!indeterminate);
  fillEl.style.width = indeterminate ? "100%" : `${percent}%`;
}

// ---------------------------------------------------------------------------
// Vaqt oralig'i (ikki dastakli slayder — faqat bir qismini yuklab olish)
// ---------------------------------------------------------------------------

const CLIP_MIN_GAP = 1; // soniya — dastaklar bir-birining ustiga chiqib ketmasin

// Slayderdagi ikkita dastak bir-biridan kamida CLIP_MIN_GAP uzoqlikda turishini
// ta'minlaydi, keyin yorliqlar/to'ldirilgan chiziq va bosish ustuvorligini yangilaydi.
function clampClipThumbs(moved) {
  const max = Number(clipRangeStart.max) || 0;
  let start = Number(clipRangeStart.value);
  let end = Number(clipRangeEnd.value);
  if (moved === "start" && start > end - CLIP_MIN_GAP) {
    start = Math.max(0, end - CLIP_MIN_GAP);
    clipRangeStart.value = start;
  } else if (moved === "end" && end < start + CLIP_MIN_GAP) {
    end = Math.min(max, start + CLIP_MIN_GAP);
    clipRangeEnd.value = end;
  }
  updateClipUI();
}

function updateClipUI() {
  const max = Number(clipRangeStart.max) || 0;
  const start = Number(clipRangeStart.value);
  const end = Number(clipRangeEnd.value);

  clipStartLabel.textContent = formatDuration(start);
  clipEndLabel.textContent = formatDuration(end);

  if (max > 0) {
    clipSliderFill.style.left = `${(start / max) * 100}%`;
    clipSliderFill.style.right = `${100 - (end / max) * 100}%`;
  }

  // Dastaklar bir-biriga yaqinlashganda "orqada" turgani ham bosilishi uchun —
  // uzoqdagi yarimda turgan dastakka ustunlik beriladi.
  if (max > 0 && start > max / 2) {
    clipRangeStart.style.zIndex = 3;
    clipRangeEnd.style.zIndex = 2;
  } else {
    clipRangeStart.style.zIndex = 2;
    clipRangeEnd.style.zIndex = 3;
  }
}

clipRangeStart.addEventListener("input", () => clampClipThumbs("start"));
clipRangeEnd.addEventListener("input", () => clampClipThumbs("end"));

// Dastaklar chetlarda (0 va butun davomiylik) qolsa {start_time: null,
// end_time: null} (ya'ni butun video) qaytaradi — aks holda tanlangan oraliq.
function readClipRange() {
  const duration = currentInfo && Math.round(currentInfo.duration || 0);
  if (!duration) return { start_time: null, end_time: null };
  const start = Number(clipRangeStart.value);
  const end = Number(clipRangeEnd.value);
  if (start <= 0 && end >= duration) return { start_time: null, end_time: null };
  return { start_time: start, end_time: end };
}

function updateVideoLangVisibility() {
  const showLang = currentInfo && currentInfo.audio_tracks.length > 1 && audioToggle.checked;
  videoLangLabel.classList.toggle("hidden", !showLang);
}

audioToggle.addEventListener("change", updateVideoLangVisibility);

fetchBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    showError("Iltimos, YouTube havolasini kiriting.");
    return;
  }
  clearError();
  videoCard.classList.add("hidden");
  fetchBtn.disabled = true;
  fetchBtn.classList.add("loading");

  try {
    const res = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");

    currentInfo = data;
    renderInfo(data);
  } catch (e) {
    showError(e.message);
  } finally {
    fetchBtn.disabled = false;
    fetchBtn.classList.remove("loading");
  }
});

function fillLangSelect(select, tracks) {
  select.innerHTML = "";
  tracks.forEach((a) => {
    const opt = document.createElement("option");
    opt.value = a.format_id;
    opt.textContent = a.label;
    select.appendChild(opt);
  });
}

function renderInfo(data) {
  thumb.src = data.thumbnail || "";
  titleEl.textContent = data.title || "";
  durationText.textContent = formatDuration(data.duration);

  resolutionSelect.innerHTML = "";
  data.resolutions.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.format_id;
    opt.textContent = r.label + (r.filesize ? ` (~${(r.filesize / 1024 / 1024).toFixed(1)} MB)` : "");
    resolutionSelect.appendChild(opt);
  });

  fillLangSelect(videoLangSelect, data.audio_tracks);
  fillLangSelect(audioLangSelect, data.audio_tracks);
  fillLangSelect(separateLangSelect, data.audio_tracks);

  audioToggle.checked = data.audio_tracks.length > 0;
  updateVideoLangVisibility();

  const subtitles = data.subtitles || [];
  subtitleLangSelect.innerHTML = "";
  subtitles.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = `${s.lang_code}::${s.auto ? 1 : 0}`;
    opt.textContent = s.label;
    subtitleLangSelect.appendChild(opt);
  });
  subtitleProgressWrap.classList.add("hidden");
  subtitleFileLink.classList.add("hidden");

  const duration = Math.max(1, Math.round(data.duration || 0));
  clipRangeStart.max = duration;
  clipRangeStart.value = 0;
  clipRangeEnd.max = duration;
  clipRangeEnd.value = duration;
  updateClipUI();

  progressWrap.classList.add("hidden");
  fileLink.classList.add("hidden");
  separateProgressWrap.classList.add("hidden");
  separateLinks.classList.add("hidden");

  updateTabsAvailability(data);
  videoCard.classList.remove("hidden");
}

function setButtonsDisabled(disabled) {
  downloadVideoBtn.disabled = disabled;
  downloadAudioBtn.disabled = disabled;
}

async function startDownload(body) {
  clearError();
  fileLink.classList.add("hidden");
  progressWrap.classList.remove("hidden");
  setProgress(progressFill, 0, true);
  progressText.textContent = "Boshlanmoqda...";
  setButtonsDisabled(true);

  const base = await apiBase();
  try {
    const res = await fetch(`${base}/api/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");
    pollProgress(data.job_id, base);
  } catch (e) {
    showError(e.message);
    setButtonsDisabled(false);
  }
}

downloadVideoBtn.addEventListener("click", () => {
  if (!currentInfo) return;
  const wantAudio = audioToggle.checked;
  startDownload({
    url: urlInput.value.trim(),
    audio_only: false,
    video_format_id: resolutionSelect.value,
    audio_format_id: wantAudio && currentInfo.audio_tracks.length ? videoLangSelect.value : null,
    title: currentInfo.title,
    ...readClipRange(),
  });
});

downloadAudioBtn.addEventListener("click", () => {
  if (!currentInfo) return;
  startDownload({
    url: urlInput.value.trim(),
    audio_only: true,
    video_format_id: null,
    audio_format_id: audioLangSelect.value,
    title: currentInfo.title,
    ...readClipRange(),
  });
});

separateBtn.addEventListener("click", async () => {
  if (!currentInfo) return;
  clearError();
  separateLinks.classList.add("hidden");
  separateProgressWrap.classList.remove("hidden");
  setProgress(separateProgressFill, 0, true);
  separateProgressText.textContent = "Boshlanmoqda...";
  separateBtn.disabled = true;

  const base = await apiBase();
  try {
    const res = await fetch(`${base}/api/separate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: urlInput.value.trim(),
        audio_format_id: separateLangSelect.value,
        title: currentInfo.title,
        engine: separateEngineSelect.value,
        ...readClipRange(),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");
    pollSeparateProgress(data.job_id, base);
  } catch (e) {
    showError(e.message);
    separateBtn.disabled = false;
  }
});

function pollSeparateProgress(jobId, base) {
  let consecutiveFailures = 0;
  const interval = setInterval(async () => {
    let data;
    try {
      const res = await fetch(`${base}/api/separate/progress/${jobId}`);
      data = await res.json();
      consecutiveFailures = 0;
    } catch (e) {
      consecutiveFailures += 1;
      if (consecutiveFailures >= POLL_MAX_CONSECUTIVE_FAILURES) {
        clearInterval(interval);
        showError("Server bilan aloqa uzildi. Sahifani yangilab qayta urinib ko'ring.");
        separateProgressWrap.classList.add("hidden");
        separateBtn.disabled = false;
      }
      return;
    }
    const pct = data.percent != null ? data.percent : 0;

    if (data.status === "queued") {
      setProgress(separateProgressFill, 0, true);
      separateProgressText.textContent = "Boshlanmoqda...";
    } else if (data.status === "installing_ai") {
      const stageLabel = { torch: "PyTorch", demucs: "Demucs", separator: "UVR/audio-separator", compat: "moslashtirish" }[data.ai_stage] || "";
      setProgress(separateProgressFill, pct, false);
      separateProgressText.textContent = `AI komponentlari o'rnatilmoqda (${stageLabel}): ${pct}% — bu bir martalik jarayon, internetga bog'liq`;
    } else if (data.status === "downloading") {
      setProgress(separateProgressFill, pct, false);
      separateProgressText.textContent = `Audio yuklab olinmoqda: ${pct}%`;
    } else if (data.status === "separating") {
      setProgress(separateProgressFill, pct, false);
      separateProgressText.textContent = `Ajratilmoqda: ${pct}% (bir necha daqiqa vaqt olishi mumkin)`;
    } else if (data.status === "finished") {
      clearInterval(interval);
      setProgress(separateProgressFill, 100, false);
      separateProgressText.textContent = "Tayyor!";
      speechFileLink.href = `${base}/api/separate/file/${jobId}/speech`;
      backgroundFileLink.href = `${base}/api/separate/file/${jobId}/background`;
      separateLinks.classList.remove("hidden");
      separateBtn.disabled = false;
    } else if (data.status === "error") {
      clearInterval(interval);
      showError(data.error || "Ajratishda xatolik yuz berdi");
      separateProgressWrap.classList.add("hidden");
      separateBtn.disabled = false;
    }
  }, 1200);
}

downloadSubtitleBtn.addEventListener("click", async () => {
  if (!currentInfo || !subtitleLangSelect.value) return;
  const [langCode, autoFlag] = subtitleLangSelect.value.split("::");
  clearError();
  subtitleFileLink.classList.add("hidden");
  subtitleProgressWrap.classList.remove("hidden");
  setProgress(subtitleProgressFill, 0, true);
  subtitleProgressText.textContent = "Boshlanmoqda...";
  downloadSubtitleBtn.disabled = true;

  const base = await apiBase();
  try {
    const res = await fetch(`${base}/api/download/subtitle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: urlInput.value.trim(),
        lang_code: langCode,
        auto: autoFlag === "1",
        title: currentInfo.title,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");
    pollSubtitleProgress(data.job_id, base);
  } catch (e) {
    showError(e.message);
    subtitleProgressWrap.classList.add("hidden");
    downloadSubtitleBtn.disabled = false;
  }
});

function pollSubtitleProgress(jobId, base) {
  let consecutiveFailures = 0;
  const interval = setInterval(async () => {
    let data;
    try {
      const res = await fetch(`${base}/api/progress/${jobId}`);
      data = await res.json();
      consecutiveFailures = 0;
    } catch (e) {
      consecutiveFailures += 1;
      if (consecutiveFailures >= POLL_MAX_CONSECUTIVE_FAILURES) {
        clearInterval(interval);
        showError("Server bilan aloqa uzildi. Sahifani yangilab qayta urinib ko'ring.");
        subtitleProgressWrap.classList.add("hidden");
        downloadSubtitleBtn.disabled = false;
      }
      return;
    }

    if (data.status === "finished") {
      clearInterval(interval);
      setProgress(subtitleProgressFill, 100, false);
      subtitleProgressText.textContent = "Tayyor!";
      subtitleFileLink.href = `${base}/api/file/${jobId}`;
      subtitleFileLink.classList.remove("hidden");
      downloadSubtitleBtn.disabled = false;
    } else if (data.status === "error") {
      clearInterval(interval);
      showError(data.error || "Subtitrni yuklab olishda xatolik yuz berdi");
      subtitleProgressWrap.classList.add("hidden");
      downloadSubtitleBtn.disabled = false;
    }
  }, 1000);
}

function pollProgress(jobId, base) {
  let consecutiveFailures = 0;
  const interval = setInterval(async () => {
    let data;
    try {
      const res = await fetch(`${base}/api/progress/${jobId}`);
      data = await res.json();
      consecutiveFailures = 0;
    } catch (e) {
      // Tarmoq uzilishi/vaqtinchalik xato — bir necha marta jim o'tkazib
      // yuboriladi (keyingi tick baribir qayta uradi). Bo'lmasa (avval)
      // bu yerdagi xato hech qayerda ushlanmagani uchun interval abadiy
      // ishlab, progress "Boshlanmoqda..."da muzlab qolardi.
      consecutiveFailures += 1;
      if (consecutiveFailures >= POLL_MAX_CONSECUTIVE_FAILURES) {
        clearInterval(interval);
        showError("Server bilan aloqa uzildi. Sahifani yangilab qayta urinib ko'ring.");
        progressWrap.classList.add("hidden");
        setButtonsDisabled(false);
      }
      return;
    }

    if (data.status === "queued") {
      setProgress(progressFill, 0, true);
      progressText.textContent = "Boshlanmoqda...";
    } else if (data.status === "downloading") {
      const pct = data.percent != null ? data.percent : 0;
      const speed = data.speed ? `${(data.speed / 1024 / 1024).toFixed(2)} MB/s` : "";
      if (data.percent != null) {
        setProgress(progressFill, pct, false);
        progressText.textContent = `Yuklanmoqda: ${pct}% ${speed}`;
      } else {
        setProgress(progressFill, 0, true);
        progressText.textContent = `Yuklanmoqda... ${speed}`;
      }
    } else if (data.status === "merging") {
      setProgress(progressFill, 100, true);
      progressText.textContent = "Video va audio birlashtirilmoqda...";
    } else if (data.status === "finished") {
      clearInterval(interval);
      setProgress(progressFill, 100, false);
      progressText.textContent = "Tayyor!";
      fileLink.href = `${base}/api/file/${jobId}`;
      fileLink.classList.remove("hidden");
      setButtonsDisabled(false);
    } else if (data.status === "error") {
      clearInterval(interval);
      showError(data.error || "Yuklab olishda xatolik yuz berdi");
      progressWrap.classList.add("hidden");
      setButtonsDisabled(false);
    }
  }, 1000);
}
