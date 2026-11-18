import json
import random

import chat_spikes as cs
import db


def quiet_then_burst(burst_at=600, base=3, burst=14, seconds=900, seed=1):
    rnd = random.Random(seed)
    counts = {}
    for t in range(0, seconds, 10):
        n = base + rnd.choice([-1, 0, 0, 1])
        if burst_at <= t < burst_at + 60:
            n = burst + rnd.choice([-2, 0, 2])
        counts[t] = max(0, n)
    return counts


def test_channel_and_vod_parsing():
    assert cs.channel_from_url("https://www.twitch.tv/DarkViperAU247") == "darkviperau247"
    assert cs.channel_from_url("https://www.twitch.tv/popout/somebody/chat") == "somebody"
    assert cs.channel_from_url("https://www.twitch.tv/videos/123") is None
    assert cs.channel_from_url("https://youtube.com/watch?v=x") is None
    assert cs.vod_id_from_url("https://www.twitch.tv/videos/987654") == "987654"
    assert cs.is_twitch("https://www.twitch.tv/somebody")
    assert not cs.is_twitch("https://example.com/somebody")


def test_is_privmsg():
    assert cs.is_privmsg(b":a!a@a.tmi.twitch.tv PRIVMSG #chan :hello\r\n")
    assert not cs.is_privmsg(b":tmi.twitch.tv 001 justinfan1 :Welcome\r\n")
    assert not cs.is_privmsg("PING :tmi.twitch.tv")


def test_bucketize_ignores_junk():
    assert cs.bucketize([0, 3, 9.9, 10, 25, -1, "x", None, float("nan")]) == {0: 3, 10: 1, 20: 1}


def test_burst_is_found_near_where_it_started():
    counts = quiet_then_burst()
    spikes = cs.find_spikes(counts, 0, 900)
    assert len(spikes) == 1
    sp = spikes[0]
    assert 570 <= sp["onset"] <= 620
    assert sp["ratio"] >= 2.5 and sp["count"] > 30


def test_steady_chat_has_no_burst():
    rnd = random.Random(3)
    counts = {t: 5 + rnd.choice([-2, -1, 0, 1, 2]) for t in range(0, 1800, 10)}
    assert cs.find_spikes(counts, 0, 1800) == []


def test_quiet_channel_noise_is_not_a_burst():
    counts = {t: (1 if t % 40 == 0 else 0) for t in range(0, 900, 10)}
    counts[500] = 3
    assert cs.find_spikes(counts, 0, 900) == []


def test_close_bursts_merge_and_far_ones_stay_apart():
    counts = quiet_then_burst(burst_at=300)
    for t in range(400, 460, 10):
        counts[t] = 15
    for t in range(800, 860, 10):
        counts[t] = 20
    spikes = cs.find_spikes(counts, 0, 900)
    assert len(spikes) == 2


def test_window_opens_before_burst_and_stays_in_band():
    counts = quiet_then_burst()
    win = cs.clip_windows(cs.find_spikes(counts, 0, 900), 900, lead=25, tail=15,
                          min_len=15, max_len=60)
    assert len(win) == 1
    w = win[0]
    assert abs((w["onset"] - w["start"]) - 25) < 1e-6
    assert w["end"] > w["peak"] and 15 <= w["end"] - w["start"] <= 60


def test_window_clamped_at_start_and_end():
    sp = [{"onset": 5.0, "peak": 20.0, "end": 40.0, "ratio": 4, "count": 80, "score": 30}]
    w = cs.clip_windows(sp, 100, lead=25, min_len=15)[0]
    assert w["start"] == 0.0
    sp = [{"onset": 95.0, "peak": 97.0, "end": 100.0, "ratio": 4, "count": 80, "score": 30}]
    w = cs.clip_windows(sp, 100, lead=25, min_len=15)[0]
    assert w["end"] == 100.0 and w["end"] - w["start"] >= 15


def test_overlapping_windows_keep_the_stronger():
    sp = [{"onset": 100.0, "peak": 110.0, "end": 130.0, "ratio": 3, "count": 40, "score": 10},
          {"onset": 130.0, "peak": 140.0, "end": 160.0, "ratio": 6, "count": 90, "score": 50}]
    win = cs.clip_windows(sp, 1000, lead=25, tail=15)
    assert len(win) == 1 and win[0]["score"] == 50


