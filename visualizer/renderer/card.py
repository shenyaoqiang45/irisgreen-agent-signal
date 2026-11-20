import math
from functools import lru_cache

from visualizer.renderer import Renderer
from visualizer.renderer.draw import draw_ring
from visualizer.renderer.fonts import load_font
from visualizer.renderer.typography import blit, rasterize_text


def _wrap(text, font, max_width):
    """Split at word or punctuation boundaries, falling back to character breaks."""
    parts = []
    remaining = text.strip()
    while remaining:
        if font.getlength(remaining) <= max_width:
            parts.append(remaining)
            break
        # If two lines can hold the text, avoid an early punctuation break
        # that would unnecessarily create a third line.
        low, high = 1, len(remaining) - 1
        while low < high:
            mid = (low + high + 1) // 2
            if font.getlength(remaining[:mid]) <= max_width:
                low = mid
            else:
                high = mid - 1
        max_cut = low
        low, high = 1, len(remaining) - 1
        while low < high:
            mid = (low + high) // 2
            if font.getlength(remaining[mid:]) <= max_width:
                high = mid
            else:
                low = mid + 1
        min_cut = low
        if min_cut <= max_cut and font.getlength(remaining[min_cut:]) <= max_width:
            candidates = range(min_cut, max_cut + 1)
            boundaries = [i for i in candidates if remaining[i - 1] in " .,;!?，。；！？"]
            cut = min(boundaries or candidates, key=lambda i: abs(i - len(remaining) / 2))
            parts.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip()
            continue
        cut = max_cut
        boundaries = [i for i in range(1, cut + 1) if remaining[i - 1] in " .,;!?，。；！？"]
        if boundaries and boundaries[-1] >= cut // 2:
            cut = boundaries[-1]
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return parts


class CardRenderer(Renderer):
    @lru_cache(maxsize=256)
    def _label(self, text, size):
        return rasterize_text(text, max_width=self.display.width - 40, font_size=size, choice=self.font_choice)

    def _content(self, lines, *, include_source=False):
        width = self.display.width - 40
        groups = []
        for size in range(48, 15, -2):
            groups = []
            font = load_font(size, self.font_choice)
            for text in lines:
                if text:
                    parts = _wrap(text, font, width)
                    if parts:
                        groups.append([(part, size, self._label(part, size)) for part in parts])
            rows = sum(len(group) for group in groups) + int(include_source)
            if max(0, rows - 1) * (size + 8) <= self.display.height - 72:
                break
        if max(0, rows - 1) * (size + 8) > self.display.height - 72:
            limit = (self.display.height - 72) // (size + 8) + 1 - int(include_source)
            visible = [row for group in groups for row in group][:limit]
            if visible:
                text, size, _ = visible[-1]
                font = load_font(size, self.font_choice)
                while text and font.getlength(text + "…") > width:
                    text = text[:-1]
                visible[-1] = (text + "…", size, self._label(text + "…", size))
            groups = [visible]
        return groups

    def frame(self, card, now):
        frame = self.empty_frame()
        if card is None:
            return frame
        x = 20
        has_source = bool(card.lines and card.lines[0])
        groups = self._content(card.lines[1:], include_source=has_source)
        rows = [row for group in groups for row in group]
        size = rows[0][1] if rows else 48
        count = len(rows) + int(has_source)
        pitch = min(68, (self.display.height - 72) // max(1, count - 1))
        y = 36
        radius = 17 + card.accent + 5 * math.sin(now * card.pulse)
        draw_ring(frame, 48, y, radius, 2)
        if has_source:
            font = load_font(size, self.font_choice)
            source = card.lines[0]
            width = self.display.width - 128
            if font.getlength(source) > width:
                while source and font.getlength(source + "…") > width:
                    source = source[:-1]
                source += "…"
            mask = self._label(source, size)
            blit(frame, mask, 96 + mask.shape[1] // 2, y)
            y += pitch
        for _, _, mask in rows:
            blit(frame, mask, x + mask.shape[1] // 2, y)
            y += pitch
        return frame
