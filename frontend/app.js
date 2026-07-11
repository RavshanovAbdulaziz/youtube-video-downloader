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
const audioSection = document.getElementById("audio-section");
const audioLangSelect = document.getElementById("audio-lang-select");
const downloadAudioBtn = document.getElementById("download-audio-btn");
const progressWrap = document.getElementById("progress-wrap");
const progressFill = document.getElementById("progress-fill");
const progressText = document.getElementById("progress-text");
const fileLink = document.getElementById("file-link");
const separateSection = document.getElementById("separate-section");
const separateEngineSelect = document.getElementById("separate-engine-select");
const separateLangSelect = document.getElementById("separate-lang-select");
const separateBtn = document.getElementById("separate-btn");
const separateProgressWrap = document.getElementById("separate-progress-wrap");
const separateProgressFill = document.getElementById("separate-progress-fill");
const separateProgressText = document.getElementById("separate-progress-text");
const separateLinks = document.getElementById("separate-links");
const speechFileLink = document.getElementById("speech-file-link");
const backgroundFileLink = document.getElementById("background-file-link");

let currentInfo = null;

function showError(msg) {
  errorMsgText.textContent = msg;
  errorMsg.classList.remove("hidden");
}

function clearError() {
  errorMsg.classList.add("hidden");
}

function formatDuration(sec) {
  if (!sec) return "";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function setProgress(fillEl, percent, indeterminate) {
  fillEl.classList.toggle("indeterminate", !!indeterminate);
  fillEl.style.width = indeterminate ? "100%" : `${percent}%`;
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
  audioSection.classList.toggle("hidden", data.audio_tracks.length === 0);
  separateSection.classList.toggle("hidden", data.audio_tracks.length === 0);
  updateVideoLangVisibility();

  progressWrap.classList.add("hidden");
  fileLink.classList.add("hidden");
  separateProgressWrap.classList.add("hidden");
  separateLinks.classList.add("hidden");
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
  setProgress(progressFill, 0, false);
  progressText.textContent = "Boshlanmoqda...";
  setButtonsDisabled(true);

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");
    pollProgress(data.job_id);
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

  try {
    const res = await fetch("/api/separate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: urlInput.value.trim(),
        audio_format_id: separateLangSelect.value,
        title: currentInfo.title,
        engine: separateEngineSelect.value,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");
    pollSeparateProgress(data.job_id);
  } catch (e) {
    showError(e.message);
    separateBtn.disabled = false;
  }
});

function pollSeparateProgress(jobId) {
  const interval = setInterval(async () => {
    const res = await fetch(`/api/separate/progress/${jobId}`);
    const data = await res.json();
    const pct = data.percent != null ? data.percent : 0;

    if (data.status === "downloading") {
      setProgress(separateProgressFill, pct, false);
      separateProgressText.textContent = `Audio yuklab olinmoqda: ${pct}%`;
    } else if (data.status === "separating") {
      setProgress(separateProgressFill, pct, false);
      separateProgressText.textContent = `Ajratilmoqda: ${pct}% (bir necha daqiqa vaqt olishi mumkin)`;
    } else if (data.status === "finished") {
      clearInterval(interval);
      setProgress(separateProgressFill, 100, false);
      separateProgressText.textContent = "Tayyor!";
      speechFileLink.href = `/api/separate/file/${jobId}/speech`;
      backgroundFileLink.href = `/api/separate/file/${jobId}/background`;
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

function pollProgress(jobId) {
  const interval = setInterval(async () => {
    const res = await fetch(`/api/progress/${jobId}`);
    const data = await res.json();

    if (data.status === "downloading") {
      const pct = data.percent != null ? data.percent : 0;
      setProgress(progressFill, pct, false);
      const speed = data.speed ? `${(data.speed / 1024 / 1024).toFixed(2)} MB/s` : "";
      progressText.textContent = `Yuklanmoqda: ${pct}% ${speed}`;
    } else if (data.status === "merging") {
      setProgress(progressFill, 100, true);
      progressText.textContent = "Video va audio birlashtirilmoqda...";
    } else if (data.status === "finished") {
      clearInterval(interval);
      setProgress(progressFill, 100, false);
      progressText.textContent = "Tayyor!";
      fileLink.href = `/api/file/${jobId}`;
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
