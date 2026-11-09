"""Where lesson YAML lives.

Ids stay stable (GAME-GI-01). Files sit in lessons/<AREA>/ with a flat
lessons/*.yaml fallback so old trees still build.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "lessons"
MODULES = ROOT / "modules"
MINICOURSES = ROOT / "minicourses"
# In-repo fallback when Downloads cannot be used. Call out_root() for the live root.
OUT = ROOT / "out"
OUT_LESSONS = OUT / "lessons"
OUT_MODULES = OUT / "modules"
OUT_RESERVED = {"lessons", "modules", "_packs", "_mathtex"}
HIDDEN_DIRS = {"_inbox", "_attic", "_drafts"}
# Per-user default: ~/Downloads/video-factory-out (Windows: %USERPROFILE%\Downloads\...).
DOWNLOADS_OUT_NAME = "video-factory-out"


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _unsafe_out_message(path: Path) -> str:
    return (
        f"Refusing output root {path}. Point VF_OUT or --out at a directory outside the repo, "
        "or leave both unset to use <Downloads>/video-factory-out. "
        "The repo root, its parents, and other in-repo folders are refused so a "
        "build cannot move lesson YAML."
    )


def _allowed_out_root(resolved: Path) -> bool:
    """Allow <repo>/out or any directory outside the repo."""
    repo = ROOT.resolve()
    if resolved == repo or resolved in repo.parents or _is_inside(repo, resolved):
        return False
    if _is_inside(resolved, repo):
        default = OUT.resolve()
        if resolved != default and not _is_inside(resolved, default):
            return False
    return True


def _ensure_safe_out_root(path: Path) -> Path:
    """Allow <repo>/out or any directory outside the repo. Refuse everything else."""
    resolved = path.resolve()
    if not _allowed_out_root(resolved):
        raise SystemExit(_unsafe_out_message(resolved))
    return resolved


def _user_downloads() -> Path | None:
    """``~/Downloads``. ``Path.home()`` is ``%USERPROFILE%`` on Windows."""
    try:
        home = Path.home()
    except (RuntimeError, OSError):
        return None
    if not home.is_absolute():
        return None
    return home / "Downloads"


def _downloads_out() -> Path | None:
    """``<Downloads>/video-factory-out``, created if missing. None when unusable."""
    downloads = _user_downloads()
    if downloads is None:
        return None
    dest = downloads / DOWNLOADS_OUT_NAME
    try:
        resolved = dest.resolve()
    except OSError:
        return None
    if not _allowed_out_root(resolved):
        return None
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    return resolved


def _out_path(value: Path | str) -> Path:
    """Absolute output directory. Relative values are rooted at the repo."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return _ensure_safe_out_root(path)


def out_root(override: Path | str | None = None) -> Path:
    """Lesson output root (slides, audio, cells, packs, logs).

    Precedence: explicit override (CLI ``--out``), then ``VF_OUT``, then
    ``<Downloads>/video-factory-out``, then ``<repo>/out`` when Downloads
    cannot be resolved or created. Lesson YAML is not affected. Relative
    overrides are resolved from the repo root so the console and
    ``build.py`` agree even when their working directories differ.
    """
    if override is not None and str(override).strip():
        return _out_path(override)
    env = os.environ.get("VF_OUT", "").strip()
    if env:
        return _out_path(env)
    downloads = _downloads_out()
    if downloads is not None:
        return downloads
    return OUT


def area_for_id(lid: str) -> str:
    stem = Path(str(lid)).stem
    return stem.split("-", 1)[0] if stem else "MISC"


def _yaml_name(lid_or_file: str) -> str:
    name = Path(str(lid_or_file)).name
    if name.endswith(".yml"):
        name = name[:-4] + ".yaml"
    if not name.endswith(".yaml"):
        name = f"{name}.yaml"
    return name


def lesson_path(lid_or_file: str) -> Path | None:
    name = _yaml_name(lid_or_file)
    area = area_for_id(name)
    candidates = [
        LESSONS / area / name,
        LESSONS / name,
    ]
    if LESSONS.is_dir():
        for sub in sorted(LESSONS.iterdir()):
            if not sub.is_dir() or sub.name.startswith(".") or sub.name in HIDDEN_DIRS:
                continue
            candidates.append(sub / name)
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            return path
    return None


