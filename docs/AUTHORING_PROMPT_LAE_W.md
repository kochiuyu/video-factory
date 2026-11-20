# Authoring and revise prompt — LAE-W What-is shorts (DOTE5891)

Use this document to draft or revise a **LAE-W** short. Do **not** use [AUTHORING_PROMPT.md](AUTHORING_PROMPT.md) (STAT lessons) or [AUTHORING_PROMPT_LAE.md](AUTHORING_PROMPT_LAE.md) (the first-year LAE-M mini-course). Those tracks have a different length, beat plan, and teaching intent. This series shares the factory, not their lesson format.

This file is the standing standard for upcoming LAE-W videos.

## What this series is

A technical, one-concept “What is …?” series for the CUHK course DOTE5891 (Business Analysis of Low-Altitude Economy). It is more technical than the gentler HeyGen LAE 101 surveys, and it is not a STAT-length lesson.

- **One simple concept per video.** About one to two minutes of speech.
- **Five cuts of each short:** English (`en`), Putonghua (`zh`), Cantonese (`zh_hk` / cell `hk`), English speech with Simplified bilingual slides (`en+zh`), and English speech with Traditional bilingual slides (`en+zh_hk` / cell `en+hk`).
- **Type-only slides** by default: large type on a cream field, not decorated illustrations.

## Sources and facts