def test_clean_windows_drops_untrusted_values():
    raw = [{"start": "10", "end": "50", "onset": 30, "peak": 35, "ratio": 3, "count": 9},
           {"start": "x", "end": 5}, {"start": 0, "end": float("inf")}, "junk",
           {"start": 5, "end": 6}, {"start": 200, "end": 300}]
    out = cs.clean_windows(raw, duration=250)
    assert [(w["start"], w["end"]) for w in out] == [(10.0, 50.0), (200.0, 250.0)]
    assert cs.clean_windows("nope") == []


def test_load_windows_reads_file_and_survives_garbage(tmp_path):
    p = tmp_path / "w.json"
    p.write_text(json.dumps([{"start": 1, "end": 40}]))
    assert cs.load_windows(str(p))[0]["end"] == 40.0
    p.write_text("not json")
    assert cs.load_windows(str(p)) == []
    assert cs.load_windows(str(tmp_path / "missing.json")) == []


def test_options_from_env_clamps():
    assert cs.options_from_env({}) == (cs.DEFAULT_LEAD, cs.DEFAULT_TAIL, cs.DEFAULT_RATIO)
    assert cs.options_from_env({"CHAT_SPIKE_LEAD": "999"})[0] == 60.0
    assert cs.options_from_env({"CHAT_SPIKE_RATIO": "0"})[2] == 1.2
    assert cs.options_from_env({"CHAT_SPIKE_LEAD": "x"})[0] == cs.DEFAULT_LEAD


def test_counts_accumulate_in_sqlite_and_feed_windows():
    stream = "live:test-accumulate"
    base = 10_000_000
    db.chat_add(stream, {base + t: n for t, n in quiet_then_burst().items()})
    db.chat_add(stream, {base + 600: 1})
    got = db.chat_series(stream, base, base + 900)
    assert got[base + 600] > quiet_then_burst()[600]
    win = cs.windows_for_range(stream, base, base + 900, duration=900)
    assert len(win) == 1 and 0 <= win[0]["start"] < 600


def test_later_chunk_uses_history_before_it():
    stream = "live:test-history"
    base = 20_000_000
    db.chat_add(stream, {base + t: n for t, n in quiet_then_burst(burst_at=600).items()})
    win = cs.windows_for_range(stream, base + 480, base + 900, duration=420)
    assert len(win) == 1
    assert 60 <= win[0]["onset"] <= 140


def test_chat_json_counts(tmp_path):
    p = tmp_path / "chat.json"
    p.write_text(json.dumps({"comments": [{"content_offset_seconds": 1.0},
                                          {"content_offset_seconds": 12.5},
                                          {"content_offset_seconds": 13.0}, {"x": 1}, 5]}))
    assert cs.counts_from_chat_json(str(p)) == {0: 1, 10: 2}


def test_vod_chat_goes_through_the_cli_once(tmp_path, monkeypatch):
    calls = []
    cli = tmp_path / "cli.cmd"
    cli.write_text("")
    monkeypatch.setattr(cs, "cli_path", lambda: str(cli))

    def fake_run(cmd, **kw):
        calls.append(cmd)
        out = cmd[cmd.index("-o") + 1]
        times = [t * 10 + i for t in range(60) for i in range(3)]
        times += [t + i * 0.1 for t in range(300, 360) for i in range(8)]
        with open(out, "w") as f:
            json.dump({"comments": [{"content_offset_seconds": x} for x in times]}, f)
    monkeypatch.setattr(cs.subprocess, "run", fake_run)
    win = cs.vod_windows("https://www.twitch.tv/videos/424242", 0)
    assert len(win) == 1 and win[0]["start"] < 300
    assert cs.vod_windows("https://www.twitch.tv/videos/424242", 0)
    assert len(calls) == 1 and calls[0][1] == "chatdownload"
    assert cs.vod_windows("https://www.twitch.tv/somebody", 0) == []
