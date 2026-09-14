# Video factory

Deterministic factory for 1–3 minute educational explainers. One lesson file becomes four experimental cells:

| Cell | Narration | Captions |
|------|-----------|----------|
| `en-en` | English | English |
| `en-zh` | English | Chinese |
| `zh-en` | Chinese | English |
| `zh-zh` | Chinese | Chinese |

The picture is shared. Language lives only in audio and burned-in captions.

This repository is the transferable object. A Grok chat is not. Give collaborators the repo, `docs/SETUP.md`, `docs/SOP.md`, and `docs/AUTHORING_PROMPT.md`. Do not give them a transcript of the original design conversation and expect the same videos.

## Quick start

**First run:** follow [docs/SETUP.md](docs/SETUP.md) in order. That is the
necessary-steps list (Python, venv, fonts, diagnose, console, first video).

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python factory/diagnose.py
python factory/app.py
```

Browser: `http://127.0.0.1:8765`. Select `ECON-QA-01.yaml` → **Preview slides only**.
Then **Preview captions**, then **Build this lesson**. Leave the terminal open.

The same tree runs on Windows, macOS, and Linux. First run: `docs/SETUP.md`.
Windows FFmpeg repair: `docs/WINDOWS.md`.

On another machine, point fonts at local Noto files if needed:

```bash
export VF_FONT_LATIN=/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf
export VF_FONT_LATIN_BOLD=/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf
export VF_FONT_CJK=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
export VF_FONT_CJK_BOLD=/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc
```

## Documents for other people

| File | Audience |
|------|----------|
| `docs/SETUP.md` | Install and start the console |
| `docs/SOP.md` | RA / operator after the console runs |
| `docs/SOP-faculty.html` | Faculty teaching from a finished pack |
| `docs/SCHEMA.md` | YAML fields and visuals |
| `docs/AUTHORING_PROMPT.md` | LLM or RA drafting YAML |
| `docs/THEMES.md` | Slide palettes |
| `docs/WINDOWS.md` | Windows FFmpeg only |
| `lessons/ECON-QA-01.yaml` | Feature-test short |

`docs/INSTALL.md` and `docs/BRIEF.template.md` are pointers only. Do not keep a second copy of setup or briefing steps.

## Design that must stay fixed

1. Schema first. If it is not in the YAML, it is not in the video.
2. One clock per section. Pad audio to `max(English, 简, 繁)` per section, then join clips.
3. TTS is inside `build.py` (Edge neural voices by default). `--no-tts` accepts vendor MP3s on the same paths.
4. Template changes are code reviews, not chat improvisation.

## Out of scope

Avatar lip-sync, generative B-roll that differs by language, and live lecture capture. Those are a different factory.
