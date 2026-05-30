---
name: create-voice-dictation-eval
description: >-
  Guides creation of a new voice-dictation MVP eval case (cleanup JSON in evals/cases/cleanup/
  or STT entry in evals/cases/stt/metadata.json) by asking one question at a time in a minimal
  order. Accepts skip/decline/default for optional fields. Use when the user wants a new eval
  case, cleanup regression story, STT WER case, or says create voice dictation eval.
---

# Create voice dictation eval

Interactive workflow to add one eval case under `coding/voice-dictation-mvp/`. **Ask exactly one question per message** until intake is complete, then write files and offer to run pytest.

**Working directory:** `coding/voice-dictation-mvp/`

**Canonical docs:** [`adding-tests.md`](../../adding-tests.md), [`AGENTS.md`](../../AGENTS.md)

**Field reference & templates:** [reference.md](reference.md)

---

## Rules

1. **One question at a time** — never batch the intake questionnaire.
2. **Optional = skippable** — if the user says `skip`, `none`, `no`, `decline`, `pass`, or `default`, omit the field or use the documented default (see reference).
3. **Infer when obvious** — propose a draft `id` or checklist strings from `raw_transcript`; user can correct on the next turn.
4. **Validate before write:**
   - Cleanup: `evals/cases/cleanup/<id>.json` must not already exist; `id` must match filename stem.
   - STT: `id` unique among `evals/cases/stt/metadata.json` → `cases[]`; `wav` file must exist or user agrees to add it.
5. **Do not edit** `evals/test_cleanup.py`, `evals/test_stt_wer.py`, or `evals/helpers.py` for a normal new case.
6. After writing, show the JSON and suggest:
   ```bash
   pytest evals/test_cleanup.py -k <id> -v
   # or
   pytest evals/test_stt_wer.py -k <id> -v
   ```

---

## Question order (minimize turns)

### Step 0 — Branch (required)

**Q0:** *"Cleanup eval (LLM rewrite) or STT eval (audio + WER)?"*

- **cleanup** → cleanup flow below
- **stt** → STT flow below

---

## Cleanup eval flow

### Phase A — Core (always)

**Q1 — Case id**  
*"Short slug for this case (e.g. `filler_rewrite`, `plain_text_only`). I'll use it as the filename and pytest id."*  
→ `id`

**Q2 — Raw transcript**  
*"Paste the messy spoken transcript (as STT would return it) — this is `raw_transcript`."*  
→ `raw_transcript`

### Phase B — Context (one combined question)

**Q3 — Vocabulary & user instructions**  
*"Any **vocabulary** terms the cleanup model should preserve (one per line or comma-separated), and any **user_instructions** (e.g. 'Use sentence case')? Reply `skip` for neither."*

| User reply | JSON |
|------------|------|
| `skip` / `none` | omit both, or `"vocabulary": null, "user_instructions": null` |
| vocab only | `vocabulary` string; omit or null `user_instructions` |
| both | set both strings |

Use newline-separated vocabulary when multiple terms (see `full_feature_example.json`).

### Phase C — How to grade (one decision)

**Q4 — Grading mode**  
*"How should this case pass? Pick one:*  
*(a) **Checklist only** — substring must/must-not (fast, no GEval)*  
*(b) **Checklist + GEval** — recommended*  
*(c) **GEval only** — no substring checklist (unusual)"*

| Mode | Next steps |
|------|------------|
| (a) | Phase D, then set `"skip_geval": true`; skip Phase E except decline path |
| (b) | Phase D, then Phase E |
| (c) | Skip Phase D unless user still wants lists; Phase E with empty/minimal checklist |

### Phase D — Checklist (if mode a or b)

**Q5 — Must contain**  
*"Strings that **must** appear in cleaned output (comma-separated)? Common: names, product terms. Reply `skip` if none."*  
→ `expected_contains` array, or omit / `[]`

