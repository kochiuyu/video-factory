# Setup: from a blank computer to a running factory

This is the only document an RA needs to get the **app** running.
After these steps you will have a browser console at `http://127.0.0.1:8765`
and you can build a test lesson without typing further commands.

You do **not** need HeyGen, Docker, GitHub, or a GPU.
You **do** need a network connection the first time speech is generated
(Microsoft Edge neural voices).

Canonical test lesson after setup: `lessons/ECON-QA-01.yaml`
(English + Putonghua/简体 + Cantonese/繁體). Feature check for type scale and staged cards.

---

## 0. What “running” means

Success looks like this:

1. A terminal stays open and prints `Video factory console: http://127.0.0.1:8765`.
2. A browser tab shows **Video factory**, a catalog of shorts and modules, and
   **Build this lesson**, **Preview slides only**, **Preview captions**.
3. You can click **Preview slides only** on `ECON-QA-01.yaml` and stills appear
   on the Slides tab.

If the terminal closes, the app stops. That is expected.

---

## 1. What must be on the machine

| Requirement | Why | How you know it is there |
|-------------|-----|---------------------------|
| Python 3.10, 3.11, or 3.12 | Runs the factory and the console | `python --version` or `python3 --version` |
| This folder | Code, fonts, sample lessons | You can see `factory/app.py` and `lessons/` |
| `fonts/LatinFallback.ttf` and `fonts/CJKFallback.ttf` | English and Chinese on slides | Both files exist under `fonts/` |
| Internet (first speech only) | Edge TTS | A browser can open microsoft.com |
| Optional: system FFmpeg | Faster video mux | `ffmpeg -version` |

`imageio-ffmpeg` in `requirements.txt` is a fallback if system FFmpeg is missing.
You still want a real `ffmpeg` on PATH when possible (Windows: see §3).

---

## 2. Get the folder onto the computer

Copy the whole `video-factory` directory. Do not pick individual `.py` files.

The folder must contain at least:

```text
video-factory/
  factory/app.py
  factory/build.py
  lessons/ECON-IN-01.yaml
  fonts/LatinFallback.ttf
  fonts/LatinFallback-Bold.ttf
  fonts/CJKFallback.ttf
  requirements.txt
  docs/SETUP.md
```

Typical location on the faculty Windows machine:

`C:\Users\kochi\Downloads\video-factory\video-factory`

If that path is different, use yours in every command below.
In PowerShell, `cd` into the folder that **directly contains** `factory` and `lessons`.

```powershell
cd C:\Users\kochi\Downloads\video-factory\video-factory
dir factory\app.py
dir lessons\ECON-IN-01.yaml
```

If either `dir` fails, you are in the wrong directory (one level too high or too low).

---

## 3. Windows (the usual workstation)

### 3.1 Install Python

1. Open https://www.python.org/downloads/windows/
2. Download Python 3.12.
3. Run the installer.
4. Tick **Add python.exe to PATH**.
5. Finish, **close every terminal**, open a new PowerShell.

```powershell
python --version
```

You need `Python 3.10` or newer. `py` also works on some PCs (`py -3.12 --version`).

If Windows Store python opens instead of a real install, turn off
**Settings → Apps → Advanced app settings → App execution aliases**
for `python.exe` / `python3.exe`, then install from python.org again.

### 3.2 Install FFmpeg (strongly recommended)

Pick one. Then close PowerShell and open a new one.

```powershell
winget install Gyan.FFmpeg
```

or

```powershell
choco install ffmpeg
```

or skip the system install and rely on `imageio-ffmpeg` (already in
`requirements.txt`). That fallback works, but a PATH install avoids
old “Access is denied” / “file not found” errors.

```powershell
ffmpeg -version
```

Any version printout is fine. `not recognized` means PATH is stale: new terminal.

### 3.3 Create a virtual environment (do this once)

From the factory root:

