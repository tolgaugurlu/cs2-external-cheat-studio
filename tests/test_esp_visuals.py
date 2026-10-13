import unittest
from esp_visuals import BONE_IDS, CanvasSink, EspRenderer, player_bounds, sample_pose, overlaps
from unittest.mock import Mock


class Sink:
    def begin(self): self.calls = {}
    def end(self): pass
    def draw(self, key, kind, coords, **options): self.calls[key] = (kind, coords, options)
    def measure(self, text, size): return len(text) * size * .6


class VisualTests(unittest.TestCase):
    def test_lock_changes_do_not_flash_palette(self):
        sink=Sink();renderer=EspRenderer(sink)
        renderer.begin((1920,1080))
        renderer.player(1,sample_pose(300,100,250),100,20,targeted=False)
        before=dict(sink.calls)
        renderer.begin((1920,1080))
        renderer.player(1,sample_pose(300,100,250),100,20,targeted=True)
        self.assertEqual(before,sink.calls)

    def test_moving_arm_does_not_stretch_bounds(self):
        pose = sample_pose(300, 100, 250)
        bounds = player_bounds(pose, (1920, 1080))
        pose[11] = (1000, 500)
        self.assertEqual(player_bounds(pose, (1920, 1080)), bounds)
        self.assertTrue({24, 25, 27}.issubset(BONE_IDS))

    def test_offscreen_or_invalid_pose_is_not_drawn(self):
        self.assertIsNone(player_bounds(sample_pose(-500, 100, 100), (1920, 1080)))
        self.assertIsNone(player_bounds({6: (float('nan'), 0), 2: (10, 20)}, (1920, 1080)))

    def test_overlapping_players_get_separate_label_rects(self):
        sink = Sink()
        renderer = EspRenderer(sink)
        renderer.begin((1920, 1080))
        for i in range(2):
            renderer.player(i, sample_pose(300 + i * 5, 100, 250), 100, 20)
        self.assertEqual(len(renderer.label_rects), 2)
        self.assertFalse(overlaps(*renderer.label_rects))
        for _, _, options in sink.calls.values():
            self.assertNotIn(options.get('fill'), ('black', '#000000', '#000'))

    def test_silhouette_renders_without_optional_information_layer(self):
        sink=Sink();renderer=EspRenderer(sink);renderer.begin((1920,1080))
        self.assertTrue(renderer.player('pawn',sample_pose(300,100,250),100,None,
                        silhouette=True,skeleton=False,boxes=False,health_bar=False,labels=False))
        self.assertIn(('pawn','head'),sink.calls)
        self.assertFalse(any(kind=='text' for kind,_,_ in sink.calls.values()))
        self.assertLessEqual(len(sink.calls),32)

    def test_unchanged_canvas_order_does_not_recreate_or_raise_every_item(self):
        canvas=Mock();canvas.create_line.side_effect=[1,2,3]
        sink=CanvasSink(canvas)
        for frame in range(3):
            sink.begin()
            for key in ('a','b'):
                sink.draw(key,'line',(0,0,frame,frame),fill='white')
            sink.end()
        self.assertEqual(canvas.create_line.call_count,2)
        self.assertEqual(canvas.tag_raise.call_count,2)
        sink.begin();sink.draw('b','line',(0,0,0,0),fill='white');sink.end()
        canvas.delete.assert_called_once_with(1)
