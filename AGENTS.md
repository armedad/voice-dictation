# Voice dictation MVP — agent guide

Instructions for AI agents working in this repo. **Do not duplicate** the full testing guide here; use the linked docs and scripts.

## Canonical docs

| Doc / script | Use for |
|--------------|---------|
| [`adding-tests.md`](adding-tests.md) | How to add unit tests, STT evals, cleanup eval cases (checklist + GEval, `expected_output`, rubric JSON) |
| [`README.md`](README.md#ai-evals-regression) | Install, Ollama, high-level eval overview |
| [`./run-tests.sh --help`](run-tests.sh) / [`run-tests.bat --help`](run-tests.bat) | All run flags (`--unit-only`, `--skip-geval`, `--skip-slow`, `--no-log`, pytest passthrough) |
| [`./install-tests.sh`](install-tests.sh) / [`install-tests.bat`](install-tests.bat) | Test venv, `requirements-dev.txt` + `requirements-eval.txt`, Whisper prefetch, Ollama model pulls |
| [`evals/eval_config.json`](evals/eval_config.json) | STT/cleanup/judge models and thresholds |

## Running tests (agents)

**Working directory:** `coding/voice-dictation-mvp/`

**Prerequisites**

1. Test harness installed once: `./install-tests.sh` (venv path in `.voice_dictation_venv` or `CHEEAPPS_VENV`).
2. For `evals/`: Ollama running on `127.0.0.1:11434` with eval models (`llama3.2:3b`, `qwen2.5:3b-instruct`). `run-tests.sh` **exits with an error** if Ollama is down when evals are included.

**Default command**

```bash
./run-tests.sh
```

Runs `tests/` + `evals/` (unit/API, STT WER, cleanup checklist, GEval judge).

**Common variants**

```bash
./run-tests.sh --unit-only              # no Ollama; fast
./run-tests.sh --evals-only             # evals only
./run-tests.sh --skip-geval             # no DeepEval judge
./run-tests.sh --skip-slow              # no Whisper STT cases
./run-tests.sh --no-log                 # terminal only
./run-tests.sh -- -k full_feature_example -v   # single case; extra pytest args after --
```

Windows: same flags on `run-tests.bat`.

Direct pytest (after activating venv from `.voice_dictation_venv`) is fine for one-offs; prefer `./run-tests.sh` for full runs so Ollama checks and logging stay consistent.

## Test result logs (default)

Each `./run-tests.sh` / `run-tests.bat` run **creates new files** (does not append) under:

```text
logs/test-runs/pytest-YYYYMMDD-HHMMSS.log   # full stdout/stderr (macOS/Linux: also shown live via tee)
logs/test-runs/pytest-YYYYMMDD-HHMMSS.xml   # JUnit XML
```

The script prints both paths at startup. **`logs/` is gitignored.**

**Agents:** after a test run, read the **`.log`** file for failures (WER lines, substring assertions, GEval scores). Use the **`.xml`** only if you need structured pass/fail counts.

To disable file logging: `./run-tests.sh --no-log`.

## Adding or changing eval cases

- **Cleanup:** drop `evals/cases/cleanup/<id>.json` — auto-discovered. See [`adding-tests.md` § Adding a cleanup eval case](adding-tests.md#adding-a-cleanup-eval-case).
- **STT:** WAV in `evals/cases/stt/` + row in `evals/cases/stt/metadata.json`.
- **Shared GEval rubric:** `evals/geval_cleanup_criteria.json` (`criteria` field).
- **Example case using all JSON features:** `evals/cases/cleanup/full_feature_example.json`.

## Layout (quick)

| Path | Role |
|------|------|
| `tests/` | Fast unit/API pytest (mocks) |
| `evals/test_stt_wer.py` | STT WER (`@pytest.mark.slow`) |
| `evals/test_cleanup.py` | `test_cleanup[<id>]` — one cleanup run, then checklist + optional GEval |
| `evals/helpers.py` | Ollama checks, `build_geval_criteria_for_case`, pipeline helpers |

## When changing behavior

- Prefer extending case JSON and `evals/geval_cleanup_criteria.json` over editing `evals/test_cleanup.py` unless the harness itself must change.
- After eval or cleanup prompt changes, run `./run-tests.sh` (or targeted `-k`) and inspect `logs/test-runs/*.log`.
