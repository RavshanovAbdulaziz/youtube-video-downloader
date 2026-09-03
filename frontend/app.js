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
const clipSection = document.getElementById("clip-section");
const clipRangeStart = document.getElementById("clip-range-start");
const clipRangeEnd = document.getElementById("clip-range-end");
const clipStartLabel = document.getElementById("clip-start-label");
const clipEndLabel = document.getElementById("clip-end-label");
const clipSliderFill = document.getElementById("clip-slider-fill");
const clipTimestampNote = document.getElementById("clip-timestamp-note");
const computeModal = document.getElementById("compute-modal");
const computeYesBtn = document.getElementById("compute-yes-btn");
const computeNoBtn = document.getElementById("compute-no-btn");
const computeStatus = document.getElementById("compute-status");
const tabsNav = document.getElementById("tabs");
const tabButtons = Array.from(document.querySelectorAll(".tab:not(.mode-tab)"));
const tabPanels = Array.from(document.querySelectorAll(".tab-panel:not(.mode-panel)"));
const modeTabButtons = Array.from(document.querySelectorAll(".mode-tab"));
const modePanels = Array.from(document.querySelectorAll(".mode-panel"));
const liveBadge = document.getElementById("live-badge");
const liveOptions = document.getElementById("live-options");
const liveResolutionSelect = document.getElementById("live-resolution-select");
const liveAudioToggle = document.getElementById("live-audio-toggle");
const liveLangLabel = document.getElementById("live-lang-label");
const liveLangSelect = document.getElementById("live-lang-select");
const liveStartBtn = document.getElementById("live-start-btn");
const liveAudioBtn = document.getElementById("live-audio-btn");
const liveRecordingWrap = document.getElementById("live-recording-wrap");
const liveElapsedText = document.getElementById("live-elapsed-text");
const liveSizeText = document.getElementById("live-size-text");
const liveStopBtn = document.getElementById("live-stop-btn");
const liveErrorMsg = document.getElementById("live-error-msg");
const liveErrorMsgText = document.getElementById("live-error-msg-text");
const liveFileLink = document.getElementById("live-file-link");
const transcriptQueryInput = document.getElementById("transcript-query-input");
const transcriptChannelInput = document.getElementById("transcript-channel-input");
const transcriptYearsFromInput = document.getElementById("transcript-years-from-input");
const transcriptMonthsFromInput = document.getElementById("transcript-months-from-input");
const transcriptYearsToInput = document.getElementById("transcript-years-to-input");
const transcriptMonthsToInput = document.getElementById("transcript-months-to-input");
const transcriptSearchBtn = document.getElementById("transcript-search-btn");
const transcriptErrorMsg = document.getElementById("transcript-error-msg");
const transcriptErrorMsgText = document.getElementById("transcript-error-msg-text");
const transcriptProgressWrap = document.getElementById("transcript-progress-wrap");
const transcriptProgressFill = document.getElementById("transcript-progress-fill");
const transcriptEmptyMsg = document.getElementById("transcript-empty-msg");
const transcriptResults = document.getElementById("transcript-results");
const findSourceUrlInput = document.getElementById("find-source-url-input");
const findSourceBtn = document.getElementById("find-source-btn");
const findSourceErrorMsg = document.getElementById("find-source-error-msg");
const findSourceErrorMsgText = document.getElementById("find-source-error-msg-text");
const findSourceProgressWrap = document.getElementById("find-source-progress-wrap");
const findSourceProgressFill = document.getElementById("find-source-progress-fill");
const findSourceResult = document.getElementById("find-source-result");

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
  const isLive = !!data.is_live;
  const hasAudio = data.audio_tracks.length > 0;
  const hasSubtitles = (data.subtitles || []).length > 0;
  // Jonli efirda hali noma'lum davomiylik/hajm bilan ishlaydigan oddiy
  // Video/Audio/Subtitr/AI tablari mos kelmaydi — faqat maxsus "Efir" tabi
  // ko'rsatiladi (pastdagi live-capture oqimi).
  document.querySelector('.tab[data-tab="live"]').classList.toggle("hidden", !isLive);
  document.querySelector('.tab[data-tab="video"]').classList.toggle("hidden", isLive);
  document.querySelector('.tab[data-tab="audio"]').classList.toggle("hidden", isLive || !hasAudio);
  document.querySelector('.tab[data-tab="separate"]').classList.toggle("hidden", isLive || !hasAudio);
  document.querySelector('.tab[data-tab="subtitle"]').classList.toggle("hidden", isLive || !hasSubtitles);
  const visibleCount = tabButtons.filter((btn) => !btn.classList.contains("hidden")).length;
  tabsNav.classList.toggle("hidden", visibleCount <= 1);
  setActiveTab(isLive ? "live" : "video");
}