```powershell
cd C:\Users\kochi\Downloads\video-factory\video-factory
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `Activate.ps1` is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Every later session you only need:

```powershell
cd C:\Users\kochi\Downloads\video-factory\video-factory
.\.venv\Scripts\Activate.ps1
```

The prompt should start with `(.venv)`.

### 3.4 Prove fonts and FFmpeg

```powershell
python factory\diagnose.py
```

Expected lines:

```text
platform: win32
latin   : ...\fonts\LatinFallback.ttf
cjk     : ...\fonts\CJKFallback.ttf
probe   : ...\out\cjk_probe.png
```

Open `out\cjk_probe.png`. You must see English on the first line and
`沉没成本  激励` on the second. Boxes = fonts missing; copy the three
files from `fonts/` again.

### 3.5 Start the app

```powershell
python factory\app.py
```

Leave this window open. A browser should open
[http://127.0.0.1:8765](http://127.0.0.1:8765).
If it does not, paste that address yourself.

You should see the lesson list (`ECON-IN-01`, `ECON-OC-01`, `ECON-SC-01`).

### 3.6 First successful click (no speech)

1. Click **ECON-IN-01**.
2. Leave **Regenerate speech** **unticked**.
3. Click **Preview slides only**.
4. Wait until the log says `slides-only`.
5. Stills appear under **Slides**.

That proves Python, fonts, and the console. No TTS, no FFmpeg mux.

### 3.7 First captions check

1. Same lesson still selected.
2. Tick the three cells you care about (English / Putonghua / Cantonese).
3. Tick **Titles follow the cell** if you want 简体 / 繁體 on the picture.
4. Click **Preview captions**.
5. Check wrapping in the three-column gallery.

### 3.8 First videos

1. Need the network.
2. Tick **Regenerate speech** only on the first full build of a lesson
   (or after you change YAML / voice / rate / pitch / volume).
3. Click **Build this lesson**.
4. Wait. First TTS for three languages is several minutes.
5. Three players appear under **Cells**.
6. Open `out\ECON-IN-01\cells\` for the MP4 files.

Do **not** close the terminal while the log says `Running…`.

---

## 4. macOS

```bash
# Homebrew Python + FFmpeg (once)
brew install python ffmpeg

cd /path/to/video-factory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python factory/diagnose.py
python factory/app.py
```

Open http://127.0.0.1:8765 and follow §3.6–3.8.

If `python3` is the system 3.9, install 3.12 from python.org or `brew`
and call it explicitly (`python3.12 -m venv .venv`).

---

## 5. Linux (Debian / Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg
cd /path/to/video-factory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python factory/diagnose.py
python factory/app.py
```

Fedora: `sudo dnf install python3 ffmpeg` then the same `venv` block.

---

## 6. Command line instead of the browser

Same venv, same folder. The console is optional.

```bash
python factory/validate.py lessons/ECON-IN-01.yaml
python factory/build.py lessons/ECON-IN-01.yaml --slides-only
python factory/build.py lessons/ECON-IN-01.yaml --match-titles --caption-preview
python factory/build.py lessons/ECON-IN-01.yaml --match-titles
python factory/build.py --all --match-titles --cells zhhk --caption-preview
```

| Flag | Use |
|------|-----|
| `--slides-only` | PNG stills, no TTS |
| `--caption-preview` | Stills + caption bars, no TTS |
| `--match-titles` | EN / 简体 / 繁體 titles on the matching cell |
| `--cells en,zhcn,zhhk` | Build only those arms |
| `--force-tts` | Redo speech |
| `--no-tts` | Use MP3s already in the output root under `<ID>/audio/` |
| `--all` | Every YAML in `lessons/` |
| `--out <dir>` | Lesson output root. Wins over `$VF_OUT`. Unset, the default is `<Downloads>/video-factory-out` |

---

## 7. After setup: daily start (30 seconds)

```powershell
cd C:\Users\kochi\Downloads\video-factory\video-factory
.\.venv\Scripts\Activate.ps1
python factory\app.py
```

macOS / Linux:

```bash
cd /path/to/video-factory
source .venv/bin/activate
python factory/app.py
```

Then work only in the browser. YAML files live in `lessons/`.
New files dropped onto the page are saved there automatically.

Build files go to your Downloads folder (`video-factory-out`), not into this
checkout. Set `VF_OUT` only when you want a different folder. See “Build files
outside the repo” below.

---

## 8. What you must not skip

These are the steps that, if missed, look like “the app is broken”:

1. **Wrong folder.** Commands run from the directory that contains `factory/`
   and `lessons/`, not from `factory/` itself and not from `Downloads/`.
2. **No venv activation.** `pip install` into a different Python than
   `python factory/app.py` produces `ModuleNotFoundError: yaml` or `PIL`.
3. **Old terminal after installing FFmpeg.** PATH does not update in an
   already-open window.
