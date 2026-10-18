"""Where lesson YAML lives.

Ids stay stable (GAME-GI-01). Files sit in lessons/<AREA>/ with a flat
lessons/*.yaml fallback so old trees still build.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "lessons"
MODULES = ROOT / "modules"
MINICOURSES = ROOT / "minicourses"
OUT = ROOT / "out"
OUT_LESSONS = OUT / "lessons"
OUT_MODULES = OUT / "modules"
OUT_RESERVED = {"lessons", "modules", "_packs", "_mathtex"}
HIDDEN_DIRS = {"_inbox", "_attic", "_drafts"}


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
    base = Path(root) if root is not None else OUT
    return (base / "modules" if use_mod else base / "lessons") / stem


def existing_out_dir(lid: str, *, module: bool | None = None, root: Path | None = None) -> Path:
    """Prefer out/lessons|modules/<id>; fall back to a leftover out/<id>."""
    modern = out_dir(lid, module=module, root=root)
    if modern.exists():
        return modern
    base = Path(root) if root is not None else OUT
    legacy = base / Path(str(lid)).stem
    if legacy.exists() and legacy.name not in OUT_RESERVED:
        return legacy
    return modern


def media_href(lid: str, *parts: str, module: bool | None = None, root: Path | None = None) -> str:
    dest = existing_out_dir(lid, module=module, root=root)
    base = Path(root) if root is not None else OUT
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


def migrate_out_layout() -> list[str]:
    """Move out/<id> into out/lessons/<id> or out/modules/<id> once."""
    moved: list[str] = []
    if not OUT.is_dir():
        return moved
    OUT_LESSONS.mkdir(parents=True, exist_ok=True)
    OUT_MODULES.mkdir(parents=True, exist_ok=True)
    for child in list(OUT.iterdir()):
        if not child.is_dir() or child.name in OUT_RESERVED or child.name.startswith("."):
            continue
        dest = out_dir(child.name)
        if dest.resolve() == child.resolve():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            n = _merge_move(child, dest)
            if child.exists() and not any(child.iterdir()):
                child.rmdir()
            if n:
                moved.append(f"{child.name} ⇉ {dest.relative_to(OUT).as_posix()} ({n} files)")
            continue
        child.rename(dest)
        moved.append(f"{child.name} → {dest.relative_to(OUT).as_posix()}")
    return moved