// ---------------------------------------------------------------------------
// Sahifa rejimi (Yuklab olish / Transkript qidiruv) — yuqori darajadagi tab,
// video-card ichidagi Video/Audio/Subtitr/AI tablaridan mustaqil.
// ---------------------------------------------------------------------------

function setActiveMode(modeId) {
  modeTabButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.mode === modeId));
  modePanels.forEach((panel) => panel.classList.toggle("active", panel.dataset.modePanel === modeId));
}

modeTabButtons.forEach((btn) => {
  btn.addEventListener("click", () => setActiveMode(btn.dataset.mode));
});

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

// Havolaga qo'shilgan vaqt belgisidan (`?t=375`) olingan boshlanish nuqtasi,
// soniyalarda; 0 — havolada vaqt belgisi bo'lmagan. Boshlanish dastagi hali
// aynan shu joyda turgan ekan, foydalanuvchiga eslatma ko'rsatiladi (dastak
// surilishi bilanoq eslatma o'z-o'zidan yo'qoladi).
let linkStartTime = 0;

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

  // Foydalanuvchi hozir qo'lda kiritayotgan maydonni ustidan yozib
  // qo'ymaslik uchun — faqat fokusda bo'lmagan maydon yangilanadi.
  if (document.activeElement !== clipStartLabel) {
    clipStartLabel.value = formatDuration(start) || "0:00";
  }
  if (document.activeElement !== clipEndLabel) {
    clipEndLabel.value = formatDuration(end) || "0:00";
  }

  if (max > 0) {
    clipSliderFill.style.left = `${(start / max) * 100}%`;
    clipSliderFill.style.right = `${100 - (end / max) * 100}%`;
  }

  const usingLinkStart = linkStartTime > 0 && start === linkStartTime;
  clipTimestampNote.textContent = usingLinkStart
    ? `Havoladagi vaqt belgisi qo'llandi — boshlanish ${formatDuration(linkStartTime)}.`
    : "";
  clipTimestampNote.classList.toggle("hidden", !usingLinkStart);

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

// "H:MM:SS", "M:SS" yoki xom soniyani soniyaga aylantiradi; noto'g'ri
// matn kiritilsa — null qaytaradi (qiymat eskisiga qaytariladi).
function parseClipTimeInput(str) {
  const trimmed = String(str ?? "").trim();
  if (!trimmed) return null;
  const parts = trimmed.split(":").map((p) => p.trim());
  if (parts.length > 3 || parts.some((p) => p === "" || !/^\d+$/.test(p))) return null;
  let seconds = 0;
  for (const part of parts) {
    seconds = seconds * 60 + Number(part);
  }
  return seconds;
}

// Dastak yorlig'iga qo'lda kiritilgan vaqtni tasdiqlaydi: to'g'ri bo'lsa
// tegishli slayder dastagini shu qiymatga suradi, aks holda eski qiymatga qaytaradi.
function commitClipLabelInput(which) {
  const input = which === "start" ? clipStartLabel : clipEndLabel;
  const max = Number(clipRangeStart.max) || 0;
  const parsed = parseClipTimeInput(input.value);
  if (parsed === null || Number.isNaN(parsed)) {
    updateClipUI();
    return;
  }
  const clamped = Math.max(0, Math.min(max, Math.round(parsed)));
  if (which === "start") {
    clipRangeStart.value = clamped;
    clampClipThumbs("start");
  } else {
    clipRangeEnd.value = clamped;
    clampClipThumbs("end");
  }
}

