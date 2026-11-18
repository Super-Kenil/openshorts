# Local setup and work log

Context for a new chat: what was built on top of upstream OpenShorts in this fork, how it runs, and what is still open.

## How to run

- One command: `start-openshorts.cmd` (double-click or run from cmd).
  - Starts Ollama, the API (uvicorn :8000) and the dashboard (Vite :5173), each in its own window, skipping any already running.
  - Waits for the API, then opens `http://localhost:5173/#app`.
- Python via **uv only** (no `.venv`, no pip): `uv run --no-project --python 3.12 --with-requirements requirements-local-windows.lock --index https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match ...`. uv keeps the env in its cache.
- `requirements-local-windows.lock`: exact package set that is known to work (torch 2.11.0+cu128, av 18.1.0, ctranslate2 4.8.5, ...). The unpinned install drifted and broke faster-whisper before.
- `win_shims/` (on `PYTHONPATH` via the start script): Windows stand-ins for Linux-only bits, so repo code stays untouched:
  - `fcntl.py`: msvcrt-based `flock`.
  - `sitecustomize.py`: drops `preexec_fn` from `subprocess.Popen` (unsupported on Windows).
  - `resource.py`: `getrusage` from `os.times()`.
- Dashboard deps: `bun install` (the start script runs it on first launch). Use bun, not npm.
- Docker/WSL was broken on this machine, so everything runs natively on Windows.

## Hardware / models

- GPU: RTX 4070 SUPER, 12 GB. Gemma 4 12b uses ~11.6 GB at 16k context, so `MAX_CONCURRENT_JOBS=1`.
- LLM: Ollama `gemma4:12b`, thinking off. User env var `**OLLAMA_CONTEXT_LENGTH**=16384`.
- ASR: faster-whisper `small` on CPU (int8).
- Encoder: NVENC (`FFMPEG_ENCODER=auto`).

## `.env` (git-ignored)

```
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=gemma4:12b
LLM_API_KEY=
LLM_REASONING_EFFORT=none
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE=int8
TRANSCRIBE_BACKEND=whisper
FFMPEG_ENCODER=auto
MAX_CONCURRENT_JOBS=1
```

Optional: `WHISPER_MODEL_HI=<model>` to use a different Whisper model for Hindi (still `small` for now), `LIVE_MIN_FREE_GB` (default 5), `LIVE_CHUNK_MINUTES` (default 20), `LLM_VISION_FRAME_WIDTH` (default 512), `LLM_MAX_TOKENS`.

## What was built

### 1. Fully local AI (no Gemini key needed)
- `llm_backend.py`: OpenAI-compatible backend with image parts (`images=[label, jpeg_bytes, ...]`), `LLM_VISION_MODEL`, `LLM_REASONING_EFFORT` (sent as `reasoning_effort`), `LLM_MAX_TOKENS`.
- Local-vision paths (Gemma via Ollama) in `layout_picker.py`, `screencast_layout.py`, `burned_subtitles.py`, `hook_grounding.py`, and silent-footage clipping in `main.py` (`_visual_pass_local`: timestamped stills every 10 s at 512 px per 600 s stretch).
- Gemma loops on unbounded JSON arrays unless frames are labelled and the exact count is stated in the prompt; `max_tokens` is the safety net.
- Dashboard: no Gemini/Upload-Post key modal when the server reports a local LLM (`keysMissing` in `App.jsx`).

### 2. Language picker
- English / Hindi / Auto-detect buttons in the Clip Generator (also used by live links).
- `/api/process` `language` field -> `main.py --language` -> `SOURCE_LANGUAGE` -> Whisper `language=` and optional `WHISPER_MODEL_<LANG>` (`subtitles.source_language()`, `transcribe_backends`).
- Hindi captions burn correctly in Devanagari (font fallback works).

