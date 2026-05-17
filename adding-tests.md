# Adding tests and evals

This project has two layers of automated checks:

| Layer | Location | Speed | Needs |
|--------|-----------|--------|--------|
| **Unit / API tests** | `tests/` | Fast (mocks, no ML) | Python venv + `requirements-dev.txt` |
| **AI evals** | `evals/` | Slower (Whisper, Ollama) | `requirements-eval.txt`, local models, Ollama running |

**Install once:** `./install-tests.sh` (or `install-tests.bat` on Windows). Same `CHEEAPPS_VENV` convention as `install.sh`; path is saved in `.voice_dictation_venv`.

**Run everything:** `./run-tests.sh` — runs `tests/` then `evals/`, checks Ollama when evals are included.

See also: [README — AI evals](README.md#ai-evals-regression), [`evals/eval_config.json`](evals/eval_config.json), `./run-tests.sh --help`.

---

## Unit and API tests (`tests/`)

Use these for deterministic logic: orchestrator behavior, settings parsing, hotkeys, Twim API routes, storage, etc.

### Where to put code

- New test file: `tests/test_<area>.py`
- Shared fixtures: `tests/conftest.py`, `tests/helpers.py`
- `pytest.ini` sets `testpaths = tests` for default discovery; `./run-tests.sh` also passes `evals/` explicitly.

### Patterns in this repo

- **Async orchestrator:** `pytest.mark.asyncio` (via `asyncio_mode = auto` in `pytest.ini`); patch adapters with `unittest.mock` / `pytest` monkeypatch. See `tests/test_orchestrator.py`.
- **HTTP API:** `AsyncClient` + ASGI transport fixtures in `tests/conftest.py`. See `tests/test_api_*.py`.
- **Config shape:** `example_voice_config` / `voice_config` fixtures load `config/example-model-settings.json`.

### Example: new unit test

```python
# tests/test_my_feature.py
def test_something(voice_config):
    assert voice_config.cleanup.model == "llama3.2:3b"
```

### Run unit tests only

```bash
./run-tests.sh --unit-only
pytest tests/ -q
pytest tests/test_orchestrator.py -k test_cancel -v
```

No Ollama or Whisper required.

---

## AI evals (`evals/`)

Regression checks against **real** local models (not mocks):

1. **STT** — audio → faster-whisper → compare to reference with **WER** ([jiwer](https://github.com/j-hyphen/jiwer)).
2. **Cleanup** — messy transcript → Ollama cleanup → **substring guardrails** (deterministic) + optional **GEval** judge (DeepEval + separate Ollama model; rubric in JSON, optional golden `expected_output` per case).

Config: [`evals/eval_config.json`](evals/eval_config.json)

| Role | Default model | Purpose |
|------|----------------|--------|
| Transcription | `base` (faster-whisper) | STT evals |
| Cleanup (system under test) | `llama3.2:3b` | Rewrite dictation |
| Judge (GEval only) | `qwen2.5:3b-instruct` | Score cleanup quality |

Override `OLLAMA_HOST` / `OLLAMA_PORT` if needed. `./install-tests.sh` pulls missing Ollama models when the server is reachable.

---

## Adding an STT eval case

### 1. Add audio + metadata

1. Place a short WAV under `evals/cases/stt/` (e.g. `my_clip.wav`).
2. Register it in `evals/cases/stt/metadata.json`:

```json
{
  "id": "my_clip",
  "wav": "my_clip.wav",
  "reference_transcript": "the exact words spoken in the clip",
  "max_wer": 0.2
}
```

| Field | Meaning |
|--------|---------|
| `id` | Unique case id (pytest name) |
| `wav` | Filename under `evals/cases/stt/` |
| `reference_transcript` | Golden text for WER |
| `max_wer` | Max allowed word error rate (0–1). Omit to use `stt_max_wer_default` in `eval_config.json` (0.25). |

Cases are loaded by `load_stt_cases()` in `evals/helpers.py`. No code change needed when you only add JSON + WAV.

### 2. How it runs

- Test: `evals/test_stt_wer.py`
- Marker: `@pytest.mark.slow` (local Whisper load)
- Skipped with: `./run-tests.sh --skip-slow` or `pytest -m "not slow"`

### 3. Run STT evals

```bash
pytest evals/test_stt_wer.py -v
pytest evals/ -m slow -v
./run-tests.sh --evals-only --skip-geval    # STT + cleanup gates, no GEval
```

---

## Adding a cleanup eval case

Read this like a recipe.

**You add:** one JSON file in `evals/cases/cleanup/` (a “story card”).  
**You may edit:** [`evals/geval_cleanup_criteria.json`](evals/geval_cleanup_criteria.json) when judge rules should apply to **every** story.  
**You do not:** register the case elsewhere or edit Python for a normal new scenario.

### The big picture

Cleanup model rewrites messy speech. One pytest per case — **`test_cleanup[<id>]`** — runs cleanup **once**, then applies two **teachers** to that same output:

| Teacher | Step in `test_cleanup` | How it decides pass/fail | Configured in |
|---------|------------------------|---------------------------|---------------|
| **Checklist** | Always (unless you only care about GEval — still runs first) | Substrings must / must not appear | `expected_contains`, `expected_not_contains` on the case JSON |
| **GEval judge** | After checklist, if `skip_geval` is false and GEval is enabled | AI scores against a rubric (and optionally a golden line) | `evals/geval_cleanup_criteria.json` + fields on the case JSON |

### Files involved

| Path | Role |
|------|------|
| `evals/cases/cleanup/<id>.json` | One scenario: input, checklist, GEval options |
| `evals/geval_cleanup_criteria.json` | Shared GEval rubric (`criteria` string) |
| `evals/test_cleanup.py` | Test code (usually leave alone) |
| `evals/eval_config.json` | Cleanup + judge **models** (not rubric text) |

---

### Step 1 — Create the story card

1. Copy e.g. [`evals/cases/cleanup/filler_rewrite.json`](evals/cases/cleanup/filler_rewrite.json).
2. Save as `evals/cases/cleanup/<your_id>.json`.
3. Set `"id"` (unique) and `"raw_transcript"` (messy dictation input).

Every `*.json` in that folder is loaded automatically — no registry.

---

### Step 2 — Checklist teacher (deterministic)

Add word lists to the **same** case JSON:

```json
"expected_contains": ["Sarah", "day"],
"expected_not_contains": ["```", "Here is", "Sure,"]
```

Inside `test_cleanup[<id>]`, after one cleanup call: checks `expected_contains` / `expected_not_contains`.

| Field | Purpose |
|--------|---------|
| `expected_contains` | Each string must appear in the cleaned output |
| `expected_not_contains` | Each string must not appear |

**Examples:** `filler_rewrite.json` (checklist + GEval). `question_not_answered.json` (checklist only; GEval off via `skip_geval`).

This is **not** DeepEval’s `expected_output` — it is a simple substring guardrail.

---

### Step 3 — GEval judge (optional)

On the same case JSON:

```json
"skip_geval": false,
"min_geval_score": 0.5
```

| Field | Purpose |
|--------|---------|
| `skip_geval` | `false` = run GEval (default for most cases). `true` = checklist only. |
| `min_geval_score` | Judge score 0–1 must be ≥ this to pass (default from `eval_config.json`: `0.5`). |

Same `test_cleanup[<id>]`, same output: graded by `qwen2.5:3b-instruct` via [DeepEval GEval](https://docs.confident-ai.com/) when GEval is on.

#### 3a — Shared rubric (all cases)

Edit [`evals/geval_cleanup_criteria.json`](evals/geval_cleanup_criteria.json):

```json
{
  "criteria": "Score 1.0 (pass) when ACTUAL OUTPUT is an acceptable dictation rewrite of INPUT: ..."
}
```

That `criteria` text is the default “what good looks like” for every case that runs GEval.

#### 3b — Per-case rubric tweaks (optional)

On the **case** JSON:

| Field | Purpose |
|--------|---------|
| `geval_criteria_augment` | Extra sentences **appended** to the shared rubric (usual way to specialize one story). |
| `geval_criteria` | **Replace** the shared rubric for this case only (rare). `geval_criteria_augment` still appends if set. |

**Example:** `plain_text_only.json` uses `geval_criteria_augment` for “plain text only, no markdown.”

#### 3c — Golden answer for the judge (optional)

On the **case** JSON:

```json
"expected_output": "I need to send the report to Sarah by end of day."
```

| When set | What DeepEval receives |
|----------|-------------------------|
| Omitted | `INPUT` + `ACTUAL OUTPUT` + rubric |
| Present | `INPUT` + `ACTUAL OUTPUT` + **`EXPECTED OUTPUT`** + rubric |

The judge is told to treat `expected_output` as the reference cleaned line (same **meaning** as ACTUAL OUTPUT; wording may differ slightly). The harness appends a short note to the rubric when this field is set.

**Example:** `filler_rewrite.json` includes both checklist lists and `expected_output`.

**Important:** `expected_output` is only used by **GEval**. It does **not** run the checklist test. Use `expected_contains` / `expected_not_contains` for hard substring rules.

#### What GEval does *not* use

- `expected_contains` / `expected_not_contains` (checklist only)
- Fields on `evals/eval_config.json` except judge model URL/name/temperature

---

### Step 4 — Run tests

1. Ollama running (`127.0.0.1:11434`).
2. Models: `llama3.2:3b` (cleanup), `qwen2.5:3b-instruct` (judge). `./install-tests.sh` pulls missing tags.

```bash
pytest evals/test_cleanup.py -k <your_id> -v
pytest evals/test_cleanup.py -v
./run-tests.sh
./run-tests.sh --skip-geval    # checklist only (no GEval step)
pytest evals/ -m geval_judge -v   # cases with GEval (checklist still runs first)
```

**`./run-tests.sh` / `run-tests.bat` (default):** each run writes new files under `logs/test-runs/` — `pytest-<timestamp>.log` (full output) and `pytest-<timestamp>.xml` (JUnit). Use `--no-log` for terminal only.

Expect one pass line per case, e.g. `test_cleanup[no_markdown] PASSED`.

---

### Pick a recipe

| Goal | Case JSON | Shared `geval_cleanup_criteria.json` |
|------|-----------|--------------------------------------|
| Checklist only | `expected_*`, `skip_geval: true` | — |
| GEval rubric only | `skip_geval: false`, optional `geval_criteria_augment` | Edit `criteria` |
| GEval + golden line | Above + `expected_output` | Edit `criteria` |
| Full coverage (recommended) | `expected_*` + `skip_geval: false` + optional `expected_output` / augment | Edit `criteria` |

---

### Full example (both teachers + golden line + augment)

Save as `evals/cases/cleanup/no_markdown.json`:

```json
{
  "id": "no_markdown",
  "raw_transcript": "um okay so please draft an email to the team about the launch",
  "vocabulary": null,
  "user_instructions": null,
  "expected_contains": ["email", "team"],
  "expected_not_contains": ["```", "Here is", "Sure,"],
  "expected_output": "Please draft an email to the team about the launch.",
  "geval_criteria_augment": "OUTPUT must be plain text only: no markdown or assistant preamble.",
  "min_geval_score": 0.5,
  "skip_geval": false
}
```

### Checklist-only example

```json
{
  "id": "my_checklist_only_case",
  "raw_transcript": "um what is the capital of france",
  "vocabulary": null,
  "user_instructions": null,
  "expected_contains": ["?"],
  "expected_not_contains": ["paris"],
  "skip_geval": true
}
```

---

### Field cheat sheet (case JSON)

| Field | Required? | Checklist | GEval |
|--------|-----------|-----------|-------|
| `id` | yes | yes | yes |
| `raw_transcript` | yes | yes | yes (as INPUT) |
| `vocabulary` | no | yes | yes |
| `user_instructions` | no | yes | yes |
| `expected_contains` | no | yes | no |
| `expected_not_contains` | no | yes | no |
| `skip_geval` | no | — | `false` on, `true` off |
| `min_geval_score` | no | no | pass threshold |
| `expected_output` | no | no | golden line → DeepEval EXPECTED OUTPUT |
| `geval_criteria_augment` | no | no | extra rubric text for this case |
| `geval_criteria` | no | no | replace shared rubric for this case |

### Repo examples

| File | Checklist | GEval | `expected_output` | Notes |
|------|-----------|-------|---------------------|--------|
| `full_feature_example.json` | yes | on | yes | All case fields (uses `geval_criteria_augment`, not `geval_criteria`) |
| `filler_rewrite.json` | yes | on | yes | Checklist + golden line |
| `plain_text_only.json` | yes | on | no | `geval_criteria_augment` for plain text |
| `question_not_answered.json` | yes | off (`skip_geval`) | no | Augment present if you turn GEval on later |

---

## Environment variables

| Variable | Effect |
|----------|--------|
| `VOICE_DICTATION_SKIP_GEVAL=1` | Skip GEval judge tests (`./run-tests.sh --skip-geval` sets this) |
| `VOICE_DICTATION_RUN_GEVAL=0` | Same as skip |
| `OLLAMA_HOST` / `OLLAMA_PORT` | Ollama URL (default `127.0.0.1` / `11434`) |
| `VOICE_DICTATION_WHISPER_DEVICE` | Whisper device for install prefetch / STT (default `cpu`) |
| `VOICE_DICTATION_WHISPER_COMPUTE` | e.g. `int8` (default in install scripts) |

---

## Pytest markers

Registered in `evals/conftest.py`:

| Marker | Used for |
|--------|-----------|
| `slow` | STT / faster-whisper WER tests |
| `requires_ollama` | All cleanup evals |
| `geval_judge` | Cleanup cases that run the GEval step (checklist still runs first) |

Examples:

```bash
./run-tests.sh --skip-geval                                   # cleanup checklist, no GEval
pytest evals/ -m geval_judge -q
pytest evals/ -m "not slow" -q                              # same as --skip-slow
```

---

## Quick reference: commands

```bash
# Setup
./install-tests.sh
./install-tests.sh --skip-ollama    # skip model pulls

# Run
./run-tests.sh                      # tests/ + evals/ (Ollama required); logs to logs/test-runs/
./run-tests.sh --unit-only          # fast
./run-tests.sh --evals-only         # evals only
./run-tests.sh --skip-slow          # no Whisper WER
./run-tests.sh --skip-geval         # no GEval judge
./run-tests.sh --no-log             # terminal only, no log files
./run-tests.sh -- -k filler_rewrite --maxfail=1

# Direct pytest (after venv activate)
pytest tests/ evals/ -q
```

---

## Checklist: new cleanup eval

- [ ] Add `evals/cases/cleanup/<id>.json` with `id` and `raw_transcript`
- [ ] **Checklist:** `expected_contains` / `expected_not_contains` as needed
- [ ] **GEval:** `skip_geval: false` unless judge-only checklist is enough
- [ ] **GEval rubric:** edit `evals/geval_cleanup_criteria.json` and/or `geval_criteria_augment` on the case
- [ ] **GEval golden line (optional):** `expected_output` if you want ACTUAL vs EXPECTED comparison
- [ ] Ollama up; `llama3.2:3b` and `qwen2.5:3b-instruct` present (`ollama list`)
- [ ] Run `pytest evals/test_cleanup.py -k <id> -v`
- [ ] Run `./run-tests.sh` before merge

## Checklist: new STT eval

- [ ] Add WAV under `evals/cases/stt/`
- [ ] Add entry to `evals/cases/stt/metadata.json`
- [ ] Run `pytest evals/test_stt_wer.py -k <id> -v`
- [ ] Tune `max_wer` if the clip is noisy

## Checklist: new unit test

- [ ] Add or extend `tests/test_*.py`
- [ ] Mock external I/O (Ollama, Whisper, network)
- [ ] Run `./run-tests.sh --unit-only`