[clipStartLabel, clipEndLabel].forEach((input, idx) => {
  const which = idx === 0 ? "start" : "end";
  input.addEventListener("change", () => commitClipLabelInput(which));
  input.addEventListener("focus", () => input.select());
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      input.blur();
    }
  });
});

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
  liveBadge.classList.toggle("hidden", !data.is_live);
  clipSection.classList.toggle("hidden", !!data.is_live);

  resolutionSelect.innerHTML = "";
  liveResolutionSelect.innerHTML = "";
  data.resolutions.forEach((r) => {
    const label = r.label + (r.filesize ? ` (~${(r.filesize / 1024 / 1024).toFixed(1)} MB)` : "");
    const opt = document.createElement("option");
    opt.value = r.format_id;
    opt.textContent = label;
    resolutionSelect.appendChild(opt);
    const liveOpt = document.createElement("option");
    liveOpt.value = r.format_id;
    liveOpt.textContent = r.label;
    liveResolutionSelect.appendChild(liveOpt);
  });

  fillLangSelect(videoLangSelect, data.audio_tracks);
  fillLangSelect(audioLangSelect, data.audio_tracks);
  fillLangSelect(separateLangSelect, data.audio_tracks);
  fillLangSelect(liveLangSelect, data.audio_tracks);

  audioToggle.checked = data.audio_tracks.length > 0;
  updateVideoLangVisibility();
  liveAudioToggle.checked = data.audio_tracks.length > 0;
  updateLiveLangVisibility();
  resetLiveTab();

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

  // Havolada vaqt belgisi bo'lsa (YouTube ulashish oynasidagi "Start at"
  // katakchasi yoki transcript qidiruvi bergan `&t=375s`) — boshlanish dastagi
  // o'sha nuqtaga qo'yiladi, tugash dastagi esa video oxirida qoladi.
  const duration = Math.max(1, Math.round(data.duration || 0));
  linkStartTime = Math.min(
    Math.max(0, Math.round(Number(data.start_time) || 0)),
    Math.max(0, duration - CLIP_MIN_GAP),
  );
  clipRangeStart.max = duration;
  clipRangeStart.value = linkStartTime;
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

// ---------------------------------------------------------------------------
// Jonli efirni yozib olish ("Efir" tabi)
// ---------------------------------------------------------------------------

let liveJobId = null;
let livePollInterval = null;

function updateLiveLangVisibility() {
  const showLang = currentInfo && currentInfo.audio_tracks.length > 1 && liveAudioToggle.checked;
  liveLangLabel.classList.toggle("hidden", !showLang);
}

liveAudioToggle.addEventListener("change", updateLiveLangVisibility);

function showLiveError(msg) {
  liveErrorMsgText.textContent = msg;
  liveErrorMsg.classList.remove("hidden");
}

function clearLiveError() {
  liveErrorMsg.classList.add("hidden");
}

function formatBytes(bytes) {
  if (!bytes) return "";
  const mb = bytes / 1024 / 1024;
  return mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(1)} MB`;
}

// Video kartasi qayta chizilganda (yangi URL tekshirilganda) "Efir" tabini
// boshlang'ich holatga qaytaradi — oldingi (agar bo'lsa) yozib olish holati
// (progress, xato, tayyor fayl havolasi) ko'rinishda qolib ketmasin.
function resetLiveTab() {
  if (livePollInterval) {
    clearInterval(livePollInterval);
    livePollInterval = null;
  }
  liveJobId = null;
  clearLiveError();
  liveFileLink.classList.add("hidden");
  liveRecordingWrap.classList.add("hidden");
  liveOptions.classList.remove("hidden");
  liveStartBtn.classList.remove("hidden");
  liveAudioBtn.classList.remove("hidden");
  liveStartBtn.disabled = false;
  liveAudioBtn.disabled = false;
  liveStopBtn.disabled = false;
  liveElapsedText.textContent = "0:00";
  liveSizeText.textContent = "";
}

async function startLiveCapture(body) {
  clearLiveError();
  liveFileLink.classList.add("hidden");
  liveStartBtn.disabled = true;
  liveAudioBtn.disabled = true;

  const base = await apiBase();
  try {
    const res = await fetch(`${base}/api/live/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");

    liveJobId = data.job_id;
    liveOptions.classList.add("hidden");
    liveStartBtn.classList.add("hidden");
    liveAudioBtn.classList.add("hidden");
    liveRecordingWrap.classList.remove("hidden");
    pollLiveProgress(liveJobId, base);
  } catch (e) {
    showLiveError(e.message);
    liveStartBtn.disabled = false;
    liveAudioBtn.disabled = false;
  }
}

