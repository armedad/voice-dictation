"""Whisper model ids accepted by faster-whisper (local CTranslate2)."""

# Sizes / checkpoints commonly used with faster-whisper; see upstream docs.
FASTER_WHISPER_MODEL_IDS: tuple[str, ...] = (
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large-v1",
    "large-v2",
    "large-v3",
    "large",
    "distil-large-v2",
    "distil-large-v3",
)
