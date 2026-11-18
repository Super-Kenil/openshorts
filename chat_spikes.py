import asyncio
import json
import math
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import time
from statistics import median

import db

BUCKET = 10
HOT = 3
HISTORY = 36
MIN_HISTORY = 6
MIN_MESSAGES = 10
MERGE_GAP = 60.0
DEFAULT_RATIO = 2.5
DEFAULT_LEAD = 25.0
DEFAULT_TAIL = 15.0

_CHANNEL = re.compile(r"^[A-Za-z0-9_]{1,25}$")
_HERE = os.path.dirname(os.path.abspath(__file__))
_HOSTS = ("twitch.tv", "www.twitch.tv", "m.twitch.tv")
_RESERVED = {"videos", "directory", "downloads", "jobs", "turbo", "settings", "p", "search",
             "friends", "subscriptions", "wallet", "drops", "inventory", "u", "popout", "embed"}


def channel_from_url(url):
    from urllib.parse import urlparse
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return None
    if (parsed.hostname or "").lower() not in _HOSTS:
        return None
    parts = [p for p in (parsed.path or "").split("/") if p]
    if parts and parts[0].lower() in ("popout", "embed") and len(parts) > 1:
        parts = parts[1:]
    if not parts or parts[0].lower() in _RESERVED or not _CHANNEL.match(parts[0]):
        return None
    return parts[0].lower()


def vod_id_from_url(url):
    import twitch_signals
    return twitch_signals.parse_vod_id(url)


def is_twitch(url):
    return channel_from_url(url) is not None or vod_id_from_url(url) is not None


def is_privmsg(line):
    if isinstance(line, bytes):
        return b" PRIVMSG #" in line
    return " PRIVMSG #" in str(line)