liveStartBtn.addEventListener("click", () => {
  if (!currentInfo) return;
  const wantAudio = liveAudioToggle.checked;
  startLiveCapture({
    url: urlInput.value.trim(),
    video_format_id: liveResolutionSelect.value,
    audio_format_id: wantAudio && currentInfo.audio_tracks.length ? liveLangSelect.value : null,
    audio_only: false,
    title: currentInfo.title,
  });
});

liveAudioBtn.addEventListener("click", () => {
  if (!currentInfo) return;
  // Ko'pchilik jonli efirlarda alohida audio-only trek yo'q — shunda
  // tanlangan video (odatda audio o'z ichiga qo'shilgan) format manba
  // sifatida yuboriladi, backend undan faqat audioni ajratib oladi.
  const hasAudioTracks = currentInfo.audio_tracks.length > 0;
  startLiveCapture({
    url: urlInput.value.trim(),
    video_format_id: hasAudioTracks ? null : liveResolutionSelect.value,
    audio_format_id: hasAudioTracks ? liveLangSelect.value : null,
    audio_only: true,
    title: currentInfo.title,
  });
});

liveStopBtn.addEventListener("click", async () => {
  if (!liveJobId) return;
  liveStopBtn.disabled = true;

  const base = await apiBase();
  try {
    const res = await fetch(`${base}/api/live/stop/${liveJobId}`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "To'xtatib bo'lmadi");
    }
  } catch (e) {
    showLiveError(e.message);
    liveStopBtn.disabled = false;
  }
});

function pollLiveProgress(jobId, base) {
  let consecutiveFailures = 0;
  livePollInterval = setInterval(async () => {
    let data;
    try {
      const res = await fetch(`${base}/api/progress/${jobId}`);
      data = await res.json();
      consecutiveFailures = 0;
    } catch (e) {
      consecutiveFailures += 1;
      if (consecutiveFailures >= POLL_MAX_CONSECUTIVE_FAILURES) {
        clearInterval(livePollInterval);
        livePollInterval = null;
        showLiveError("Server bilan aloqa uzildi. Sahifani yangilab qayta urinib ko'ring.");
        resetLiveTab();
      }
      return;
    }

    if (data.status === "queued" || data.status === "downloading") {
      liveElapsedText.textContent = formatDuration(Math.floor(data.elapsed || 0)) || "0:00";
      liveSizeText.textContent = formatBytes(data.downloaded_bytes);
    } else if (data.status === "stopping") {
      liveSizeText.textContent = "To'xtatilmoqda, shu paytgacha yozilgani saqlanmoqda...";
    } else if (data.status === "merging") {
      liveSizeText.textContent = "Fayl yakunlanmoqda...";
    } else if (data.status === "finished") {
      clearInterval(livePollInterval);
      livePollInterval = null;
      liveRecordingWrap.classList.add("hidden");
      liveOptions.classList.remove("hidden");
      liveStartBtn.classList.remove("hidden");
      liveAudioBtn.classList.remove("hidden");
      liveStartBtn.disabled = false;
      liveAudioBtn.disabled = false;
      liveFileLink.href = `${base}/api/file/${jobId}`;
      liveFileLink.classList.remove("hidden");
    } else if (data.status === "error") {
      clearInterval(livePollInterval);
      livePollInterval = null;
      showLiveError(data.error || "Efirni yozib olishda xatolik yuz berdi");
      liveRecordingWrap.classList.add("hidden");
      liveOptions.classList.remove("hidden");
      liveStartBtn.classList.remove("hidden");
      liveAudioBtn.classList.remove("hidden");
      liveStartBtn.disabled = false;
      liveAudioBtn.disabled = false;
    }
  }, 1000);
}

// ---------------------------------------------------------------------------
// Transkript qidiruv
// ---------------------------------------------------------------------------

const TRANSCRIPT_EMPTY_DEFAULT_MSG = "Hech narsa topilmadi. Boshqa so'z bilan urinib ko'ring.";
// `blocked` javobda true bo'lganda ko'rsatiladi — bo'sh natija so'z
// transkriptlarda umuman yo'qligini emas, YouTube ba'zi videolarni
// tekshirishni vaqtincha bloklaganini bildiradi (qayta urinishga arziydi).
const TRANSCRIPT_EMPTY_BLOCKED_MSG = "Hech narsa topilmadi — YouTube ba'zi videolarni tekshirishni vaqtincha bloklagan bo'lishi mumkin. Bir necha daqiqadan so'ng qayta urinib ko'ring.";