**Q6 — Must not contain**  
*"Strings that **must not** appear? Reply `skip` to use repo defaults: `` ``` ``, `Here is`, `Sure,` — or give your own list."*  
→ `expected_not_contains`; if skip, use defaults above

**Heuristics (suggest, don't assume):**

| Transcript signal | Suggest |
|-------------------|---------|
| Question | `expected_contains: ["?"]`, `expected_not_contains` includes factual answer tokens |
| Names / brands | include in `expected_contains` |
| Risk of markdown / assistant voice | defaults + `**`, `# ` if needed |

### Phase E — GEval (if mode b or c, and not checklist-only)

**Q7 — Golden output**  
*"Optional **expected_output** — ideal cleaned line for the judge (same meaning, wording may differ). Reply `skip` if checklist is enough."*  
→ `expected_output` or omit

**Q8 — Extra judge rules**  
*"Any **geval_criteria_augment** for this story only (plain text only, don't answer questions, near-verbatim OK, etc.)? Reply `skip` to rely on shared rubric in `evals/geval_cleanup_criteria.json`."*  
→ `geval_criteria_augment` or omit

**Q9 — GEval threshold** (only if prior answer suggests GEval runs)  
*"Minimum GEval score 0–1? Reply `default` for **0.5** (from eval_config)."*  
→ omit `min_geval_score` or set float

**Q10 — Full rubric override** (ask only if user said shared rubric is wrong)  
*"Replace the shared rubric entirely with **geval_criteria**? Reply `skip` (almost always)."*  
→ rare; omit by default

Set `"skip_geval": false` when Phase E runs.

### Phase F — Write

1. Build JSON (pretty-printed, trailing newline). Omit null optional keys unless repo examples use explicit `null`.
2. Write `evals/cases/cleanup/<id>.json`.
3. Summarize: checklist fields, GEval on/off, suggested test command.

---

## STT eval flow

**Q1 — Case id** → `id`

**Q2 — WAV file**  
*"Filename under `evals/cases/stt/` (e.g. `my_clip.wav`). Does the file already exist, or will you add it before running tests?"*  
→ `wav`; confirm path `evals/cases/stt/<wav>` exists or warn user to add it

**Q3 — Reference transcript**  
*"Exact words spoken in the clip (`reference_transcript`)."*  
→ `reference_transcript`

**Q4 — Max WER**  
*"Max word error rate 0–1? Reply `default` for **0.25** (or per-case override like `0.15` for short clips)."*  
→ `max_wer` or omit (uses `stt_max_wer_default` in `evals/eval_config.json`)

**Q5 — Write**

1. Read `evals/cases/stt/metadata.json`.
2. Append to `cases[]` (keep valid JSON, existing cases unchanged).
3. Do not duplicate `id`.

---

## After write (both types)

Offer to run (Ollama required for cleanup):

```bash
./run-tests.sh -- -k <id> -v
```

If cleanup + GEval and user wants speed: `./run-tests.sh --skip-geval -- -k <id> -v` for checklist only.

---

## Do not ask

- Judge/cleanup **model names** — live in `evals/eval_config.json` and TWIM `_default/settings.json`
- Shared GEval **criteria** text — `evals/geval_cleanup_criteria.json` (unless user explicitly wants to edit global rubric; that's a separate task)

---

## Examples in repo

| File | Pattern |
|------|---------|
| `evals/cases/cleanup/filler_rewrite.json` | Checklist + GEval + `expected_output` |
| `evals/cases/cleanup/plain_text_only.json` | Near-verbatim + `geval_criteria_augment` |
| `evals/cases/cleanup/question_not_answered.json` | Checklist only, `skip_geval: true` |
| `evals/cases/cleanup/full_feature_example.json` | Vocab + instructions + both teachers |
| `evals/cases/stt/metadata.json` | STT registry |

See [reference.md](reference.md) for full field matrix and JSON skeletons.