### 3. Text watermark
- `text_watermark.py`: settings in `output/.text_watermark.json` (text, opacity, size % of height, 9 positions), rendered as an ASS overlay so Hindi shapes correctly. Applied per clip in `main.py` after captions, as a `branded_<ts>_<file>` copy announced via `CLIP_READY`.
- Endpoints `GET/PUT /api/watermark` live in `live_clipper.py` (kept out of `text_watermark.py` so `main.py`'s import graph never reaches `app.py`; `test_audit_hardening` enforces that).
- UI: Settings card (`TextWatermarkCard.jsx`) and under the video preview in the subtitle editor (`WatermarkControls.jsx`, `WatermarkOverlay.jsx`). Applying subtitles sends `watermark` to `/api/subtitle`, which saves it as the global setting and burns it.
- Limits: subtitle styles rendered in the browser (non-karaoke Remotion path) don't get it. Re-editing a clip's captions/hook later re-renders from the clean original.

### 4. Live stream clipping (`live_clipper.py`)
- Paste a live (or upcoming) link in the Clip Generator: `/api/live/probe` detects it and the form shows save folder (+ folder browser `/api/live/browse`), "start from the latest moment" checkbox or a start time, chunk length (default 20 min) and the usual advanced options.
- Recording: yt-dlp extracts the HLS URLs (inside `ssrf_guard`), ffmpeg `-c copy` segment muxer writes fragmented-MP4 chunks straight into `<folder>/live_<stamp>_<id>/chunks/` (written once, readable even if cut off).
- Each finished chunk is submitted in place to `/api/process` (in-process via `httpx.ASGITransport`, upload slot with `in_place: True`, so no copy). Clips are copied next to the chunk folder as `partNNN_clipN_<title>.mp4` + `.json`; the chunk is deleted once clipped (failed or unclipped chunks are kept).
- File names: Hindi titles are romanized to Hinglish by Gemma (`romanize()`), ASCII only; the JSON keeps the original title plus `title_roman`.
- States: scheduled, waiting (stream not live yet), recording, paused, ended, finished, stopped, error. Pause stops recording and holds the queue; stop cancels the running clip job (`app.cancel_job`) and keeps unclipped chunks.
- Survives restarts: `output/.live_sessions.json` registry + `session.json` per session; on startup (`resume_all` in `app.py` lifespan) sessions resume, partial chunks are recovered from disk, a leftover recorder is killed by saved PID.
- Several streams at once: each records in parallel; chunks from all streams and normal videos share one FIFO job queue, one clipping job at a time (Gemma/VRAM bound), so streams take turns instead of waiting for a whole stream to end.
- Low disk (< `LIVE_MIN_FREE_GB`) auto-pauses recording.
- UI: the Clip Generator's own processing view (`LiveSessionPanel.jsx`: controls, playable recordings, session log) with clips as normal `ResultCard`s on the right. Running sessions are listed on the start screen after "New project". The old separate Live tab was removed.

### 5. Other
- Clip length band 2 s to 180 s (`clip_selection.clip_duration_bounds`, `/api/process`, MCP schema, form inputs).
- `app.cancel_job(job_id)`: cancels a queued or running job (tree-kill on Windows).
- Tests added: `tests/test_live_clipper.py`, `tests/test_text_watermark.py`, extra cases in `tests/test_llm_backend.py`, updated `tests/test_generation_controls.py`.

## Known state / caveats

- Pre-existing test failures on Windows (cp1252 file reads, missing cloud-only `jwt`); run with `PYTHONUTF8=1` to clear the encoding ones. `test_gemini_retry` fails only because `.env` sets `LLM_BASE_URL`.
- `bun run lint` has 10 pre-existing errors (none in the new files); `bun run build` passes.
- Whisper `small` is weak on Hindi; looking for a better small Hindi model.
- Twitch live works (tested on a live channel: records, clips). Chat-burst clipping verified by unit tests and a live run, but that channel's chat was near silent, so the real-burst path is untested on live data.
- The `llm_backend.py` module docstring is stale (says frame stages stay on Gemini).
- Repo is public: keep hosts, IPs, personal paths and metrics out of code, docs and commits.
- Nothing in this fork's latest local changes is committed: `start-openshorts.cmd`, `requirements-local-windows.lock`, `win_shims/`, `dashboard/bun.lock`, this file.

## Chat-burst clipping, caption preview, SQLite (added later)

- `tools/twitchdownloader/` (git-ignored): TwitchDownloaderCLI 1.56.5 from github.com/lay295/TwitchDownloader. Used for a Twitch VOD's chat (`chat_spikes.download_vod_chat`). VOD video still comes from yt-dlp.
- `chat_spikes.py`: chat messages counted per 10 s into SQLite. Live: anonymous read-only Twitch chat connection (`ChatCounter`, counts only). A burst = next 30 s at least 2.5x (sensitivity low/medium/high = 3.5/2.5/1.8) the median of the previous 6 min. Clip opens 20-30 s (default 25) before the burst began, ends 15 s after its peak. `main._chat_pick`: bounds from chat, title/hook from the model. No bursts: normal AI picking.
- Clip Generator form, Twitch links: "clip where chat bursts" card. Captions: "captions look" card with a live preview rendered by the real caption burner (`/api/caption-preview`), style sent per job as `CAPTION_STYLE_JSON`.
- `data/openshorts.db` (git-ignored): settings (caption style, language, layout, hook, save folder, chunk length, delete-recordings, chat options), live session registry, chat counts. Stays in the browser: sign-in, API keys, tutorial/nudge flags, editor UI state.
- "delete each recording after it is clipped" checkbox (default on) in the live form.
- If a job dies with `0xC0000142` or yt-dlp says ffmpeg is missing, the API was started from a windowless background shell; start it with `start-openshorts.cmd`.
