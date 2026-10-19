# Windows setup

**First time on this PC?** Use [SETUP.md](SETUP.md) (Python, venv, fonts, console).
This page is the FFmpeg repair sheet and the UTF-8 note for Chinese YAML.

## Chinese YAML on Windows (`charmap` codec)

`charmap codec can't decode byte 0x8f` means a script opened a lesson file with the Windows code page instead of UTF-8.

The factory already reads and writes YAML as UTF-8. `factory/app.py` and `factory/build.py` also call `force_utf8()` on start.

If a helper script or Gemini's local runner still crashes:

```python
from pathlib import Path
import yaml

data = yaml.safe_load(Path("lessons/ECON/ECON-MB-01.yaml").read_text(encoding="utf-8"))
Path("lessons/ECON/ECON-MB-01.yaml").write_text(
    yaml.dump(data, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)
```

Optional for the whole machine (new terminals only):

```powershell
setx PYTHONUTF8 1
setx PYTHONIOENCODING utf-8
```

The traceback `FileNotFoundError: [WinError 2]` on `ffprobe` / `ffmpeg` means Windows does not have FFmpeg on PATH. Speech may already have been written; assembly cannot start.

## Install FFmpeg (required)

In PowerShell, pick one:

```powershell
winget install Gyan.FFmpeg
```

or

```powershell
choco install ffmpeg
```

or, Python-only fallback (no system install):

```powershell
pip install imageio-ffmpeg
```

Close the terminal and the factory console, then open a new one so PATH updates. Check:

```powershell
ffmpeg -version
```

Copy the updated `factory/ff.py`, `factory/mux.py`, and `factory/build.py` into your Downloads copy before rebuilding. Older copies still call the bare word `ffprobe`.

## Then rebuild

```powershell
cd $HOME\Downloads\video-factory\video-factory
python factory/build.py lessons\ECON-OC-01.yaml
```

Or start `python factory/app.py` and click Build. Do not tick “Regenerate speech” unless you changed the YAML; the MP3s from the failed run can be reused.

## Optional fonts

If Chinese on slides looks like boxes, install Noto Sans CJK and set:

```powershell
$env:VF_FONT_CJK="C:\Windows\Fonts\NotoSansCJKsc-Regular.otf"
$env:VF_FONT_LATIN="C:\Windows\Fonts\NotoSans-Regular.ttf"
```

## Output folder outside Dropbox

If the repo is under Dropbox, keep build files outside it so PNG, MP3, and MP4
sync does not pin the client. Lesson YAML stays in the repo.

```powershell
$env:VF_OUT = "C:\Users\kochi\video-factory-out"
python factory\app.py
```

`python factory\build.py --out C:\Users\kochi\video-factory-out ...` is the same switch for one build. Unset, output stays in `<repo>\out`. Details: [SETUP.md](SETUP.md).