- Draw claims only from the course companion site, [https://kochiuyu.github.io/lae-companion/](https://kochiuyu.github.io/lae-companion/), or from another source the faculty owner has approved. Treat the companion site as read-only. Do not edit it.
- Do not invent facts, numbers, legal limits, routes, or visuals.
- A classroom or “possible service” example must be labelled on screen and in speech as an example, not as a claim that the route or service operates today.
- Keep policy language and legal operating limits on separate layers. Do not treat a policy working description as permission to fly.

## One-concept rule

If an item needs a definition **and** a contrast **and** a second term, split it. Examples already split for this reason: drone vs SUA; VLOS vs BVLOS; UTM vs U-space; UAM vs AAM.

The first-wave list (later economics and policy terms come after this batch):

1. What is LAE?
2. What is the 1,000-metre band?
3. What is a drone?
4. What is an SUA?
5. What is an eVTOL?
6. What is VLOS?
7. What is BVLOS?
8. What is a vertiport?
9. What is UTM?
10. What is U-space?
11. What is UAM?
12. What is AAM?

Lessons 1 and 2 are the reference shorts. New lessons should feel like them.

## Typical beat plan

Four beats, one card each:

1. **`whatis_title`** — the question, and a short hook that narrows a common misunderstanding.
2. **`whatis_definition`** — one definition, not a list of subtopics.
3. **`whatis_example`** *or* **`whatis_contrast`** — either one classroom example, or “what it is / what it is not.” Do not put both in the same short unless the faculty owner asks.
4. **`whatis_takeaway`** — one rule the viewer should remember.

Do not use STAT cards (quiz pair, formula box, charts, staged `s1`/`s2` reveals) or the LAE-M corridor story.

## Voice and languages

- Write the **English speech first** and get it approved before translating.
- Spoken Chinese must be naturally phrased Putonghua and Cantonese, not a stiff, sentence-by-sentence translation of the English cadence.
- On-screen Chinese may stay more compact than the speech. Do not rewrite approved on-screen wording just to match a speech polish, unless typography overflows or the faculty owner asks.
- Do not mix 简体 characters into `zh_hk`, or Cantonese particles into `zh`.
- Do not mention the factory, captions, slide names, or production process in the speech.
- Default factory voices: `en-US-GuyNeural`, `zh-CN-YunxiNeural`, `zh-HK-WanLungNeural`.

## Slides

- Cream field, large navy type, one gold label. Keep the layout spare, with room for mixed-language text.
- The title card may keep the existing decorative circles and gold corner. Body cards stay typographic.
- Do not add icons, diagrams, or illustrations unless the faculty owner asks. If aids are approved, they must be factual (for example a short mission chain already in the script), shown as stills first, and used only where they help — usually the example or contrast card.
- **`whatis_example`** must carry the classroom-example stamp.
- **`whatis_contrast`** stacks “What it is” over “What it is not.” No VS badge and no second panel colour.
- An optional `source_*` footer (companion page and issuers such as LegCo CB(3)933/2024) is allowed on `whatis_*` cards only. Mixed-language footers keep the English source line so the citation stays readable.
- In a mixed cell, English is the large primary line; the matching Chinese sits underneath it.

## Timing

A lesson whose beats are all `whatis_*` times **each language on its own speech**, then holds the card for a **0.4 s** breath. It does not pad a shorter language up to the longest one, and it does not keep the card up for leftover YAML `seconds` after the line has finished.

- Mixed cells follow the English speech.
- YAML `seconds` and `duration_target_s` are planning budgets, not hold times. After a build, they may be updated to match speech plus breath if validation needs it.
- Do not cut or split a line only to avoid the factory’s “card longer than 20 s” warning when the sentence itself is that long. Fix a multi-second freeze after the voice stops; do not confuse that freeze with a long spoken example.
- STAT and LAE-M stay on the shared clock. Do not change their timing or pixels. Set `clock: shared` only if a lesson must keep that older behaviour; `clock: own` opts another lesson into per-language timing.

## Factory contract

- Folder: `lessons/LAE-W/`.
- Lesson id and file: `LAE-W-T##-SLUG`, for example `LAE-W-T01-LAE.yaml`. Do not collide with `LAE-M*` ids.
- Visuals: `whatis_title`, `whatis_definition`, `whatis_example`, `whatis_contrast`, `whatis_takeaway` only. One still per beat. Do not use `s1_*`.
- Speech lives in the beat’s `en`, `zh`, and `zh_hk` fields. That is the only spoken source. Captions follow the speech.
- `title_*` is the short question (“What is LAE?”). Do not put `(English)`, `(普通话)`, or `(粵語)` in the YAML title; the factory adds the language tag when it writes the YouTube paste file.
- Optional `youtube.description_*` may be added when the upload text is actually written. Do not invent a description. Each description must be strictly less than 2500 characters, with no ASCII `<` or `>` (use “to”, `→`, or fullwidth `＜` `＞`). A mixed cell uses the speech-language description.

Validate and build:

```bash
python factory/validate.py lessons/LAE-W/LAE-W-T01-LAE.yaml
python factory/build.py lessons/LAE-W/LAE-W-T01-LAE.yaml --slides-only --cells en,zh,hk,en+zh,en+hk --match-titles
python factory/build.py lessons/LAE-W/LAE-W-T01-LAE.yaml --cells en,zh,hk,en+zh,en+hk --match-titles
```

If factory code must change, keep the change additive and opt-in. Existing STAT and LAE-M lessons must still validate and paint the same pixels.

## Order of work — making a new short

1. **Pick one concept** from the agreed list, or propose a split if the item is doing too much.
2. **Draft the English speech and on-screen wording** from the approved sources. Label classroom examples. Stop for faculty approval.
3. **Write the YAML** on a branch. Do not merge yet.
4. **Render stills first** (`--slides-only`) in English, then `zh`, `zh_hk`, `en+zh`, and `en+zh_hk`. Hold TTS and the MP4s.
5. **Faculty reviews the stills** (colour, type size, mixed-language spacing, line breaks).
6. **Build all five videos.** Faculty watches them: pauses at the end of each card, natural Chinese phrasing, captions, and the takeaway.
7. **Revise and rebuild** if needed, then review again.
8. **Merge into video-factory** only after faculty approval.
9. **Publish to YouTube or the educational catalog** only after faculty approval. The factory paste file does not upload anything.

## How to revise

Revise one short at a time.

- Keep approved English speech, on-screen wording, facts, and ids unless the faculty owner asks to change them, or a validator requires a trivial fix.
- If Mandarin or Cantonese sounds translated, rewrite the speech in natural phrasing with the same facts. Leave on-screen Chinese alone unless it is wrong or overflowing.
- If a card freezes after the voice stops, fix timing (per-language clock, short breath). Do not pad to the longest language or the old YAML budget.
- If typography changes, show stills before rebuilding the videos. If only speech or timing changes, rebuilt videos are enough.
- Validate the YAML, and confirm a slides-only build of an existing STAT lesson (for example `STAT-M03-T01-INTRO`) still stages its usual cards when factory code changed.
- Do not merge, upload, or catalog a revision until the faculty owner has watched it and approved.

## QA before delivery

- One concept only; about one to two minutes.
- Every claim is sourced; examples are stamped; policy and legal limits are not mixed.
- English, Putonghua, and Cantonese speech are each natural in that language.
- Type is large enough; mixed slides have space; contrast and example follow the layouts above.
- Each language cut ends a beat shortly after its own speech (about 0.4 s), with no multi-second freeze.
- `validate.py` reports OK. Five MP4s exist for the five cells.

## Publishing (same pattern as STAT, only when asked)

The factory does not upload. When the faculty owner asks to publish, follow the STAT release pattern:

1. Write YouTube titles and descriptions (series name and number in the title if faculty wants that, plus the factory language tag). Prepare covers if used.
2. Upload all five cuts of the ready shorts as **Unlisted**, each into a language-mix playlist.
3. Add playlist and previous/next links, and check that every video is Unlisted, not a draft.
4. Then make **one topic Public per day**, all five cuts of that topic together, starting with T01.
5. After a topic is Public, it may be added to the educational-video catalog — only when the faculty owner asks, and through the catalog owner, not by editing that site from this track.

Do not start an upload or a daily Public routine until those steps have been approved for this series.

## Do not

- Follow the STAT authoring or revise prompt, or the first-year LAE-M guide, for these shorts.
- Pack two concepts into one video.
- Invent facts, numbers, citations, routes, or illustrations.
- Change STAT or LAE-M layouts, timing, or lesson files in order to ship a What-is short.
- Merge a pull request, publish to YouTube, or add a video to the catalog without faculty approval.