function showTranscriptError(msg) {
  transcriptErrorMsgText.textContent = msg;
  transcriptErrorMsg.classList.remove("hidden");
}

function clearTranscriptError() {
  transcriptErrorMsg.classList.add("hidden");
}

// "N yil M oy oldin" inputlarini backend kutgan "YYYY-MM-DD" sanasiga
// aylantiradi. Ikkalasi ham bo'sh bo'lsa (chegara belgilanmagan) `null`
// qaytaradi — foydalanuvchi aniq kunni emas, taxminiy davrni kiritadi,
// shuning uchun kun doim oyning 1-kuni sifatida olinadi.
function transcriptAgoToISODate(yearsInput, monthsInput) {
  const years = parseInt(yearsInput.value, 10) || 0;
  const months = parseInt(monthsInput.value, 10) || 0;
  if (!yearsInput.value.trim() && !monthsInput.value.trim()) return null;
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - (years * 12 + months));
  return d.toISOString().slice(0, 10);
}

// Moslikni <mark> bilan ajratib ko'rsatadi — innerHTML/string interpolatsiya
// ATAYLAB ishlatilmaydi: bu matn YouTube subtitrlaridan keladi (ishonchsiz
// manba), shuning uchun DOM tugunlari to'g'ridan-to'g'ri (textContent bilan)
// quriladi — XSS ehtimoli umuman yo'q.
function renderHighlightedText(container, text, query) {
  container.textContent = "";
  const needle = query.toLowerCase();
  if (!needle) {
    container.appendChild(document.createTextNode(text));
    return;
  }
  const lower = text.toLowerCase();
  let cursor = 0;
  while (true) {
    const foundAt = lower.indexOf(needle, cursor);
    if (foundAt === -1) {
      container.appendChild(document.createTextNode(text.slice(cursor)));
      break;
    }
    container.appendChild(document.createTextNode(text.slice(cursor, foundAt)));
    const mark = document.createElement("mark");
    mark.textContent = text.slice(foundAt, foundAt + query.length);
    container.appendChild(mark);
    cursor = foundAt + query.length;
  }
}

function renderTranscriptResults(results, query) {
  transcriptResults.innerHTML = "";
  results.forEach((r) => {
    const card = document.createElement("a");
    card.className = "transcript-result";
    card.href = r.url;
    card.target = "_blank";
    card.rel = "noopener noreferrer";

    const head = document.createElement("div");
    head.className = "transcript-result-head";

    const time = document.createElement("span");
    time.className = "transcript-result-time";
    time.textContent = formatDuration(r.start_time);

    const title = document.createElement("span");
    title.className = "transcript-result-title";
    title.textContent = r.video_title;

    head.appendChild(time);
    head.appendChild(title);

    const channel = document.createElement("p");
    channel.className = "transcript-result-channel";
    channel.textContent = r.channel_name;

    const text = document.createElement("p");
    text.className = "transcript-result-text";
    renderHighlightedText(text, r.text, query);

    card.appendChild(head);
    card.appendChild(channel);
    card.appendChild(text);
    transcriptResults.appendChild(card);
  });
}

