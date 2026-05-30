"""Tests for core.hotkey_chord — chord JSON validation and display labels."""

from __future__ import annotations

import pytest

from core.hotkey_chord import (
    format_chord_display,
    normalize_chord,
    parse_chord_or_raise,
)


class TestNormalizeChord:
    def test_none_clears_chord(self) -> None:
        assert normalize_chord(None) is None

    def test_dedupes_and_sorts_modifiers(self) -> None:
        chord = {"modifiers": ["shift", "cmd", "shift", "cmd"], "key": "d"}
        assert normalize_chord(chord) == {
            "modifiers": ["cmd", "shift"],
            "key": "d",
        }

    def test_normalizes_key_case(self) -> None:
        chord = {"modifiers": ["ctrl"], "key": "Escape"}
        assert normalize_chord(chord)["key"] == "escape"

    def test_single_digit_key(self) -> None:
        chord = {"modifiers": ["ctrl"], "key": "0"}
        assert normalize_chord(chord) == {"modifiers": ["ctrl"], "key": "0"}

    def test_named_key_with_underscore(self) -> None:
        chord = {"modifiers": ["alt"], "key": "page_up"}
        assert normalize_chord(chord)["key"] == "page_up"

    @pytest.mark.parametrize(
        "bad",
        [
            "not-a-dict",
            {"modifiers": [], "key": "a"},
            {"modifiers": ["win"], "key": "a"},
            {"modifiers": ["cmd"], "key": ""},
            {"modifiers": ["cmd"], "key": "$"},
            {"modifiers": ["cmd"], "key": "a" * 30},
            {"modifiers": "cmd", "key": "a"},
        ],
    )
    def test_invalid_input_raises(self, bad: object) -> None:
        with pytest.raises(ValueError):
            normalize_chord(bad)

    def test_parse_chord_or_raise_matches_normalize(self) -> None:
        raw = {"modifiers": ["ctrl", "shift"], "key": "r"}
        assert parse_chord_or_raise(raw) == normalize_chord(raw)


class TestFormatChordDisplay:
    def test_empty_when_none(self) -> None:
        assert format_chord_display(None) == ""

    def test_letter_uppercased(self) -> None:
        chord = {"modifiers": ["cmd", "shift"], "key": "d"}
        assert format_chord_display(chord) == "Cmd+Shift+D"

    def test_named_key_title_case(self) -> None:
        chord = {"modifiers": ["alt"], "key": "escape"}
        assert format_chord_display(chord) == "Alt+Escape"

    def test_invalid_chord_label(self) -> None:
        assert format_chord_display({"modifiers": ["cmd"], "key": "!!!"}) == "(invalid hotkey)"
