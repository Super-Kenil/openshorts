import json
import shutil

import pytest

import caption_style as cstyle
import subtitles


def test_resolve_defaults_match_the_default_preset():
    s = cstyle.resolve({})
    d = subtitles.AUTO_CAPTION_STYLE
    assert (s["font_name"], s["font_size"], s["effect"], s["uppercase"]) == (
        d["font_name"], d["font_size"], d["effect"], d["uppercase"])
    assert s["position"] == "bottom"


def test_resolve_clamps_and_drops_bad_values():
    s = cstyle.resolve({"font_size": 9999, "font_color": "red", "effect": "explode",
                        "position": "left", "border_width": -3, "base_opacity": 7,
                        "font_name": "Anton; Fontname=x,{evil}", "shadow": 99, "max_chars": 0})
    assert s["font_size"] == 200 and s["font_color"] == "#FFFFFF"
    assert s["effect"] == "none" and s["position"] == "bottom"
    assert s["border_width"] == 0 and s["base_opacity"] == 1.0
    assert "{" not in s["font_name"] and ";" not in s["font_name"] and "," not in s["font_name"]
    assert s["shadow"] == 6 and s["max_chars"] == 1


def test_preset_then_overrides():
    s = cstyle.resolve({"preset": "pill", "font_size": 60, "highlight_color": "#112233"})
    assert s["effect"] == "highlight" and s["font_size"] == 60 and s["highlight_color"] == "#112233"
    assert cstyle.resolve({"preset": "nope"})["preset"] == "default"
    assert cstyle.resolve("not a dict")["preset"] == "default"


def test_job_style_defaults_without_env_and_on_garbage():
    assert cstyle.job_style({}) == dict(subtitles.AUTO_CAPTION_STYLE)
    assert cstyle.job_style({"CAPTION_STYLE_JSON": "{broken"}) == dict(subtitles.AUTO_CAPTION_STYLE)


def test_job_style_reads_env_and_feeds_generate_ass(tmp_path):
    env = {"CAPTION_STYLE_JSON": json.dumps(cstyle.resolve(
        {"preset": "hormozi", "position": "middle", "font_size": 52}))}
    style = cstyle.job_style(env)
    assert style["alignment"] == "middle" and style["font_size"] == 52 and style["reveal"] is True
    words = [{"word": f" w{i}", "start": i * 0.4, "end": i * 0.4 + 0.4} for i in range(6)]
    transcript = {"segments": [{"start": 0, "end": 2.4, "text": "x", "words": words}]}
    out = tmp_path / "t.ass"
    assert subtitles.generate_ass(transcript, 0, 3, str(out), **cstyle.ass_options(style))
    assert "Dialogue" in out.read_text()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="no ffmpeg")
def test_preview_renders_real_frames():
    frames = cstyle.render_preview({"preset": "pill"}, "hello there chat", frames=3, width=270)
    assert len(frames) == 3 and all(f.startswith("data:image/jpeg;base64,") for f in frames)
    assert frames == cstyle.render_preview({"preset": "pill"}, "hello there chat", frames=3, width=270)
