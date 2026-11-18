import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
from collections import OrderedDict

import subtitles

_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
POSITIONS = ("top", "middle", "bottom")
EFFECTS = ("none", "glow", "pop", "box", "highlight")
FONTS = ("Anton", "Montserrat ExtraBold", "Verdana", "Arial", "Impact", "Helvetica",
         "Georgia", "Courier New", "Noto Serif")
SAMPLE_TEXT = "this is the moment chat went absolutely crazy and nobody saw it coming"
MAX_TEXT = 140


def _num(value, lo, hi, default, integer=False):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:
        return default
    v = max(lo, min(hi, v))
    return int(round(v)) if integer else round(v, 2)


def _color(value, default):
    return value.upper() if isinstance(value, str) and _COLOR.match(value) else default


def resolve(raw):
    raw = raw if isinstance(raw, dict) else {}
    name = str(raw.get("preset") or "default").strip().lower()
    base = dict(subtitles.CAPTION_PRESETS.get(name) or subtitles.CAPTION_PRESETS["default"])
    font = str(raw.get("font_name", base.get("font_name", "Anton")))
    font = subtitles._sanitize_font_name(font)[:40]
    effect = raw.get("effect", base.get("effect", "pop"))
    position = raw.get("position", "bottom")
    return {
        "preset": name if name in subtitles.CAPTION_PRESETS else "default",
        "position": position if position in POSITIONS else "bottom",
        "font_name": font,
        "font_size": _num(raw.get("font_size", base.get("font_size")), 10, 200, 44, True),
        "font_color": _color(raw.get("font_color", base.get("font_color")), "#FFFFFF"),
        "highlight_color": _color(raw.get("highlight_color", base.get("highlight_color")), "#FFE500"),
        "border_color": _color(raw.get("border_color", base.get("border_color")), "#000000"),
        "border_width": _num(raw.get("border_width", base.get("border_width")), 0, 10, 4, True),
        "bg_color": _color(raw.get("bg_color", base.get("bg_color")), "#000000"),
        "bg_opacity": _num(raw.get("bg_opacity", base.get("bg_opacity", 0.0)), 0.0, 1.0, 0.0),
        "effect": effect if effect in EFFECTS else "none",
        "base_opacity": _num(raw.get("base_opacity", base.get("base_opacity", 1.0)), 0.1, 1.0, 1.0),
        "uppercase": bool(raw.get("uppercase", base.get("uppercase", False))),
        "reveal": bool(raw.get("reveal", base.get("reveal", False))),
        "shadow": _num(raw.get("shadow", base.get("shadow", 0)), 0, 6, 0, True),
        "max_chars": _num(raw.get("max_chars", base.get("max_chars")), 1, 40, 16, True),
        "max_duration": _num(raw.get("max_duration", base.get("max_duration", 1.4)), 0.4, 5.0, 1.4),
    }


def job_style(env=None):
    env = os.environ if env is None else env
    text = str(env.get("CAPTION_STYLE_JSON") or "").strip()
    if not text:
        return dict(subtitles.AUTO_CAPTION_STYLE)
    try:
        s = resolve(json.loads(text))
    except ValueError:
        return dict(subtitles.AUTO_CAPTION_STYLE)
    return {"style": "karaoke", "alignment": s["position"], "font_name": s["font_name"],
            "font_size": s["font_size"], "font_color": s["font_color"],
            "highlight_color": s["highlight_color"], "border_color": s["border_color"],
            "border_width": s["border_width"], "effect": s["effect"],
            "base_opacity": s["base_opacity"], "uppercase": s["uppercase"],
            "max_chars": s["max_chars"], "max_duration": s["max_duration"],
            "bg_color": s["bg_color"], "bg_opacity": s["bg_opacity"],
            "reveal": s["reveal"], "shadow": s["shadow"]}


def ass_options(style):
    return dict(
        max_chars=style["max_chars"], max_duration=style["max_duration"],
        alignment=style["alignment"], fontsize=style["font_size"],
        font_name=style["font_name"], font_color=style["font_color"],
        border_color=style["border_color"], border_width=style["border_width"],
        highlight_color=style["highlight_color"], effect=style["effect"],
        base_opacity=style["base_opacity"], uppercase=style["uppercase"],
        bg_color=style.get("bg_color", "#000000"), bg_opacity=style.get("bg_opacity", 0.0),
        reveal=style.get("reveal", False), shadow=style.get("shadow", 0))


WORD_SECONDS = 0.4
_cache = OrderedDict()
_cache_lock = threading.Lock()
_render_lock = threading.Lock()


def _sample_transcript(text):
    words = [w for w in " ".join(str(text or SAMPLE_TEXT).split())[:MAX_TEXT].split(" ") if w] \
        or SAMPLE_TEXT.split(" ")
    words = words[:24]
    entries = [{"word": " " + w, "start": round(i * WORD_SECONDS, 3),
                "end": round((i + 1) * WORD_SECONDS, 3)} for i, w in enumerate(words)]
    return {"language": "en", "segments": [{"start": 0.0, "end": entries[-1]["end"],
                                            "text": " ".join(words), "words": entries}]}, len(words)


def render_preview(raw_style, text=None, frames=6, width=540):
    style = job_style({"CAPTION_STYLE_JSON": json.dumps(resolve(raw_style))})
    transcript, n_words = _sample_transcript(text)
    frames = max(1, min(8, int(frames)))
    key = hashlib.sha1(json.dumps([style, transcript, frames, width], sort_keys=True).encode()).hexdigest()
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return list(_cache[key])
    height = int(width * 16 / 9)
    total = n_words * WORD_SECONDS
    step = max(WORD_SECONDS, total / frames)
    work = tempfile.mkdtemp(prefix="capprev_")
    try:
        ass = os.path.join(work, "p.ass")
        if not subtitles.generate_ass(transcript, 0.0, total + 0.5, ass, **ass_options(style)):
            return []
        vf = subtitles.subtitles_filter(ass)
        src = (f"gradients=s=1080x1920:c0=0x2f4466:c1=0x0b0e14:x0=0:y0=0:x1=1080:y1=1920:"
               f"d={total + 1:.2f}:r=10")
        pattern = os.path.join(work, "f%02d.jpg")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src,
               "-vf", f"setpts=PTS+0.15/TB,{vf},fps=1/{step:.3f},scale={width}:{height}",
               "-frames:v", str(frames), "-q:v", "4", pattern]
        with _render_lock:
            done = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
        if done.returncode != 0:
            raise RuntimeError(done.stderr.decode(errors="replace")[-300:])
        out = []
        for i in range(1, frames + 1):
            p = os.path.join(work, f"f{i:02d}.jpg")
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    out.append("data:image/jpeg;base64," + base64.b64encode(f.read()).decode())
    finally:
        for name in os.listdir(work):
            try:
                os.remove(os.path.join(work, name))
            except OSError:
                pass
        try:
            os.rmdir(work)
        except OSError:
            pass
    with _cache_lock:
        _cache[key] = out
        while len(_cache) > 32:
            _cache.popitem(last=False)
    return list(out)
