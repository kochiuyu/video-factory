# Animated scenes

`visual: animated` is an opt-in moving scene. Counters, a ten-frame, and a number sentence are drawn with [Manim Community](https://www.manim.community/). Slide lessons do not import this path and do not need Manim installed.

Install it only when a lesson asks for it:

```bash
python -m pip install -r requirements-manim.txt
```

On Debian or Ubuntu, a source build of the Cairo binding also needs `pkg-config`, `libcairo2-dev`, `libpango1.0-dev`, and `python3-dev`. `fonts-noto-cjk` supplies the on-screen Chinese. The factory file `fonts/CJKFallback.ttf` is the fallback.

## Authoring

```yaml
- id: thirteen
  visual: animated
  scene: ten_and_ones
  count: 13
  seconds: 14
  s1_en: "Thirteen counters. They fill a frame of ten."
  s1_zh: "十三个圆片。它们填满一个十格框。"
  s1_zh_hk: "十三個圓片。佢哋填滿一個十格框。"
  s2_en: "The full frame stays together. That is one ten, and three ones are left."
  s2_zh: "满框留在一起，就是一个十，还剩三个一。"
  s2_zh_hk: "滿框留喺一齊，就係一個十，仲剩三個一。"
  s3_en: "Thirteen equals ten plus three."
  s3_zh: "十三等于十加三。"
  s3_zh_hk: "十三等於十加三。"
```

`scene` is `ten_and_ones` or `make_ten`.

- `ten_and_ones` takes `count` from 10 to 20. The demo uses 13: ten counters fill the frame, three sit beside it, and the sentence is `13 = 10 + 3`.
- `make_ten` takes `a` (1–9) and `b`. `b` must be large enough to fill the empty cells and `a + b` must stay within 20. The demo uses 9 and 8. One of the eight moves into the empty cell: `9 + 1 = 10`, then `10 + 7 = 17`.

Speech is the factory's staged lines, one line per motion: `s1`, `s2`, and `s3` in English and 简体. If any `zh_hk` field is set, all three Cantonese lines are required, so a Cantonese voice is not handed Mandarin. Write the Cantonese the way it is spoken (`係`, `喺`, `仲`, `放入`). On-screen labels come from the per-language table in `factory/anim.py`: 简体 for `zh` (`凑成十`), 繁體 for `zh_hk` (`湊成十`).

Number sentences are plain text, not LaTeX, so a TeX install is not required.

## Timing

Each beat is still one MP3. After the voices are generated, the step lengths are the caption holds from `pages_for_stages` for those three lines. The motion plays, then holds, for that many seconds. The 0.4s breath at the end of the beat stays on the last step. A longer Cantonese line makes the counters travel more slowly and rest longer. The MP3 is not trimmed.

Caption cards are drawn on top of the moving picture for those same holds. The SRT writer is unchanged. English, Mandarin, and Cantonese are separate renders, because the labels and the audio lengths both differ.

If the word-time match fails, the holds fall back to speech-weight. The animation uses whichever holds the captions used.

## Frame size and cache

The default frame is 1920×1080. A lesson with `format: "9:16"` renders the animation at 1080×1920. Phone slide layout is a separate change and is not part of this path.

The silent movie is cached under `anim/` (`9x16/anim/` for a 9:16 lesson). The key is the scene spec, the step durations, the language, the frame size, and the Manim version. Slide caches and `LAYOUT_VERSION` are left alone.

## Demo

`examples/demo-ten-and-ones.yaml` is the P1 demo (a ten and some ones, then make ten with 9 + 8). It sits outside `lessons/`, so `build --all` does not render it.

```bash
python factory/build.py examples/demo-ten-and-ones.yaml --cells en,zh,hk --match-titles --out /path/to/out
```

`--slides-only` and `--caption-preview` paint slide stills. A lesson that is only animated scenes has none, and those flags say so. A full build writes the video.

## Limits

A bilingual slide cell shows the primary language on the counters and the sentence. The second language stays in the captions and the other cell. A speaker should still hear the Cantonese before a classroom cut: the lines are written to be spoken, and Edge reads exactly the text in the YAML.
