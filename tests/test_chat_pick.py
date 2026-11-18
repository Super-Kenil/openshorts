import main


WORDS = [{"w": f" w{i}", "s": float(i), "e": i + 0.8} for i in range(200)]


def fake_stage(client, model, items, build, schema, key, costs, label):
    build(items)
    return [{"source_window_id": items[0]["id"], "start": 90.0, "end": 95.0, "predicted_score": 88,
             "video_title_for_youtube_short": "T", "viral_hook_text": "H",
             "video_description_for_tiktok": "d", "video_description_for_instagram": "d",
             "why": ""}]


def test_chat_windows_set_the_bounds_and_the_model_only_the_copy(monkeypatch):
    monkeypatch.setattr(main, "_run_stage_split", fake_stage)
    windows = [{"start": 20.0, "end": 70.0, "onset": 45.0, "peak": 55.0, "ratio": 4.0, "count": 60},
               {"start": 120.0, "end": 170.0, "onset": 145.0, "peak": 150.0, "ratio": 3.0, "count": 40}]
    out = main._chat_pick(None, "m", "en", 200.0, windows, WORDS)
    first, second = out["shorts"]
    assert first["start"] <= 20.5 and first["end"] >= 69.0
    assert first["video_title_for_youtube_short"] == "T"
    assert second["video_title_for_youtube_short"] == "Chat went wild"
    assert second["start"] <= 120.5 and second["end"] >= 169.0
    assert first["chat_burst"]["onset"] == 45.0


def test_no_usable_window_returns_none(monkeypatch):
    monkeypatch.setattr(main, "_run_stage_split", fake_stage)
    assert main._chat_pick(None, "m", "en", 200.0, [{"start": 5.0, "end": 6.0, "onset": 5, "peak": 5}], WORDS) is None
