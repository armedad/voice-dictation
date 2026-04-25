"""PortAudio input device enumeration via sounddevice (ai-frame dictation + validation)."""
from __future__ import annotations

from typing import Any


def _hostapi_name(apis: Any, ha_idx: int) -> str:
    try:
        if isinstance(apis, (list, tuple)) and 0 <= ha_idx < len(apis):
            ha = apis[ha_idx]
            if isinstance(ha, dict):
                return str(ha.get("name") or "")
    except Exception:
        pass
    return ""


def list_input_devices() -> tuple[list[dict[str, Any]], dict[str, Any] | None, str | None]:
    """
    Return ``(input_devices, system_default_device_or_none, error_or_none)``.

    Each input device dict includes: ``index``, ``name``, ``hostapi_name``,
    ``default_samplerate``, ``max_input_channels``.
    """
    try:
        import sounddevice as sd
    except ImportError:
        return [], None, "sounddevice is not installed."

    try:
        apis = sd.query_hostapis()
        raw_list = sd.query_devices()
        if not isinstance(raw_list, (list, tuple)):
            return [], None, "Unexpected PortAudio device list."

        devices: list[dict[str, Any]] = []
        for i, dev in enumerate(raw_list):
            if not isinstance(dev, dict):
                continue
            if int(dev.get("max_input_channels") or 0) < 1:
                continue
            ha_idx = int(dev.get("hostapi", -1))
            devices.append(
                {
                    "index": i,
                    "name": str(dev.get("name") or "Unknown"),
                    "hostapi_name": _hostapi_name(apis, ha_idx),
                    "default_samplerate": dev.get("default_samplerate"),
                    "max_input_channels": int(dev.get("max_input_channels") or 0),
                }
            )

        sys_d: dict[str, Any] | None = None
        try:
            d = sd.query_devices(kind="input")
            if isinstance(d, dict):
                ha_idx = int(d.get("hostapi", -1))
                raw_idx = d.get("index")
                idx: int | None = int(raw_idx) if isinstance(raw_idx, int) else None
                if idx is None:
                    try:
                        raw = sd.default.device[0]
                        idx = int(raw) if raw is not None and int(raw) >= 0 else None
                    except Exception:
                        idx = None
                sys_d = {
                    "index": idx,
                    "name": str(d.get("name") or "Unknown"),
                    "hostapi_name": _hostapi_name(apis, ha_idx),
                    "default_samplerate": d.get("default_samplerate"),
                }
        except Exception:
            sys_d = None

        return devices, sys_d, None
    except Exception as e:
        return [], None, str(e)


def valid_input_indices() -> set[int]:
    devices, _, err = list_input_devices()
    if err:
        return set()
    return {int(d["index"]) for d in devices}
