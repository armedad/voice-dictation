"""STT regression: Word Error Rate vs golden reference transcripts."""

from __future__ import annotations

import asyncio

import jiwer
import pytest

from evals.helpers import load_eval_config, load_stt_cases, normalize_for_wer, run_stt_only

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("case", load_stt_cases(), ids=lambda c: c["id"])
def test_stt_wer_within_threshold(case: dict, eval_config: dict) -> None:
    wav_path = case["wav_path"]
    assert wav_path.is_file(), f"Missing fixture WAV: {wav_path}"

    hypothesis = asyncio.run(run_stt_only(wav_path, cfg=eval_config))
    ref = normalize_for_wer(case["reference_transcript"])
    hyp = normalize_for_wer(hypothesis)

    wer = jiwer.wer(ref, hyp)
    max_wer = float(case.get("max_wer", eval_config.get("stt_max_wer_default", 0.25)))

    assert wer <= max_wer, (
        f"WER {wer:.3f} > {max_wer:.3f} for case {case['id']!r}\n"
        f"  reference: {case['reference_transcript']!r}\n"
        f"  hypothesis: {hypothesis!r}"
    )
