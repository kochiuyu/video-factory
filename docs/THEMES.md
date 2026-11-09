# Slide themes

Colour is not locked in `slides.py`. Each file in `themes/` is a palette.
Layout (title band, two columns, takeaway bars) stays the same so cells
remain comparable while you shop for a look.

## Try before you commit

In the console: pick **Slide theme** → **Generate slides only**.
No speech is generated. Switch theme and paint again. When one look wins,
use that same theme for **Build cells** and stop changing it mid-sample.

```powershell
python factory\build.py lessons\ECON-IN-01.yaml --theme slate-minimal --slides-only
python factory\build.py lessons\ECON-IN-01.yaml --theme high-contrast --slides-only
```

## Shipped palettes

| File | Look |
|------|------|
| `themes/cuhk-navy.yaml` | Navy / gold / cream (current default) |
| `themes/slate-minimal.yaml` | Grey lecture, no blobs |
| `themes/high-contrast.yaml` | Black / white / gold |

## Make another

Copy a file in `themes/` and change hex colours. Restart the console.
The new `id` appears in the dropdown.

```yaml
id: my-draft
label: My draft
bg: "#F7F4EE"
ink: "#141C28"
muted: "#5A6473"
white: "#FFFFFF"
navy: "#0B1F3A"
gold: "#C4A35A"
emerald: "#1F6F5B"
wash: "#ECE4D2"
wash2: "#E8E0CE"
blobs: true
corner: true
```

`blobs` and `corner` only toggle decoration. Do not invent a new card
layout in a theme file; that is a `slides.py` change and a schema review.

## Typography (opt-in)

Two optional keys change type, not colour. Leave them out and slides render exactly as before.

```yaml
typography: 2          # body text regular weight, capped at ~0.65x the title (title stays bold)
title_font: NotoSansCJK-Bold.ttc      # optional; replaces the bold face (titles)
body_font: NotoSansCJK-Regular.ttc    # optional; replaces the regular face (body, second-language lines)
```

- `typography: 2` applies to `two_column`, `takeaway`, `example`, `three_column` and `steps` bodies: about 54 px single-language and 47 px bilingual, regular weight, so the bold title leads.
- A font path is tried as given, then under `fonts/`, `themes/` and the repo root. It is used only when it paints a CJK + Latin sample (简体, 繁體, digits, `%`, `=`); otherwise the build prints `theme: title_font … ignored` and keeps the current faces.
- `VF_TYPOGRAPHY=2` turns it on for one build without editing a theme. The setting is part of the slide cache key, so stills re-render.
- Shipped example: `themes/cuhk-navy-type2.yaml` (cuhk-navy colours + `typography: 2`). Use it with `python factory/build.py lessons/STAT/<lesson>.yaml --theme cuhk-navy-type2`. No lesson or module selects a theme in YAML, so nothing switches by default; pass the flag for the M04 builds.
