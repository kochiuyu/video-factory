# Experimental Mean focus preview

These contact sheets compare the default renderer with the opt-in focus layout.
They are not a replacement for `lessons/STAT/STAT-M01-T02-MEAN.yaml`. That file is unchanged.

Regenerate with:

```bash
python factory/focus_preview.py
```

Each `compare-*.png` sheet is phone width (390 px) and captioned. The left column is the default layout. The right column is `slide_style: focus`, with the arithmetic card on `layout: calculation`. Speech, numbers, quiz, and beat order are the production lesson.

Mixes: `zh`, `hk+en`, `zh+en`, `en+zh`.

`shop-partition-*.png` splits only the data beat's first spoken stage into four shop slices. Joining the slices returns that stage exactly. The card does not include the original second and third stages, so it is not aligned to the production data beat. Each row shows the caption card that names that shop's cups. Stage 1 also has an earlier card for the opening sentence, and stage 4 has a later card for the closing question. Those other cards are on the same still; the sheet does not stack every card.

`tex-equation-en.png` is the existing accounting-equation card, copied in memory from `ACC-M01-EQ`. The source lesson is not edited.

No audio is generated and no TTS service is called. Captions are still previews.
