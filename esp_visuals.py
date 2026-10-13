"""Presentation-only ESP primitives, shared by the overlay and its preview."""

import math

PROFILES = ("Dengeli", "Minimal", "Belirgin")
PALETTES = {
    "Koral / Mavi": ("#FF8C79", "#75CAFF"),
    "Altın / Mavi": ("#FFD27A", "#75CAFF"),
    "Beyaz / Mavi": ("#F0F4FA", "#75CAFF"),
}
BONES = ((6, 5), (5, 4), (4, 2), (5, 8), (8, 9), (9, 11),
         (5, 13), (13, 14), (14, 16), (2, 22), (22, 23), (23, 24),
         (2, 25), (25, 26), (26, 27))
BONE_IDS = sorted({bone for pair in BONES for bone in pair})
OUTLINE = "#10151F"
PANEL = "#141D2A"
TEXT = "#F0F4FA"
MUTED = "#A7B7CA"


class CanvasSink:
    """Reuse Tk canvas items instead of destroying every object each frame."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.items = {}
        self.used = set()
        self.fonts = {}
        self.order = []
        self.previous_order = []

    def begin(self):
        self.used.clear()
        self.order = []

    def end(self):
        for key in self.items.keys() - self.used:
            self.canvas.delete(self.items.pop(key)[0])
        if self.order != self.previous_order:
            for key in self.order:
                self.canvas.tag_raise(self.items[key][0])
            self.previous_order = self.order

    def draw(self, key, kind, coords, **options):
        self.used.add(key)
        self.order.append(key)
        record = self.items.get(key)
        if record is not None and record[1] != kind:
            self.canvas.delete(record[0])
            record = None
        if record is None:
            item = getattr(self.canvas, "create_" + kind)(*coords, **options)
        else:
            item, _, previous_coords, previous_options = record
            if previous_coords != coords:
                self.canvas.coords(item, *coords)
            if previous_options != options:
                self.canvas.itemconfigure(item, **options)
        self.items[key] = (item, kind, coords, options)

    def measure(self, text, size):
        from tkinter.font import Font
        if size not in self.fonts:
            self.fonts[size] = Font(root=self.canvas, family="Segoe UI", size=-size, weight="bold")
        return self.fonts[size].measure(text)


def player_bounds(coords, viewport):
    """Use head/torso/feet so a moving weapon arm does not stretch the box."""
    width, height = viewport
    valid = {k: p for k, p in coords.items() if len(p) == 2 and
             all(math.isfinite(v) and abs(v) < max(width, height) * 4 for v in p)}
    body = [valid[k] for k in (6, 5, 4, 2, 22, 23, 24, 25, 26, 27) if k in valid]
    if len(body) < 3 or 6 not in valid or 2 not in valid:
        return None
    top = min(p[1] for p in body)
    bottom = max(p[1] for p in body)
    body_height = bottom - top
    if body_height < 10 or body_height > height * 1.7:
        return None
    center = (valid[6][0] + valid[2][0]) / 2
    half_width = max(body_height * 0.22, min(body_height * 0.35,
                                          max(abs(p[0] - center) for p in body) + 3))
    box = (center - half_width, top - body_height * 0.08,
           center + half_width, bottom + body_height * 0.035)
    if box[2] < 0 or box[0] > width or box[3] < 0 or box[1] > height:
        return None
    return box


def overlaps(a, b):
    return a[0] < b[2] + 3 and a[2] + 3 > b[0] and a[1] < b[3] + 3 and a[3] + 3 > b[1]


def sample_pose(cx, top, height):
    points = {6: (0, 0), 5: (0, .12), 4: (0, .29), 2: (0, .51),
              8: (-.14, .17), 9: (-.22, .35), 11: (-.10, .43),
              13: (.14, .17), 14: (.22, .35), 16: (.08, .44),
              22: (-.09, .56), 23: (-.12, .78), 24: (-.17, 1),
              25: (.09, .56), 26: (.12, .78), 27: (.17, 1)}
    return {k: (cx + x * height, top + y * height) for k, (x, y) in points.items()}


class EspRenderer:
    def __init__(self, sink):
        self.sink = sink
        self.label_rects = []

    def begin(self, viewport):
        self.viewport = viewport
        self.label_rects = []
        self.sink.begin()

    def end(self):
        self.sink.end()

    def line(self, key, points, color, width):
        self.sink.draw((key, "shadow"), "line", points, fill=OUTLINE, width=width + 2,
                       capstyle="round", joinstyle="round")
        self.sink.draw((key, "line"), "line", points, fill=color, width=width,
                       capstyle="round", joinstyle="round")

    def label(self, key, cx, preferred_y, below_y, text, color, size):
        width = self.sink.measure(text, size) + 18
        height = size + 12
        screen_w, screen_h = self.viewport
        x = max(4, min(screen_w - width - 4, cx - width / 2))
        for requested_y in (preferred_y - height, below_y + 8, preferred_y - 2 * height - 4):
            y = max(4, min(screen_h - height - 4, requested_y))
            rect = (x, y, x + width, y + height)
            if any(overlaps(rect, occupied) for occupied in self.label_rects):
                continue
            self.label_rects.append(rect)
            self.sink.draw((key, "bg"), "rectangle", rect, fill=PANEL, outline="#324256", width=1)
            self.sink.draw((key, "accent"), "rectangle", (x, y + 2, x + 2, y + height - 2), fill=color, outline="")
            self.sink.draw((key, "text"), "text", (x + width / 2 + 1, y + height / 2),
                           text=text, fill=TEXT, font=("Segoe UI", -size, "bold"))
            return rect
        return None

    def player(self, key, coords, health, distance, enemy=True, targeted=False,
               profile="Dengeli", palette="Koral / Mavi", text_scale=100,
               skeleton=True, health_bar=True, labels=True, boxes=True, silhouette=False):
        box = player_bounds(coords, self.viewport)
        if box is None or (distance is not None and not math.isfinite(distance)):
            return False
        x1, y1, x2, y2 = box
        box_h = y2 - y1
        scale = max(.85, min(1.6, self.viewport[1] / 1080))
        bold = profile == "Belirgin"
        minimal = profile == "Minimal"
        color = PALETTES.get(palette, PALETTES["Koral / Mavi"])[0 if enemy else 1]
        weight = (2.6 if bold else 1.8) * scale
        font_size = round((15 if bold else 13) * scale * max(.8, min(1.6, text_scale / 100)))
        if silhouette and hasattr(self.sink,'draw_silhouette'):
            self.sink.draw_silhouette(key,coords,box_h,color)
        elif silhouette:


            torso = (tuple(v for b in (5,13,25,22,8) for v in coords[b])
                     if all(b in coords and all(math.isfinite(v) and abs(v)<max(self.viewport)*4 for v in coords[b])
                            for b in (5,13,25,22,8)) else None)
            limbs=[]
            for a,b in ((6,5),(5,8),(8,9),(9,11),(5,13),(13,14),(14,16),
                        (2,22),(22,23),(23,24),(2,25),(25,26),(26,27)):
                if a not in coords or b not in coords:
                    continue
                points=(*coords[a],*coords[b])
                if not all(math.isfinite(v) and abs(v)<max(self.viewport)*4 for v in points):
                    continue
                thickness=.073 if a in (22,25) else .055
                limbs.append((a,b,points,max(2,min(70,box_h*thickness))))

            for layer in ('outer','inner'):
                for a,b,points,width in limbs:
                    self.sink.draw((key,'limb-'+layer,a,b),'line',points,
                                   fill=color if layer=='outer' else '#243247',
                                   width=width+(2 if layer=='outer' else 0),
                                   capstyle='round',joinstyle='round')
                if torso:
                    self.sink.draw((key,'body-'+layer),'polygon',torso,fill='#243247',
                                   outline=color if layer=='outer' else '',
                                   width=max(1.5,box_h*.012),joinstyle='round')
            hx,hy=coords[6];radius=max(2,min(32,box_h*.047))
            self.sink.draw((key,'head'),'oval',(hx-radius,hy-radius,hx+radius,hy+radius),
                           fill='#31435A',outline=color,width=max(1.5,box_h*.012))
        if skeleton and not minimal and box_h >= 52 * scale:
            for start, end in BONES:
                if start in coords and end in coords:
                    points = (*coords[start], *coords[end])
                    if all(math.isfinite(v) and abs(v) < max(self.viewport) * 4 for v in points):
                        self.line((key, "bone", start, end), points, "#E3EAF2", 1.2 * scale)
        if boxes:
            seg_x = min((x2 - x1) * .27, 22 * scale)
            seg_y = min(box_h * .17, 28 * scale)
            for index, (x, y, dx, dy) in enumerate(((x1, y1, 1, 1), (x2, y1, -1, 1),
                                                   (x1, y2, 1, -1), (x2, y2, -1, -1))):
                self.line((key, "corner", index), (x + dx * seg_x, y, x, y, x, y + dy * seg_y), color, weight)
        if health_bar:
            ratio = max(0, min(1, health / 100))
            bar_w = max(3, round(4 * scale))
            bar_x = x1 - 9 * scale
            hp_color = "#6FE0B1" if ratio > .55 else "#F5CB76" if ratio > .25 else "#FF817B"
            self.sink.draw((key, "health-bg"), "rectangle", (bar_x - bar_w - 1, y1 - 1, bar_x + 1, y2 + 1),
                           fill=OUTLINE, outline="#263444", width=1)
            if ratio > 0:
                self.sink.draw((key, "health-fill"), "rectangle", (bar_x - bar_w, y2 - box_h * ratio, bar_x, y2),
                               fill=hp_color, outline="")
            if health < 100 and box_h >= 65 * scale and not minimal:
                self.label((key, "hp"), bar_x - 12 * scale, y1 + 3, y2,
                           str(max(0, int(health))), hp_color, max(10, font_size - 2))
        if labels:
            relation = "RAKİP" if enemy else "TAKIM"
            text = (relation if distance is None else f"{int(max(0,distance))} m" if minimal
                    else f"{relation}  ·  {int(max(0,distance))} m")
            self.label((key, "label"), (x1 + x2) / 2, y1 - 8 * scale, y2,
                       text, color, font_size)
        return True

    def banner(self, key, title, detail, fraction=0, color="#FFD27A", y=30):
        width = min(340, self.viewport[0] - 24)
        x = (self.viewport[0] - width) / 2
        self.sink.draw((key, "panel"), "rectangle", (x, y, x + width, y + 66),
                       fill=PANEL, outline="#324256", width=1)
        self.sink.draw((key, "title"), "text", (x + 14, y + 19), text=title, anchor="w",
                       fill=color, font=("Segoe UI", -14, "bold"))
        self.sink.draw((key, "detail"), "text", (x + 14, y + 39), text=detail, anchor="w",
                       fill=MUTED, font=("Segoe UI", -12))
        self.sink.draw((key, "track"), "rectangle", (x + 14, y + 53, x + width - 14, y + 57),
                       fill="#2A384B", outline="")
        progress = max(0, min(1, fraction))
        if progress:
            self.sink.draw((key, "fill"), "rectangle", (x + 14, y + 53, x + 14 + (width - 28) * progress, y + 57),
                           fill=color, outline="")
