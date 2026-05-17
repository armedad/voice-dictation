"""Tests for platform_mac.chord_vk — macOS virtual key / modifier mapping."""

from __future__ import annotations

import pytest

from platform_mac.chord_vk import (
    chord_to_carbon_vk_and_modifiers,
    cmdKey,
    controlKey,
    optionKey,
    shiftKey,
)


class TestChordToCarbonVkAndModifiers:
    def test_cmd_shift_d(self) -> None:
        vk, mods = chord_to_carbon_vk_and_modifiers(
            {"modifiers": ["cmd", "shift"], "key": "d"}
        )
        assert vk == 0x02  # ANSI D
        assert mods == cmdKey | shiftKey

    def test_ctrl_alt_comma(self) -> None:
        vk, mods = chord_to_carbon_vk_and_modifiers(
            {"modifiers": ["ctrl", "alt"], "key": "comma"}
        )
        assert vk == 0x2B
        assert mods == controlKey | optionKey

    def test_f5(self) -> None:
        vk, mods = chord_to_carbon_vk_and_modifiers(
            {"modifiers": ["cmd"], "key": "f5"}
        )
        assert vk == 0x60
        assert mods == cmdKey

    def test_digit_1(self) -> None:
        vk, _ = chord_to_carbon_vk_and_modifiers(
            {"modifiers": ["ctrl"], "key": "1"}
        )
        assert vk == 0x12

    def test_null_chord_raises(self) -> None:
        with pytest.raises(ValueError, match="null"):
            chord_to_carbon_vk_and_modifiers(None)  # type: ignore[arg-type]

    def test_unsupported_key_raises(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            chord_to_carbon_vk_and_modifiers(
                {"modifiers": ["cmd"], "key": "not_a_real_key"}
            )

    def test_f16_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="F16"):
            chord_to_carbon_vk_and_modifiers({"modifiers": ["cmd"], "key": "f16"})