def bucketize(offsets, bucket=BUCKET):
    out = {}
    for t in offsets:
        try:
            t = float(t)
        except (TypeError, ValueError):
            continue
        if t < 0 or math.isnan(t):
            continue
        key = int(t // bucket * bucket)
        out[key] = out.get(key, 0) + 1
    return out


def find_spikes(counts, start, end, ratio=DEFAULT_RATIO, bucket=BUCKET):
    n = int((end - start) // bucket)
    if n <= MIN_HISTORY:
        return []
    s = [counts.get(int(start + i * bucket), 0) for i in range(n)]
    ratio = max(1.2, float(ratio))
    hot_idx = []
    meta = {}
    for i in range(MIN_HISTORY, n):
        prev = s[max(0, i - HISTORY):i]
        base = max(median(prev), sum(prev) / len(prev) * 0.6, 0.5)
        window = s[i:i + HOT]
        if len(window) < HOT:
            break
        cur = sum(window) / HOT
        if (sum(window) >= MIN_MESSAGES and cur >= base * ratio
                and cur - base >= 3 * math.sqrt(base / HOT)):
            hot_idx.append(i)
            meta[i] = (cur / base, base)
    events = []
    for i in hot_idx:
        if events and i <= events[-1]["last"] + 1:
            events[-1]["last"] = i
            events[-1]["ratio"] = max(events[-1]["ratio"], meta[i][0])
        else:
            events.append({"first": i, "last": i, "ratio": meta[i][0]})
    out = []
    for e in events:
        first = e["first"]
        base = meta[first][1]
        onset_i = next((j for j in range(first, min(first + HOT, n)) if s[j] >= base * ratio), first)
        stop_i = min(n, e["last"] + HOT)
        peak_i = max(range(first, stop_i), key=lambda j: s[j])
        out.append({"onset": float(start + onset_i * bucket), "peak": float(start + peak_i * bucket),
                    "end": float(start + stop_i * bucket), "ratio": round(e["ratio"], 2),
                    "count": int(sum(s[first:stop_i]))})
    merged = []
    for sp in out:
        if merged and sp["onset"] - merged[-1]["end"] < MERGE_GAP:
            m = merged[-1]
            if sp["ratio"] > m["ratio"]:
                m["peak"] = sp["peak"]
            m["end"] = max(m["end"], sp["end"])
            m["ratio"] = max(m["ratio"], sp["ratio"])
            m["count"] += sp["count"]
        else:
            merged.append(dict(sp))
    for m in merged:
        m["score"] = round(m["ratio"] * math.sqrt(max(1, m["count"])), 2)
    return merged


def clip_windows(spikes, duration, lead=DEFAULT_LEAD, tail=DEFAULT_TAIL,
                 min_len=15.0, max_len=60.0, limit=None):
    duration = float(duration or 0)
    lead = max(0.0, float(lead))
    chosen = []
    for sp in sorted(spikes or [], key=lambda x: -x.get("score", 0)):
        if limit and len(chosen) >= limit:
            break
        start = max(0.0, sp["onset"] - lead)
        end = max(sp["peak"] + BUCKET, sp["onset"]) + float(tail)
        if duration:
            end = min(end, duration)
        if end - start < min_len:
            end = start + min_len
            if duration and end > duration:
                end = duration
                start = max(0.0, end - min_len)
        if end - start > max_len:
            end = start + max_len
        if end - start < 2.0:
            continue
        if any(start < c["end"] and end > c["start"] for c in chosen):
            continue
        chosen.append({"start": round(start, 3), "end": round(end, 3),
                       "onset": sp["onset"], "peak": sp["peak"], "ratio": sp["ratio"],
                       "count": sp["count"], "score": sp.get("score", 0)})
    return sorted(chosen, key=lambda c: c["start"])


def clean_windows(raw, duration=None):
    out = []
    if not isinstance(raw, list):
        return out
    for w in raw[:50]:
        if not isinstance(w, dict):
            continue
        try:
            start, end = float(w["start"]), float(w["end"])
            onset = float(w.get("onset", start))
            peak = float(w.get("peak", onset))
            ratio = float(w.get("ratio", 0))
            count = int(w.get("count", 0))
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(x) for x in (start, end, onset, peak, ratio)):
            continue
        start = max(0.0, start)
        if duration:
            end = min(end, float(duration))
        if end - start < 2.0:
            continue
        out.append({"start": round(start, 3), "end": round(end, 3), "onset": onset,
                    "peak": peak, "ratio": ratio, "count": count})
    return sorted(out, key=lambda c: c["start"])


def load_windows(path, duration=None):
    try:
        with open(path, encoding="utf-8") as f:
            return clean_windows(json.load(f), duration)
    except (OSError, ValueError):
        return []


def options_from_env(env=None):
    env = os.environ if env is None else env

    def num(name, default, lo, hi):
        try:
            return max(lo, min(hi, float(env.get(name, default))))
        except (TypeError, ValueError):
            return default
    return (num("CHAT_SPIKE_LEAD", DEFAULT_LEAD, 5, 60),
            num("CHAT_SPIKE_TAIL", DEFAULT_TAIL, 5, 60),
            num("CHAT_SPIKE_RATIO", DEFAULT_RATIO, 1.2, 10))


def windows_for_range(stream, start, end, duration=None, ratio=DEFAULT_RATIO,
                      lead=DEFAULT_LEAD, tail=DEFAULT_TAIL, min_len=15.0, max_len=60.0,
                      limit=None):
    lo = max(0, start - HISTORY * BUCKET)
    counts = db.chat_series(stream, lo, end)
    if not counts:
        return []
    lo = max(lo, min(counts))
    spikes = find_spikes(counts, lo, end, ratio=ratio)
    db.chat_spikes_save(stream, spikes)
    inside = [dict(sp, onset=sp["onset"] - start, peak=sp["peak"] - start, end=sp["end"] - start)
              for sp in spikes if start - HOT * BUCKET < sp["onset"] < end]
    return clip_windows(inside, duration if duration else end - start, lead=lead, tail=tail,
                        min_len=min_len, max_len=max_len, limit=limit)


class ChatCounter:

    HOST, PORT = "irc.chat.twitch.tv", 6697

    def __init__(self, channel, stream, note=None):
        if not _CHANNEL.match(channel or ""):
            raise ValueError("bad channel name")
        self.channel = channel.lower()
        self.stream = stream
        self.note = note or (lambda msg: None)
        self.pending = {}
        self.total = 0
        self.connected = False
        self._task = None
        self._stop = False

    def start(self):
        self._stop = False
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        await self._flush(final=True)

    def _count(self):
        t = int(time.time() // BUCKET * BUCKET)
        self.pending[t] = self.pending.get(t, 0) + 1
        self.total += 1

    async def _flush(self, final=False):
        now = int(time.time() // BUCKET * BUCKET)
        done = {t: n for t, n in self.pending.items() if final or t < now}
        for t in done:
            self.pending.pop(t, None)
        if done:
            try:
                await asyncio.to_thread(db.chat_add, self.stream, done)
            except Exception as e:
                self.note(f"chat counts not saved: {e}")

    async def _flusher(self):
        while True:
            await asyncio.sleep(BUCKET)
            await self._flush()

    async def _run(self):
        flusher = asyncio.create_task(self._flusher())
        delay = 2.0
        try:
            while not self._stop:
                try:
                    await self._session()
                    delay = 2.0
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if self.connected:
                        self.note(f"chat connection lost ({type(e).__name__}), retrying")
                    self.connected = False
                await asyncio.sleep(delay)
                delay = min(60.0, delay * 2)
        finally:
            flusher.cancel()

    async def _session(self):
        ctx = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.HOST, self.PORT, ssl=ctx), timeout=20)
        try:
            nick = f"justinfan{int(time.time()) % 80000 + 10000}"
            writer.write(f"NICK {nick}\r\nJOIN #{self.channel}\r\n".encode())
            await writer.drain()
            if not self.connected:
                self.note(f"counting chat messages in #{self.channel}")
            self.connected = True
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=420)
                if not line:
                    raise ConnectionError("closed")
                if line.startswith(b"PING"):
                    writer.write(b"PONG :tmi.twitch.tv\r\n")
                    await writer.drain()
                elif is_privmsg(line):
                    self._count()
        finally:
            writer.close()


