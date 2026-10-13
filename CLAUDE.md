# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted YouTube/TikTok video downloader with a FastAPI backend, a
vanilla JS frontend (no build step), and an optional Telegram bot — all
sharing the same yt-dlp-based download core. Also bundles a "separate vocals
from background" AI feature (Demucs/UVR) and a YouTube transcript-search
subsystem. Runs either locally on Windows (packaged as a tray `.exe`) or on
a server via Docker. See `README.md` (in Uzbek) for full user-facing setup
and deployment docs (Oracle Cloud Always Free deployment, Telegram bot file
size limits, the local Bot API server option, etc.) — it's kept up to date
and worth reading before touching deployment-related code.

## Commands

All Python commands use the `py -3.14` launcher, not a bare `python`/`pip`
— this repo targets Python 3.14 specifically and that's what's installed
system-wide on the Windows dev machine.

```bash
cd backend

# Install/update dependencies
py -3.14 -m pip install -r requirements.txt

# Run the dev server (auto-reloads on file save, keeps console open)
py -3.14 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
# equivalent: ..\start_dev.bat

# Run the Telegram bot standalone (needs BOT_TOKEN in backend/.env)
py -3.14 bot.py
# equivalent: ..\start_bot.bat

# Tests (network-free, no AI libs required — everything is monkeypatched;
# whole suite runs in ~15-20s)
py -3.14 -m pip install pytest pytest-asyncio httpx   # one-time
py -3.14 -m pytest

# Run one file / one test
py -3.14 -m pytest tests/test_downloader_internals.py
py -3.14 -m pytest tests/test_downloader_internals.py::TestWithRetries::test_retries_on_transient_error -q
```

There is no linter/formatter configured in this repo.

Windows `.bat` launchers at the repo root (`setup.bat`, `start.bat`,
`start_dev.bat`, `start_bot.bat`, `stop.bat`, `build_exe.bat`,
`create_shortcut.bat`) wrap the above for non-technical end users; prefer
the raw commands above when iterating on code.

## Architecture

### Request flow and job pattern

`backend/main.py` is the FastAPI app: it serves the JSON API under `/api/*`
and also mounts `frontend/` as static files at `/` (single origin, no CORS
headaches in normal use). The frontend (`frontend/app.js`, plain JS, no
framework/build step) talks to these endpoints directly.

Every long-running operation (video/audio download, subtitle download, live
capture, audio separation, AI-stack install) follows the same shape: a
`start_X(...)` function creates a `job_id`, spawns a daemon `threading.Thread`
to do the real work, and returns immediately. Progress/result lives in a
module-level `dict` (`downloader.jobs`, `separator.jobs`, ...) guarded by a
lock, polled via a `get_progress`/`get_info`-style endpoint from the
frontend or bot. There is no database or task queue — job state is
in-memory only and lost on process restart.

### `backend/downloader.py` — the core

Everything yt-dlp-related funnels through `ydl_opts_ctx(extra: dict)`, a
context manager that centralizes: cookies (file or read-live-from-browser),
PO-token provider base URL, bundled ffmpeg/Node paths (packaged builds),
YouTube `player_client` ordering, and an optional outbound proxy. **This is
the one place to touch when changing global yt-dlp behavior** — `separator.py`
imports and reuses it rather than duplicating options.

Two non-obvious pieces of engineering in this file, both documented in long
comments at their definition sites — read those before changing this logic:

- **Byte-range clip downloading** (`_download_clip`, `_fetch_range`,
  `_sidx_plan`): YouTube's CDN randomly 403s when yt-dlp's normal downloader
  tries to *resume* a large (100+ MB) download after a dropped connection.
  So downloads (even full, non-clipped ones) are done here by manually
  fetching independent 8 MB `Range` requests via yt-dlp's own authenticated
  HTTP client, with a `sidx`-box parser to seek precisely into fragmented
  MP4 streams for clip start/end times without downloading the whole file.