def lesson_dest(lid_or_file: str) -> Path:
    name = _yaml_name(lid_or_file)
    folder = LESSONS / area_for_id(name)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def iter_lesson_paths(*, include_hidden: bool = False) -> list[Path]:
    found: dict[str, Path] = {}
    if not LESSONS.is_dir():
        return []
    for path in LESSONS.glob("*.yaml"):
        found[path.name] = path
    for sub in sorted(LESSONS.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        if sub.name in HIDDEN_DIRS and not include_hidden:
            continue
        for path in sub.glob("*.yaml"):
            found[path.name] = path
    return sorted(found.values(), key=lambda p: p.name)


def iter_module_paths() -> list[Path]:
    if not MODULES.is_dir():
        return []
    return sorted(MODULES.glob("*.yaml"), key=lambda p: p.name)




def iter_minicourse_paths() -> list[Path]:
    """Collections of standalone shorts. Not concatenated modules."""
    if not MINICOURSES.is_dir():
        return []
    return sorted(MINICOURSES.glob("*.yaml"), key=lambda p: p.name)


def is_module_id(lid: str) -> bool:
    stem = Path(str(lid)).stem
    return (MODULES / f"{stem}.yaml").is_file()


def out_dir(lid: str, *, module: bool | None = None, root: Path | None = None) -> Path:
    """Painted outputs: <root>/lessons/<id> or <root>/modules/<id>."""
    stem = Path(str(lid)).stem
    use_mod = is_module_id(stem) if module is None else bool(module)
    base = Path(root) if root is not None else out_root()
    return (base / "modules" if use_mod else base / "lessons") / stem


def existing_out_dir(lid: str, *, module: bool | None = None, root: Path | None = None) -> Path:
    """Prefer out/lessons|modules/<id>; fall back to a leftover out/<id>."""
    modern = out_dir(lid, module=module, root=root)
    if modern.exists():
        return modern
    base = Path(root) if root is not None else out_root()
    legacy = base / Path(str(lid)).stem
    if legacy.exists() and legacy.name not in OUT_RESERVED:
        return legacy
    return modern


def media_href(lid: str, *parts: str, module: bool | None = None, root: Path | None = None) -> str:
    dest = existing_out_dir(lid, module=module, root=root)
    base = Path(root) if root is not None else out_root()
    try:
        rel = dest.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        rel = dest.name
    extra = "/".join(str(p).replace("\\", "/") for p in parts if p)
    return f"/media/{rel}/{extra}" if extra else f"/media/{rel}"


def _merge_move(src: Path, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for item in list(src.iterdir()):
        target = dest / item.name
        if item.is_dir():
            moved += _merge_move(item, target)
            if item.exists() and not any(item.iterdir()):
                item.rmdir()
            continue
        if not target.exists():
            item.rename(target)
            moved += 1
    return moved


def migrate_out_layout(root: Path | None = None) -> list[str]:
    """Move <root>/<id> into <root>/lessons/<id> or <root>/modules/<id> once."""
    moved: list[str] = []
    base = _ensure_safe_out_root(Path(root) if root is not None else out_root())
    if not base.is_dir():
        return moved
    (base / "lessons").mkdir(parents=True, exist_ok=True)
    (base / "modules").mkdir(parents=True, exist_ok=True)
    for child in list(base.iterdir()):
        if not child.is_dir() or child.name in OUT_RESERVED or child.name.startswith("."):
            continue
        dest = out_dir(child.name, root=base)
        if dest.resolve() == child.resolve():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            n = _merge_move(child, dest)
            if child.exists() and not any(child.iterdir()):
                child.rmdir()
            if n:
                moved.append(f"{child.name} ⇉ {dest.relative_to(base).as_posix()} ({n} files)")
            continue
        child.rename(dest)
        moved.append(f"{child.name} → {dest.relative_to(base).as_posix()}")
    return moved
