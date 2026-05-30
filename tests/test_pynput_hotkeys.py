"""Tests for platform_win.pynput_hotkeys — chord to pynput combo strings."""

from __future__ import annotations

import pytest

from platform_win.pynput_hotkeys import chord_to_pynput_combo


class TestChordToPynputCombo:
    def test_ctrl_shift_r(self) -> None:
        chord = {"modifiers": ["shift", "ctrl"], "key": "r"}
        assert chord_to_pynput_combo(chord) == "<ctrl>+<shift>+r"

    def test_cmd_maps_to_pynput_cmd_token(self) -> None:
        chord = {"modifiers": ["cmd"], "key": "a"}
        assert chord_to_pynput_combo(chord) == "<cmd>+a"

    def test_escape_alias(self) -> None:
        chord = {"modifiers": ["ctrl"], "key": "escape"}
        assert chord_to_pynput_combo(chord) == "<ctrl>+<esc>"

    def test_f12(self) -> None:
        chord = {"modifiers": ["alt"], "key": "f12"}
        assert chord_to_pynput_combo(chord) == "<alt>+<f12>"

    def test_empty_key_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            chord_to_pynput_combo({"modifiers": ["ctrl"], "key": ""})