4. **Closing the console terminal.** The page at `:8765` dies with it.
5. **Ticking Regenerate speech** when you only wanted slides. That re-calls
   Edge TTS for every beat.
6. **Missing `fonts/` files.** Slides render boxes or faint Latin titles.
7. **Offline first full build.** Edge TTS will fail; slides-only still works.

---

## 9. Failures you will actually see

| Symptom | Cause | Fix |
|---------|--------|-----|
| `python` not recognized | Python not on PATH | Reinstall 3.12 with “Add to PATH”; new terminal |
| `ModuleNotFoundError` | Packages not in this interpreter | Activate `.venv`, `pip install -r requirements.txt` |
| `WinError 2` / `ffmpeg` file not found | No FFmpeg on PATH | §3.2; new terminal; `pip install imageio-ffmpeg` |
| `WinError 5` Access is denied | Bad ffmpeg path resolved to `.` | Update `factory/ff.py`; install Gyan FFmpeg |
| Page will not load | App not running, or wrong port | Terminal must show `8765`; do not use another port |
| Chinese is boxes | No CJK font | Confirm `fonts/CJKFallback.ttf`; run `diagnose.py` |
| English title unreadable | Old factory without bundled Latin | Copy `fonts/LatinFallback*.ttf` and current `slides.py` |
| TTS error / empty MP3 | No network, or Edge blocked | Stay on slides-only; retry later; or drop vendor MP3s and `--no-tts` |
| Only one language built | Cell checkboxes | Tick English / Putonghua / Cantonese as needed |
| Captions vertical | Old `mux.py` | Copy the current `factory/mux.py` |

Logs: `<output root>/lessons/<ID>/build.log` and `<output root>/last_build.log`
(Downloads `video-factory-out` unless `VF_OUT` or `--out` overrides it).
The console also has **Open last_build.log**.

---

## 10. Optional environment variables

Set these in the same terminal *before* `python factory/app.py`
only if you need to override a default.

```powershell
$env:VF_VOICE_EN="en-US-JennyNeural"
$env:VF_VOICE_ZH_CN="zh-CN-XiaoxiaoNeural"
$env:VF_VOICE_ZH_HK="zh-HK-HiuMaanNeural"
$env:VF_TTS_RATE="+0%"
$env:VF_TTS_VOLUME="+0%"
$env:VF_TTS_PITCH="+0Hz"
$env:VF_FONT_LATIN="C:\Windows\Fonts\arial.ttf"
$env:VF_FONT_CJK="C:\Windows\Fonts\msyh.ttc"
$env:VF_FFMPEG="C:\ffmpeg\bin\ffmpeg.exe"
```

The console Options panel sets the voice / rate / caption values for that
build without touching the environment.

### Build files outside the repo

Slides, audio, caption overlays, cells, YouTube sidecars, packs, PDFs, and
logs go to the lesson output root. Lesson YAML stays in the repo.

When `VF_OUT` and `--out` are both unset, that root is a folder in the
current user's Downloads:

- Windows: `%USERPROFILE%\Downloads\video-factory-out`
- macOS and Linux: `~/Downloads/video-factory-out`

The factory creates `video-factory-out` if it is missing. A machine that
already has User `VF_OUT` set keeps that path. Set `VF_OUT`, or pass `--out`,
only to use a different directory. If Downloads cannot be resolved or created,
the factory falls back to `<repo>\out`.

```powershell
# optional override — omit this to keep the Downloads default
$env:VF_OUT = "$env:USERPROFILE\vf-custom-out"
python factory\app.py
```

The same switch on one command. `--out` wins over `VF_OUT` when both are set:

```powershell
python factory\build.py lessons\STAT\STAT-M01-T02-MEAN.yaml --out "$env:USERPROFILE\vf-custom-out" --slides-only
python factory\app.py --out "$env:USERPROFILE\vf-custom-out"
```

Copy an existing `out` folder to the new directory if you want to keep renders
you already have. The factory does not move lesson YAML.

---

## 11. What “done with setup” allows next

- Faculty / RA writes YAML → see `docs/SCHEMA.md`, `docs/AUTHORING_PROMPT.md`, and `docs/QA_CHECKLIST.md`. Revise an existing file with `docs/REVISE_PROMPT.md`.
- Day-to-day production → `docs/SOP.md`.
- Windows-only FFmpeg notes → `docs/WINDOWS.md`.

You do not need those documents to start the app. You need this one.
