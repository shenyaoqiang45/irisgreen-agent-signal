"""Font stack for Linux tests and Windows PC preview.

Search order:
1. Noto Sans CJK (SC preferred)
2. Source Han Sans
3. Microsoft YaHei / SimHei / other system CJK fonts
4. DejaVu Sans / Arial (ASCII)
5. Pillow's built-in default font (ASCII always available)

Chinese glyphs require a CJK font. If none is installed, ASCII still
renders and CJK characters may appear as empty boxes (tofu). See the
package README for install notes.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

from PIL import ImageFont

# (path, preferred TTC/OTC face index or None, is_cjk)
_CANDIDATES: tuple[tuple[str, int | None, bool], ...] = (
    # Linux — Noto / Source Han
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2, True),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2, True),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 2, True),
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", 0, True),
    ("/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf", 0, True),
    ("/usr/share/fonts/opentype/source-han-sans/SourceHanSansCN-Regular.otf", 0, True),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0, True),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0, True),
    # Windows
    (r"C:\Windows\Fonts\msyh.ttc", 0, True),
    (r"C:\Windows\Fonts\msyhbd.ttc", 0, True),
    (r"C:\Windows\Fonts\simhei.ttf", 0, True),
    (r"C:\Windows\Fonts\simsun.ttc", 0, True),
    (r"C:\Windows\Fonts\msjh.ttc", 0, True),
    (r"C:\Windows\Fonts\mingliu.ttc", 0, True),
    (r"C:\Windows\Fonts\msyh.ttf", 0, True),
    # ASCII fallbacks
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0, False),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0, False),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0, False),
    (r"C:\Windows\Fonts\arial.ttf", 0, False),
    (r"C:\Windows\Fonts\calibri.ttf", 0, False),
    (r"C:\Windows\Fonts\tahoma.ttf", 0, False),
    (r"C:\Windows\Fonts\segoeui.ttf", 0, False),
)

_FC_QUERIES_CJK = (
    "Noto Sans CJK SC",
    "Noto Sans CJK",
    "Source Han Sans SC",
    "Source Han Sans CN",
    "Microsoft YaHei",
    "SimHei",
    "WenQuanYi Micro Hei",
)
_FC_QUERIES_ANY = ("DejaVu Sans", "Liberation Sans", "Arial", "sans-serif")


@dataclass(frozen=True)
class FontChoice:
    path: str | None
    index: int
    size: int
    is_cjk: bool
    family: str
    builtin: bool = False


def _fc_match(query: str) -> str | None:
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", query],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    path = (result.stdout or "").strip()
    if path and os.path.isfile(path):
        return path
    return None


def _face_name(path: str, index: int) -> str:
    try:
        font = ImageFont.truetype(path, size=16, index=index)
        return " ".join(part for part in font.getname() if part)
    except Exception:
        return os.path.basename(path)


def _pick_index(path: str, preferred: int | None) -> int:
    prefer = ("SC", "CN", "GB", "Hans", "YaHei", "SimHei", "Gothic")
    if preferred is not None:
        try:
            ImageFont.truetype(path, size=12, index=preferred)
            name = _face_name(path, preferred)
            if any(token.lower() in name.lower() for token in prefer) or preferred == 0:
                # Still scan in case a better SC face exists.
                pass
        except Exception:
            preferred = None
    best = preferred if preferred is not None else 0
    for index in range(16):
        try:
            ImageFont.truetype(path, size=12, index=index)
        except Exception:
            if index == 0:
                continue
            break
        name = _face_name(path, index)
        if any(token.lower() in name.lower() for token in prefer):
            return index
    return best


def _iter_paths() -> Iterable[tuple[str, int | None, bool]]:
    yield from _CANDIDATES
    for query in _FC_QUERIES_CJK:
        path = _fc_match(query)
        if path:
            yield path, None, True
    for query in _FC_QUERIES_ANY:
        path = _fc_match(query)
        if path:
            yield path, None, False


@lru_cache(maxsize=1)
def resolve_font() -> FontChoice:
    """Pick the best available system font (CJK preferred)."""
    seen: set[str] = set()
    ascii_fallback: FontChoice | None = None
    for path, preferred, is_cjk in _iter_paths():
        if not path or path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            index = _pick_index(path, preferred)
            ImageFont.truetype(path, size=16, index=index)
        except Exception:
            continue
        choice = FontChoice(
            path=path,
            index=index,
            size=16,
            is_cjk=is_cjk or _looks_cjk(_face_name(path, index)),
            family=_face_name(path, index),
            builtin=False,
        )
        if choice.is_cjk:
            return choice
        if ascii_fallback is None:
            ascii_fallback = choice
    if ascii_fallback is not None:
        return ascii_fallback
    return FontChoice(
        path=None,
        index=0,
        size=24,
        is_cjk=False,
        family="Pillow Default",
        builtin=True,
    )


def _looks_cjk(name: str) -> bool:
    tokens = (
        "cjk",
        "yahei",
        "simhei",
        "simsun",
        "source han",
        "noto sans cjk",
        "gothic",
        "ming",
        "hei",
        "wqy",
        "wenquanyi",
        "noto serif cjk",
    )
    lowered = name.lower()
    return any(token in lowered for token in tokens)


def load_font(size: int, choice: FontChoice | None = None) -> ImageFont.ImageFont:
    """Load a PIL font at ``size`` from the resolved stack."""
    info = choice or resolve_font()
    if info.builtin or not info.path:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()
    return ImageFont.truetype(info.path, size=size, index=info.index)


def font_supports_cjk(choice: FontChoice | None = None) -> bool:
    info = choice or resolve_font()
    return info.is_cjk
