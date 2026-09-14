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
