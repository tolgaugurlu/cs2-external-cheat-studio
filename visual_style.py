"""Game contour palettes, targeting bones and a static panel preview."""
PALETTES = {
    'Koral / Mavi': ('#FF8C79', '#75CAFF'),
    'Altın / Mavi': ('#FFD27A', '#75CAFF'),
    'Beyaz / Mavi': ('#F0F4FA', '#75CAFF'),
}
BONES = ((6, 5), (5, 4), (4, 2), (5, 8), (8, 9), (9, 11),
         (5, 13), (13, 14), (14, 16), (2, 22), (22, 23), (23, 24),
         (2, 25), (25, 26), (26, 27))
BONE_IDS = sorted({bone for pair in BONES for bone in pair})


def sample_pose(cx, top, height):
    points = {6: (0, 0), 5: (0, .12), 4: (0, .29), 2: (0, .51),
              8: (-.14, .17), 9: (-.22, .35), 11: (-.10, .43),
              13: (.14, .17), 14: (.22, .35), 16: (.08, .44),
              22: (-.09, .56), 23: (-.12, .78), 24: (-.17, 1),
              25: (.09, .56), 26: (.12, .78), 27: (.17, 1)}
    return {bone: (cx + x * height, top + y * height) for bone, (x, y) in points.items()}
