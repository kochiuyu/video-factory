# Standard operating procedure

Faculty teaching from a finished pack should print [SOP-faculty.html](SOP-faculty.html) (one A4 page). This file is the operator cycle after the console already runs. If the console is not up yet, stop and follow
[SETUP.md](SETUP.md).

## Roles

| Role | Owns | Does not own |
|------|------|----------------|
| Faculty | Glossary lock, conceptual sign-off, course zip | ffmpeg, file mux |
| Drafter (RA or any LLM using `AUTHORING_PROMPT.md`) | YAML draft, quiz stems | Final terms. Delivery uses `QA_CHECKLIST.md`. |
| Operator | Validate, TTS, `build.py`, duration check | Changing the claim |
| Reviewer | Watch one matched video end-to-end; spot-check the other two languages | Rewriting the lesson |

One person may hold two roles. Faculty and reviewer should not be the same person as the drafter for the first ten topics.

## Workstation

Required (see [SETUP.md](SETUP.md) for the exact clicks):

- Python 3.10+
- Activated `.venv` with `requirements.txt`
- Bundled files in `fonts/`
- ffmpeg on PATH, or `imageio-ffmpeg`
- This repository

Optional:

- Alternative TTS MP3s dropped into `out/<ID>/audio/{en,zh}/` if you pass `--no-tts`

## Cycle for one topic (target: one working day after the template is familiar)

1. Faculty commissions a topic in the console (or from `docs/AUTHORING_PROMPT.md`). Do not start from `briefs/` — that folder is leftover.
2. Drafter writes `lessons/<AREA>/<ID>.yaml` from `docs/AUTHORING_PROMPT.md`. Check must be clean, and `docs/QA_CHECKLIST.md` must pass, before Build.
3. Faculty locks glossary pairs and the example.
4. Run one production command:

   `python3 factory/build.py lessons/<ID>.yaml`

   This validates implicitly via the builder, paints slides, synthesizes missing narration, pads both languages to one clock, and writes four cells. Use `--force-tts` only if the spoken text changed. Use `--no-tts` only if audio will be supplied by another vendor.
5. Reviewer (human audit) plays `en-en` and `zh-zh` in full, then spot-checks captions on the mixed cells.
6. If any cell duration differs from the silent master by more than 0.3 s, stop and re-pad. The factory pads to `max(en, zh)` per beat; do not edit the picture to fit one language.
7. Copy the four files into the experiment library. Do not rename cells after fielding.

## QA gate (all must pass)

Lesson YAML also passes `docs/QA_CHECKLIST.md` before delivery: standalone hook and takeaway, evidence labels, model assumptions, and the multiple-choice quiz shape.

- [ ] Glossary locked strings appear verbatim in both scripts.
- [ ] No extra English sentence on the ZH-labelled picture, and the reverse.
- [ ] Captions stay inside the safe area; Chinese lines wrap.
- [ ] `python3 factory/validate.py lessons/<ID>.yaml` reports no missing-glyph errors. Run `python3 factory/diagnose.py` after a font change.
- [ ] Four cells share the same duration.
- [ ] Quiz items test spoken claims, not off-screen trivia.
- [ ] File names match `out/<ID>/cells/<ID>_{en-en,en-zh,zh-en,zh-zh}.mp4`.

## What other people must not copy from the original chat

- Sandbox paths such as `/home/workdir/...`
- The assumption that Grok Voice is the only legal TTS
- Informal wording that is not in the YAML
- A new visual invented in a single conversation

If the template must change, change `factory/slides.py`, `docs/SCHEMA.md`, and one pilot lesson in the same review.
