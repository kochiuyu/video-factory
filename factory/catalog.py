"""Where lesson YAML lives.

Ids stay stable (GAME-GI-01). Files sit in lessons/<AREA>/ with a flat
lessons/*.yaml fallback so old trees still build.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "lessons"
MODULES = ROOT / "modules"
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
