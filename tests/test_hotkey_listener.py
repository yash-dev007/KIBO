from __future__ import annotations

from unittest.mock import patch

from src.system.hotkey_listener import HotkeyListener


def _listener() -> HotkeyListener:
    return HotkeyListener({"activation_hotkey": "ctrl+k", "clip_hotkey": "ctrl+alt+k"})


def test_stop_removes_only_registered_handles() -> None:
    listener = _listener()
    handles = {"ctrl+k": object(), "ctrl+alt+k": object()}

    with patch("src.system.hotkey_listener.keyboard.add_hotkey", side_effect=lambda h, cb: handles[h]), \
         patch("src.system.hotkey_listener.keyboard.remove_hotkey") as remove_hotkey, \
         patch("src.system.hotkey_listener.keyboard.unhook_all") as unhook_all:
        listener.start_listening()
        listener.stop()

    assert remove_hotkey.call_count == 2
    assert {call.args[0] for call in remove_hotkey.call_args_list} == set(handles.values())
    unhook_all.assert_not_called()
    assert listener._registered_handles == {}


def test_rebind_only_replaces_changed_hotkey() -> None:
    listener = _listener()
    handles = {
        "ctrl+k": "talk-old",
        "ctrl+alt+k": "clip-old",
        "ctrl+shift+k": "talk-new",
    }

    with patch("src.system.hotkey_listener.keyboard.add_hotkey", side_effect=lambda h, cb: handles[h]) as add_hotkey, \
         patch("src.system.hotkey_listener.keyboard.remove_hotkey") as remove_hotkey:
        listener.start_listening()
        listener.rebind(talk_hotkey="ctrl+shift+k")

    assert remove_hotkey.call_count == 1
    assert remove_hotkey.call_args.args[0] == "talk-old"
    assert add_hotkey.call_count == 3
    assert listener.is_registered("ctrl+shift+k") is True
    assert listener.is_registered("ctrl+alt+k") is True
    assert listener.is_registered("ctrl+k") is False


def test_registration_failure_emits_failed_hotkey() -> None:
    listener = _listener()
    failed: list[str] = []
    listener.registration_failed.connect(failed.append)

    def add_hotkey(hotkey, callback):
        if hotkey == "ctrl+k":
            raise RuntimeError("busy")
        return object()

    with patch("src.system.hotkey_listener.keyboard.add_hotkey", side_effect=add_hotkey):
        listener.start_listening()

    assert failed == ["ctrl+k"]
    assert listener.is_registered("ctrl+k") is False
    assert listener.is_registered("ctrl+alt+k") is True
