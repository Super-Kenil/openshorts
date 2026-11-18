import db


def test_settings_roundtrip_and_delete():
    db.set_setting("t.alpha", {"a": [1, 2], "b": "ü"})
    assert db.get_setting("t.alpha") == {"a": [1, 2], "b": "ü"}
    db.set_setting("t.alpha", False)
    assert db.get_setting("t.alpha") is False
    assert "t.alpha" in db.all_settings()
    db.delete_setting("t.alpha")
    assert db.get_setting("t.alpha", "gone") == "gone"


def test_live_registry():
    db.live_registry_set("abc", "D:/x")
    assert db.live_registry()["abc"] == "D:/x"
    db.live_registry_remove("abc")
    assert "abc" not in db.live_registry()


def test_chat_replace_overwrites():
    db.chat_add("t.stream", {10: 2})
    db.chat_replace("t.stream", {20: 5})
    assert db.chat_series("t.stream", 0, 100) == {20: 5}