- **TikTok reachability workarounds** (`_resolve_short_url`,
  `_deprioritize_blocked_curl_cffi_default`): TikTok short links
  (`vm./vt.tiktok.com`) need a real browser TLS fingerprint (`curl_cffi`) to
  resolve without being connection-reset. Separately, TikTok's WAF
  specifically blocks curl_cffi's *default* "latest Chrome" impersonation
  profile (returns a fake "Site Maintenance" 200 page), so on import this
  module reorders curl_cffi's internal target list to prefer Safari for
  wildcard impersonation requests. `PROXY_URL` (env `YTDLP_PROXY` or
  `config.json`'s `"proxy"`) exists because some ISPs SNI-block TikTok
  entirely regardless of TLS fingerprint — the only fix is routing around
  it.

`get_info(url)` is the single source of truth for what a frontend/bot can
offer for a given URL (resolutions, audio tracks/languages including
YouTube auto-dubs, subtitles, live status). It resolves TikTok short links
once and returns the resolved `url` in its response — callers (frontend,
bot) should use that resolved URL for subsequent download/subtitle/separate
calls instead of re-resolving the original short link every time.

### Other backend modules

- `separator.py` — Demucs/UVR vocal/background separation. Reuses
  `downloader.ydl_opts_ctx`/`_resolve_short_url`/retry helpers; own `jobs`
  dict and job pattern.
- `ai_setup.py` — lazily, automatically installs the optional PyTorch +
  Demucs + audio-separator stack into `paths.runtime_python_exe()`'s
  site-packages on first use of the separation feature (mirrors
  `install_ai.bat`'s command sequence but fully automatic, GPU
  auto-detected).
- `pot_server.py` — auto-launches a local bgutil PO-token provider
  subprocess on Windows (only when `YTDLP_POT_BASE_URL` isn't already set,
  e.g. Docker points it at the separate `pot-provider` container instead).
- `paths.py` — resolves writable data directories and reads/writes
  `config.json` (small persisted settings: bot token, GPU flag,
  `cookies_from_browser`, proxy, etc.). Supports two modes: running from
  source (paths relative to `backend/`) vs. a packaged desktop build
  (`APP_DATA_DIR` for writable data, `APP_RUNTIME_DIR` for bundled
  ffmpeg/Node/Python). All backend modules resolve paths through here
  rather than hardcoding them.
- `bot.py` + `bot_ui/` — Telegram bot (aiogram) front end over the same
  `downloader`/`separator` core. Has its own SSRF-protection host allowlist
  (`_is_supported_url` — currently YouTube + TikTok domains only) since
  yt-dlp's generic extractor will otherwise fetch almost any HTTP(S) URL,
  including internal/cloud-metadata addresses.
- `transcript/` — separate subsystem: "search spoken content across a
  YouTube channel or all of YouTube" (not video titles — actual
  transcript/subtitle text). `fetch.py` (YouTube Data API v3 + transcript
  fetching), `store.py` (SQLite persistence/indexing in
  `transcript_search.db`), `search.py` (matching/orchestration — the
  `_extract_matches()` function is the one place to swap in
  semantic/embedding search later), `api.py` (FastAPI router, mounted into
  `main.py` via `include_router`), `cli.py`. Needs `YOUTUBE_API_KEY` in
  `backend/.env`; degrades to "just this tab disabled" without it.
- `launcher/` (separate from `backend/`) — the desktop tray app
  (`tray_app.py`, pystray) used for the packaged `.exe` distribution; spawns
  and supervises the uvicorn server and bot as child processes, handles the
  first-run bot-token prompt (`token_dialog.py`).

### Why YouTube-hostile-network workarounds matter here

This project runs both on residential Windows machines and on cloud VMs
(Oracle Cloud Always Free is the documented recommendation in `README.md`).
YouTube aggressively blocks known cloud/datacenter IP ranges ("Sign in to
confirm you're not a bot"), which is why cookies, the bgutil PO-token
provider, and specific `player_client` ordering (see the long comment above
`opts["extractor_args"]` in `downloader.py`) all coexist as layered
mitigations — none of them alone is fully reliable. The Telegram bot in
particular is documented as intentionally run from a residential machine
rather than the cloud VM for this reason.

### Tests

`backend/tests/conftest.py` points `APP_DATA_DIR` at a fresh temp directory
and disables the PO-token server/network lookups **before any backend
module is imported** (import order matters — `paths.py` reads env vars at
import time). Tests never hit the network; yt-dlp/curl_cffi calls are
monkeypatched (see the `fake_extract`/`fake_curl`-style fixtures in
`tests/test_get_info_parsing.py` and `tests/test_resolve_short_url.py` for
the established pattern). Convention: one `TestSomething` class per
function/behavior under test, `test_*` methods with descriptive names.
