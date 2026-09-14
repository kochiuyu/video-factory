# Windows setup

**First time on this PC?** Use [SETUP.md](SETUP.md) (Python, venv, fonts, console).
This page is only the FFmpeg repair sheet.

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
