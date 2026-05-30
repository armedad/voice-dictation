# Eval case reference — voice dictation MVP

Paths relative to `coding/voice-dictation-mvp/`.

## Cleanup case (`evals/cases/cleanup/<id>.json`)

Auto-discovered: one `*.json` per file, no registry. Pytest: `test_cleanup[<id>]`.

### Field matrix

| Field | Required | Default if omitted | Used by |
|-------|----------|-------------------|---------|
| `id` | yes | — | pytest id; must match filename |
| `raw_transcript` | yes | — | cleanup input |
| `vocabulary` | no | TWIM default user vocab | cleanup prompts |
| `user_instructions` | no | TWIM default user instructions | cleanup prompts |
| `expected_contains` | no | no checks | checklist |
| `expected_not_contains` | no | no checks | checklist |
| `skip_geval` | no | `false` | GEval step |
| `min_geval_score` | no | `0.5` from `evals/eval_config.json` | GEval threshold |
| `expected_output` | no | — | GEval golden (not checklist) |
| `geval_criteria_augment` | no | — | appended to shared rubric |
| `geval_criteria` | no | shared file | replaces shared rubric (rare) |

### Intake → skip behavior

| User says | Agent action |
|-----------|----------------|
| `skip` / `none` / `decline` on optional field | Omit key or use `null` per repo style |
| `default` on `min_geval_score` | Omit key (harness uses 0.5) |
| `default` on STT `max_wer` | Omit key (uses `stt_max_wer_default` 0.25) |
| `skip` on must-not list | Use `["```", "Here is", "Sure,"]` |

### Skeleton — checklist + GEval (full)

```json
{
  "id": "my_case",
  "raw_transcript": "um so like paste messy transcript here",
  "vocabulary": "TermOne\nTermTwo",
  "user_instructions": "Use sentence case.",
  "expected_contains": ["TermOne"],
  "expected_not_contains": ["```", "Here is", "Sure,"],
  "expected_output": "Optional ideal cleaned line.",
  "geval_criteria_augment": "Optional per-case judge notes.",
  "min_geval_score": 0.5,
  "skip_geval": false
}
```

### Skeleton — checklist only

```json
{
  "id": "my_checklist_case",
  "raw_transcript": "um what is the capital of france",
  "expected_contains": ["?"],
  "expected_not_contains": ["paris"],
  "skip_geval": true
}
```

### Skeleton — minimal (GEval only, uncommon)

```json
{
  "id": "my_geval_case",
  "raw_transcript": "messy input",
  "skip_geval": false,
  "geval_criteria_augment": "Case-specific judge rules."
}
```

---

## STT case (`evals/cases/stt/`)

- Audio: `evals/cases/stt/<wav>`
- Registry: `evals/cases/stt/metadata.json` → `cases[]`
- Pytest: `test_stt_wer[<id>]` (`@pytest.mark.slow`)

### Field matrix

| Field | Required | Default if omitted |
|-------|----------|-------------------|
| `id` | yes | — |
| `wav` | yes | filename in `stt/` |
| `reference_transcript` | yes | golden text for WER |
| `max_wer` | no | `stt_max_wer_default` (0.25) in `evals/eval_config.json` |

### metadata.json append pattern

```json
{
  "cases": [
    {
      "id": "my_clip",
      "wav": "my_clip.wav",
      "reference_transcript": "exact words spoken",
      "max_wer": 0.2
    }
  ]
}
```

Merge new object into existing `cases` array; preserve other entries.

---

## Shared rubric (edit separately)

`evals/geval_cleanup_criteria.json`:

```json
{
  "criteria": "Score 1.0 (pass) when ACTUAL OUTPUT is an acceptable dictation rewrite of INPUT: ..."
}
```

Per-case `geval_criteria_augment` appends to this text unless `geval_criteria` replaces it.

---

## Models (do not set in case JSON)

| Role | Source |
|------|--------|
| Cleanup (SUT) | `twim/users/_default/settings.json` → `default_model` |
| GEval judge | `evals/eval_config.json` → `judge.model` |
| STT | `evals/eval_config.json` → `transcription.model` |

Pull models: `./install-tests.sh` or `./install.sh`.
