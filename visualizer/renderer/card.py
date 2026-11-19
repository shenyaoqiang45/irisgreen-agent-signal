import math
from functools import lru_cache

from visualizer.renderer import Renderer
from visualizer.renderer.draw import draw_ring
from visualizer.renderer.fonts import load_font
from visualizer.renderer.typography import blit, rasterize_text


class CardRenderer(Renderer):
    @lru_cache(maxsize=256)
    def _label(self, text, size):
        return rasterize_text(text, max_width=590, font_size=size, choice=self.font_choice)

    def frame(self, card, now):
        frame = self.empty_frame()
        if card is None:
            return frame
        x = self.display.width // 2
        radius = 17 + card.accent + 5 * math.sin(now * card.pulse)
        draw_ring(frame, x, 80, radius, 2)
        rows = [(line, 48 if i == 1 else 32) for i, line in enumerate(card.lines) if line]
        y = 155
        spare = max(0, 6 - len(rows))
        for line, size in rows:
            font = load_font(size, self.font_choice)
            parts = [line]
            if spare and font.getlength(line) > 590:
                # Prefer a balanced break at a space or sentence boundary.
                breaks = [i for i in range(1, len(line)) if line[i - 1] in " .,;!?，。；！？"]
                cut = min(breaks or range(1, len(line)), key=lambda i: abs(i - len(line) / 2))
                parts = [part.strip() for part in (line[:cut], line[cut:]) if part.strip()]
                spare -= len(parts) - 1
            for part in parts:
                blit(frame, self._label(part, size), x, y)
                y += 54
        return frame
