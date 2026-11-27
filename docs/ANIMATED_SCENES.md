# Animated scenes

`visual: animated` is an opt-in moving scene. Counters, a ten-frame, and a number sentence are drawn with [Manim Community](https://www.manim.community/). Slide lessons do not import this path and do not need Manim installed.

Install it only when a lesson asks for it:

```bash
python -m pip install -r requirements-manim.txt
```

On Debian or Ubuntu, a source build of the Cairo binding also needs `pkg-config`, `libcairo2-dev`, `libpango1.0-dev`, and `python3-dev`. `fonts-noto-cjk` supplies the on-screen Chinese. The factory file `fonts/CJKFallback.ttf` is the fallback.

## Authoring

Any beat may set `visual: animated`. A hook, a definition, a middle step, or a takeaway can be a moving scene, and the beats around it can stay on the slide cards they already use. The factory does not assign a role to slides or to Manim. `visual: animated` is a choice on that beat alone.

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

`scene` names a registered scene. The registry is `factory/scene_registry.py`. Each scene has a step count, a parameter check, and a per-language label table. `title_card` and `takeaway` are slide visuals, not registry scenes. A beat uses one or the other.

The scenes are `one_ten`, `ten_and_ones`, `make_ten`, `count_objects`, `number_track`, `ordinal_row`, `pair_counters`, `part_whole`, `number_blocks`, `lesson_hook`, and `lesson_takeaway`.

- `one_ten` takes `count` from 10 to 20 and four spoken lines. Ten counters start as single ones, gather into one frame, and the frame is labelled "one ten". The ones that do not fit then sit beside it, the child is asked how many, and the last line answers. The demo uses 13, so the answer is three.
- `ten_and_ones` takes `count` from 10 to 20. The demo uses 13: ten counters fill the frame, three sit beside it, and the sentence is `13 = 10 + 3`. `count: 20` fills two frames and the sentence is `20 = 10 + 10`. In a 9:16 frame the two frames stack; in 16:9 they stay side by side. One frame is unchanged.
- `make_ten` takes `a` (1–9) and `b`. `b` must be large enough to fill the empty cells and `a + b` must stay within 20. The demo uses 9 and 8. One of the eight moves into the empty cell: `9 + 1 = 10`, then `10 + 7 = 17`.
- `count_objects` takes `mode` and `count`. `mode: count` lights counters one by one and writes the number on each (touch each once). `count` is 1 to 20. `mode: rearrange` moves that same set into a circle and keeps the total. `mode: zero` needs `count: 0`: an empty tray, then 0. Three spoken lines.
- `number_track` takes `low`, `high`, `start`, and `end`. The track runs from `low` to `high`. Use `0` and `20` for the classroom track. In 16:9 that track is one row, so a hop across 10 is a sideways move. In 9:16 it wraps onto the next row only when a cell would be too small to read. Every row reads left to right, and the next row starts at the left. A 0–20 track is six cells wide: 0–5, then 6–11, then 12–17, then 18–20. The marker lands on each spoken number, including the number it starts on: "Nine. Ten. Eleven. Twelve." lands on 9, then 10, then 11, then 12. Word starts come from the TTS sidecar. Without them the hops share the step evenly. A hop that passes 10 is marked "cross ten". The result number stands on its own line. "One more" (or "One less") and "Cross ten" stack under the track, one short label per line, at the same size, so they do not sit beside the number. `0 <= low < high <= 30`, the track is at most 20 steps long, and `start` and `end` sit on the track and differ. Three spoken lines.
- `ordinal_row` takes `n`, `mark`, `direction`, and `mode`. `n` is 1 to 20 tokens. `mark` is the marked token, counted from the left, so the star stays put when the question names the other end. `direction` is `left` or `right`. `mode: ordinal` pops `1st`, `2nd`, `3rd` (第一、第二、第三) one by one up to that token, and the highlight box moves with each spoken place. `mode: total` counts every token and shows how many. Place labels (`1st`, `2nd`, 第一) and count labels (`1`, `2`, 一) sit centred above each token, at least 48px at 1080p and 56px on a 1920-tall 9:16 frame, and the token row is about twice the old cap where the frame has the room. In 9:16 the six tokens use the safe width, and the centre spacing is at least the label plus 16px (the label may shrink, but not below 44px). The count lands on the spoken words from the TTS sidecar; without them the steps share the line evenly. In 9:16 a long ordinal row snakes, so the next token sits beside the one before it. A later place lesson can reuse the scene by changing `n`, `mark`, and `direction`. Three spoken lines.
- `count_objects` in `mode: count` lights each counter as that number is spoken, using the same word starts. `ten_and_ones` moves one counter into place per spoken number on its first line when the sidecar has one word per counter (the 1-to-13 count). A line that is not a count, such as two full frames, keeps one shared motion.
- `pair_counters` takes `n` from 0 to 20. The counters start slightly apart and slide into `n // 2` pairs. A leftover counter (`n % 2`) stays alone and gets a gold ring on the last line. Pair labels (`1`, `2`, or 一, 二) land on the spoken count, and the highlight box moves with them. Labels are at least 48px at 1080p and 56px on a 1920-tall 9:16 frame, and a row keeps at least 16px between labels (the label may shrink, but not below 44px). In 9:16 a long set uses three pairs across so the row fills the safe width. The count uses TTS word starts; without them the pairs share the line evenly. Three spoken lines.
- `part_whole` takes `a` and `b`, each an integer from 0 to 9, not both 0, with `a + b` from 1 to 18. A part of 0 is an empty mat, a place with nothing on it. Empty circles are only counters that move away. The counters start as two coloured parts. Part labels (digits, or 三 and 四) land on the two spoken number words, and the highlight box moves from one label to the other. On the last line the parts slide together, a bracket joins them, and the bond reads `whole = a + b`. Optional `also` is another left-hand part of the same whole (not equal to `a`): the counters move to that split, the labels land on the new parts, and the parts then slide together while the whole stays put. Optional `cover` is `a` or `b`: that part is covered and the bond is read as `whole − covered = kept`, drawn with a minus sign as wide as `=` and `+`. Optional `leave` is `a` or `b`, and is not used with `also` or `cover`: on the last line those counters move away, landing on the spoken word for the part that leaves, then the difference lands on the spoken word for the part that stays. An empty circle remains in each spot, and the bond is the same subtraction. Taking away a part of 0 moves no counters, so no empty circle appears, and the bond is `whole − 0 = whole`. Taking every counter away leaves an empty circle in each spot and `whole − whole = 0`. Without those word timings the two motions share the line evenly. A part of five counters or fewer stays on one row in both aspects. A longer part may wrap in 9:16. `also` and `cover` are not used together. An optional `whole` must equal `a + b`. Labels share one reference-glyph centre, at least 48px at 1080p and 56px on a 1920-tall 9:16 frame, with at least 16px between the two labels. The count uses TTS word starts; without them the two labels share the line evenly. Three spoken lines.
- `number_blocks` takes `mode` (`tens`, `compare`, `order`, `hop`, or `groups`) and three spoken lines. `tens` takes `count` from 0 to 100 and draws that many bundles of ten, then the leftover ones. Zero ones are an empty mat with 0, the same empty-mat idea as a part of 0. The bundles land on the spoken tens when the first line ends in one word per bundle ("Ten, twenty."); otherwise they share that line. The ones, or the empty mat, appear on the second line, and the number on the third. `pair_ones: true` puts those ones into pairs and rings one leftover. `compare` takes two different numbers `a` and `b` from 0 to 100, shows one and then the other, and rings the larger number. `order` takes `a` and `b`, and may add `n` and `mark`: two to four values from 0 to 100, drawn left to right in that order. In 9:16, four values sit in two rows. `hop` takes `start` and `end` from 0 to 100. They differ, and they are at most five steps apart, so the row is one left-to-right line in both 16:9 and 9:16. The marker lands on each spoken number, including the number it starts on. `groups` takes `a` (how many in a box, 2–5), `n` (how many boxes, 1–6), and optional `b` (loose counters, fewer than one box). The total stays within 20. The running totals under the boxes land on the spoken count. A loose counter is ringed on the last line. This scene is for numbers the 0–20 scenes cannot show. A lesson that fits `one_ten`, `ten_and_ones`, `number_track`, `pair_counters`, or `part_whole` should keep using those.
- `lesson_hook` takes `motif` (`counters`, `ten_frame`, `track`, `ordinal`, `pairs`, or `parts`) and one spoken line (`s1`). The grade tag and the `title_*` fade in, then the motif. The grade tag is `P1` in English and `小一` in Chinese, drawn large enough that the two characters stay separate. An ordinal hook may set `n` and `mark` (six tokens, the third one marked, when they are omitted). Those tokens are about twice the previous size. A pairs hook may set `n` (eight counters when it is omitted). A parts hook may set `a` and `b` (3 and 4 when they are omitted, and either part may be 0). In 9:16 the title and the picture each fill the safe width. A long parts title wraps onto two centred lines so each line stays at least 52px on a 1920-tall frame, and the grade tag keeps its own size.
- `lesson_takeaway` takes the same `motif` and three spoken lines, or four when `s4` is written. Each line fades in, in order, with its own cue. The words on screen are the spoken lines. Every takeaway, including a three-line one, is the same grid: the frame minus 8% on each side, a heading band, and the caption band, split into one equal cell per line. The gap between pictures is a quarter of the row. In 16:9 the picture column is 40% of that width and the sentence column is 60%, with at least 40px at 1080p between the picture (labels included) and the sentence. The body face is one size for every row and every language, at least 44px at 1080p and 52px on a 1920-tall 9:16 frame. A line that is wider than its column breaks at a sentence or a word, and Chinese breaks only at punctuation. In 9:16 each wrapped line is centred, and the rows are centred in the band between the heading and the caption. The heading is the same size in every language. A circle of counters keeps its total clearly to the right of the dots. A counters recap with `count` lights that many counters on the first line, one per spoken number, then shows the total, moves the counters into a circle beside that same total, and ends on an empty tray with 0. A ten-frame recap shows one full frame, a frame plus three ones with 13, two full frames with 20, then highlights the ten and counts the three ones. An ordinal recap with `n` and `mark` shows the total, the place from the left, the place from the right, and the same row with the total still beside the marked token. In 9:16 those four token rows share one size, about 80% of the safe width. A pairs recap with `n` shows that count paired, the next count with one left over, and a pair of two. `also` adds a fourth cue: that many counters in rows of five pairs, at the same counter size, with a leftover ringed. In 9:16 those rows share one size, about 80% of the safe width. A parts recap sets `bonds`, one to four cues. Each cue is `[left, right]` (two colours) or `[whole]` (one green row). A part of 0 is an empty mat beside the other part. A one-number cue stays one green row. A negative right part, such as `[3, -2]`, keeps the left counters and draws that many empty circles beside them, the part that was taken away. A kept part of 0, such as `[0, -4]`, draws only those empty circles. In 9:16 those rows share one size, about 80% of the safe width. A takeaway may also set `cues`, one picture per spoken line. Those pictures replace the motif, including the track motif's fixed rows (9–12, 17–20, and 12 down to 9). `kind: tens` draws that many ten-rods and one-cubes (`count` 0–100). Every tens row in one takeaway uses the same rod and the same cube, so a cube stays much smaller than a rod and ten rods are that same rod in two rows of five. `kind: compare` draws `a` and `b` with every ten-rod and every one-cube, the ones beside the rods, leaves at least 40px at 1080p between the two numbers, and rings the larger number together with its blocks. `kind: tens_mark` with `a` and `b` draws both numbers and outlines their ten-rods. With `rods` alone it draws that many ten-rods (four when omitted). `kind: tiles` draws `values` left to right. `kind: pairs` draws `n` boxes of two, plus `extra: 1` for one loose counter. `kind: counters` draws `n` counters. An unknown kind is an error. It is not drawn as the track placeholder.

Counters stay inside the safe margin for the whole motion, including the group they start in. That group is a grid with a gap, not a pile. In 9:16 the "one ten" label sits between the frame and the ones outside it.

To add a scene: subclass `SceneKind` in `factory/scene_registry.py`, `register` it, draw it under the same name in `factory/anim.py`, and add its YAML here.

Speech is the factory's staged lines, one line per motion: `s1`, `s2`, and `s3` in English and 简体. `one_ten` also has `s4`, the short answer. If any `zh_hk` field is set, every Cantonese line for that scene is required, so a Cantonese voice is not handed Mandarin. Write the Cantonese the way it is spoken (`係`, `喺`, `仲`). On-screen labels come from the per-language table in `factory/scene_registry.py`: 简体 for `zh` (`凑成十`), 繁體 for `zh_hk` (`湊成十`).

Number sentences are plain text, not LaTeX, so a TeX install is not required.

`count_objects` and `number_track`, and two full frames:

```yaml
- id: count
  visual: animated
  scene: count_objects
  mode: count
  count: 5
  seconds: 14
  s1_en: "Point to each counter once."
  s1_zh: "每个圆片，只点一次。"
  s1_zh_hk: "每個圓片，只指一次。"
  s2_en: "One. Two. Three. Four. Five."
  s2_zh: "一，二，三，四，五。"
  s2_zh_hk: "一，二，三，四，五。"
  s3_en: "Five. The last number tells how many."
  s3_zh: "五个。最后说的这个数，就是有多少个。"
  s3_zh_hk: "五個。最後講嘅呢個數，就係有幾多個。"

- id: empty
  visual: animated
  scene: count_objects
  mode: zero
  count: 0
  seconds: 12
  s1_en: "This tray is empty."
  s1_zh: "这个盘子是空的。"
  s1_zh_hk: "呢個盤係空嘅。"
  s2_en: "How many counters are there?"
  s2_zh: "有几个圆片？"
  s2_zh_hk: "有幾多個圓片呀？"
  s3_en: "Zero. Nothing to count. We write 0."
  s3_zh: "零个。没有可以数的。我们写0。"
  s3_zh_hk: "零個。冇嘢可以數。我哋寫0。"

- id: twenty
  visual: animated
  scene: ten_and_ones
  count: 20
  seconds: 12
  s1_en: "Two full frames. Each frame is one ten."
  s1_zh: "两个满框。每个框是一个十。"
  s1_zh_hk: "兩個滿框。每個框係一個十。"
  s2_en: "How many counters now?"
  s2_zh: "现在一共有多少个？"
  s2_zh_hk: "而家一共有幾多個呀？"
  s3_en: "Twenty. Ten plus ten is twenty."
  s3_zh: "二十。十加十就是二十。"
  s3_zh_hk: "二十。十加十就係二十。"

- id: across-ten
  visual: animated
  scene: number_track
  low: 0
  high: 20
  start: 12
  end: 9
  seconds: 12
  s1_en: "Can we count back across ten?"
  s1_zh: "往回数，能跨过十吗？"
  s1_zh_hk: "倒轉數，可唔可以跨過十呀？"
  s2_en: "Twelve. Eleven. Ten. Nine."
  s2_zh: "十二，十一，十，九。"
  s2_zh_hk: "十二，十一，十，九。"
  s3_en: "Yes. We land on nine."
  s3_zh: "可以。我们数到九。"
  s3_zh_hk: "可以。我哋數到九。"

- id: from-left
  visual: animated
  scene: ordinal_row
  mode: ordinal
  direction: left
  n: 6
  mark: 3
  seconds: 14
  s1_en: "Start at the left."
  s1_zh: "现在从左边数。"
  s1_zh_hk: "而家由左邊數。"
  s2_en: "First. Second. Third."
  s2_zh: "第一，第二，第三。"
  s2_zh_hk: "第一，第二，第三。"
  s3_en: "The star is third. Third is its place."
  s3_zh: "星星是第三。第三是它的位置。"
  s3_zh_hk: "星星係第三。第三就係佢嘅位置。"
```

## Timing

Each beat is still one MP3. After the voices are generated, the step lengths are the caption holds from `pages_for_stages` for those lines. The motion plays, then holds, for that many seconds. The 0.4s breath at the end of the beat stays on the last step. A longer Cantonese line makes the counters travel more slowly and rest longer. The MP3 is not trimmed.

Caption cards are drawn on top of the moving picture for those same holds. The SRT writer is unchanged. English, Mandarin, and Cantonese are separate renders, because the labels and the audio lengths both differ.

If the word-time match fails, the holds fall back to speech-weight. The animation uses whichever holds the captions used.

## Frame size and cache

The default frame is 1920×1080. A lesson with `format: "9:16"` renders the animation at 1080×1920. Phone slide layout is a separate change and is not part of this path.

The silent movie is cached under `anim/` (`9x16/anim/` for a 9:16 lesson). The key is the scene spec, the step durations, the language, the frame size, and the Manim version. Slide caches and `LAYOUT_VERSION` are left alone.

## Demo

`examples/demo-ten-and-ones.yaml` is the P1 demo. It sits outside `lessons/`, so `build --all` does not render it. The hook is a `title_card` and the takeaway is a `takeaway` card. The definition is `one_ten`, then `ten_and_ones` shows `13 = 10 + 3` and `make_ten` shows `9 + 8`. That mix is one example of choosing a slide or an animated scene per beat. It is not a required order.

```bash
python factory/build.py examples/demo-ten-and-ones.yaml --cells en,zh,hk --match-titles --out /path/to/out
```

`--slides-only` and `--caption-preview` paint slide stills. A lesson that is only animated scenes has none, and those flags say so. A full build writes the video.

The P1 lessons `lessons/P1/P1-NUM-01.yaml`, `P1-NUM-02.yaml`, `P1-NUM-03.yaml`, and `P1-NUM-04.yaml` use these scenes. `build --all` does render them.

```bash
python factory/build.py lessons/P1/P1-NUM-02.yaml --cells en,zh,hk --match-titles --out /path/to/out
```

## Limits

A bilingual slide cell shows the primary language on the counters and the sentence. The second language stays in the captions and the other cell. A speaker should still hear the Cantonese before a classroom cut: the lines are written to be spoken, and Edge reads exactly the text in the YAML.