transcriptSearchBtn.addEventListener("click", async () => {
  const query = transcriptQueryInput.value.trim();
  if (!query) {
    showTranscriptError("Iltimos, qidiriladigan so'z yoki iborani kiriting.");
    return;
  }
  const channelId = transcriptChannelInput.value.trim();
  // "Necha vaqt oldindan" (uzoqroq o'tmish) -> published_after (pastki
  // chegara); "Necha vaqt oldingacha" (yaqinroq) -> published_before
  // (yuqori chegara). Masalan "3 yil oldindan — 1 yil oldingacha".
  const publishedAfter = transcriptAgoToISODate(transcriptYearsFromInput, transcriptMonthsFromInput);
  const publishedBefore = transcriptAgoToISODate(transcriptYearsToInput, transcriptMonthsToInput);
  if (publishedAfter && publishedBefore && publishedAfter > publishedBefore) {
    showTranscriptError("\"Necha vaqt oldindan\" qiymati \"necha vaqt oldingacha\"dan uzoqroq o'tmishda bo'lishi kerak.");
    return;
  }

  clearTranscriptError();
  transcriptEmptyMsg.classList.add("hidden");
  transcriptResults.innerHTML = "";
  transcriptProgressWrap.classList.remove("hidden");
  setProgress(transcriptProgressFill, 0, true);
  transcriptSearchBtn.disabled = true;
  transcriptSearchBtn.classList.add("loading");

  try {
    const res = await fetch("/api/transcript/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query, channel_id: channelId || null,
        published_after: publishedAfter, published_before: publishedBefore,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");

    if (data.results.length === 0) {
      transcriptEmptyMsg.textContent = data.blocked ? TRANSCRIPT_EMPTY_BLOCKED_MSG : TRANSCRIPT_EMPTY_DEFAULT_MSG;
      transcriptEmptyMsg.classList.remove("hidden");
    } else {
      renderTranscriptResults(data.results, query);
    }
  } catch (e) {
    showTranscriptError(e.message);
  } finally {
    transcriptProgressWrap.classList.add("hidden");
    transcriptSearchBtn.disabled = false;
    transcriptSearchBtn.classList.remove("loading");
  }
});

// ---------------------------------------------------------------------------
// Klip -> manba stream ("bu shorts qaysi streamdan olingan?")
// ---------------------------------------------------------------------------

function showFindSourceError(msg) {
  findSourceErrorMsgText.textContent = msg;
  findSourceErrorMsg.classList.remove("hidden");
}

// Natija kartasi DOM tugunlari orqali quriladi (innerHTML emas) — matn
// YouTube subtitrlaridan keladi, ya'ni ishonchsiz manba.
function renderFindSourceResult(data) {
  findSourceResult.textContent = "";

  if (!data.found) {
    const msg = document.createElement("p");
    msg.className = "hint";
    msg.textContent =
      "Ishonchli manba topilmadi — ehtimol manba stream hali indekslanmagan. " +
      "Bunday holatda taxminiy (ehtimol xato) javob ATAYLAB ko'rsatilmaydi. " +
      "Yuqoridagi qidiruv orqali kanalni kerakli davr bilan indekslab, qayta urinib ko'ring.";
    findSourceResult.appendChild(msg);
    return;
  }

  const m = data.match;
  const card = document.createElement("a");
  card.className = "transcript-result";
  card.href = m.url;
  card.target = "_blank";
  card.rel = "noopener noreferrer";

  const head = document.createElement("div");
  head.className = "transcript-result-head";

  const time = document.createElement("span");
  time.className = "transcript-result-time";
  time.textContent = formatDuration(m.start_time);

  const title = document.createElement("span");
  title.className = "transcript-result-title";
  title.textContent = m.video_title || m.video_id;

  head.appendChild(time);
  head.appendChild(title);

  const channel = document.createElement("p");
  channel.className = "transcript-result-channel";
  channel.textContent = m.published_at ? `${m.channel_name} — ${m.published_at}` : m.channel_name;

  const detail = document.createElement("p");
  detail.className = "transcript-result-text";
  detail.textContent = data.confident
    ? `Mos kelgan so'zlar: ${m.matched_terms.slice(0, 10).join(", ")}`
    : `Ishonch past (ball: ${m.score.toFixed(1)}) — bu taxminiy moslik bo'lishi mumkin. ` +
      `Mos so'zlar: ${m.matched_terms.slice(0, 10).join(", ")}`;

  card.appendChild(head);
  card.appendChild(channel);
  card.appendChild(detail);
  findSourceResult.appendChild(card);
}

findSourceBtn.addEventListener("click", async () => {
  const clipUrl = findSourceUrlInput.value.trim();
  if (!clipUrl) {
    showFindSourceError("Iltimos, klip (Shorts) havolasini kiriting.");
    return;
  }
  const channelId = transcriptChannelInput.value.trim();

  findSourceErrorMsg.classList.add("hidden");
  findSourceResult.textContent = "";
  findSourceProgressWrap.classList.remove("hidden");
  setProgress(findSourceProgressFill, 0, true);
  findSourceBtn.disabled = true;
  findSourceBtn.classList.add("loading");

  try {
    const res = await fetch("/api/transcript/find-source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clip_url: clipUrl, channel_id: channelId || null }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");
    renderFindSourceResult(data);
  } catch (e) {
    showFindSourceError(e.message);
  } finally {
    findSourceProgressWrap.classList.add("hidden");
    findSourceBtn.disabled = false;
    findSourceBtn.classList.remove("loading");
  }
});