def cli_path():
    explicit = os.environ.get("TWITCH_DOWNLOADER_CLI", "").strip()
    names = ("TwitchDownloaderCLI.exe", "TwitchDownloaderCLI")
    for cand in ([explicit] if explicit else []) + [os.path.join(_HERE, "tools", "twitchdownloader", n) for n in names]:
        if cand and os.path.isfile(cand):
            return cand
    return shutil.which("TwitchDownloaderCLI")


def counts_from_chat_json(path, bucket=BUCKET):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    comments = data.get("comments") if isinstance(data, dict) else None
    return bucketize((c.get("content_offset_seconds") for c in comments or [] if isinstance(c, dict)),
                     bucket)


def download_vod_chat(vod_id, timeout=3600):
    stream = f"vod:{vod_id}"
    if db.chat_has(stream):
        return True
    cli = cli_path()
    if not cli or not str(vod_id).isdigit():
        return False
    work = tempfile.mkdtemp(prefix="vodchat_")
    try:
        out = os.path.join(work, "chat.json")
        subprocess.run([cli, "chatdownload", "-u", str(vod_id), "-o", out, "--collision", "Overwrite"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout,
                       cwd=work)
        if not os.path.isfile(out):
            return False
        db.chat_replace(stream, counts_from_chat_json(out))
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


def vod_windows(url, duration, min_len=15.0, max_len=60.0, limit=None, env=None):
    vod = vod_id_from_url(url)
    if not vod or not download_vod_chat(vod):
        return []
    lead, tail, ratio = options_from_env(env)
    dur = float(duration or 0)
    if not dur:
        counts = db.chat_series(f"vod:{vod}", 0, 10 ** 9)
        dur = (max(counts) + BUCKET) if counts else 0
    return windows_for_range(f"vod:{vod}", 0, dur, duration=dur or None, ratio=ratio,
                             lead=lead, tail=tail, min_len=min_len, max_len=max_len, limit=limit)
