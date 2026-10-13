"""Exercise only our own off-screen bitmap/window; never capture the desktop."""
import ctypes as C
from ctypes import wintypes as W
import unittest

from esp_visuals import EspRenderer,sample_pose
from gdi_overlay import GdiSink,bind,u


class NativeSurfaceTests(unittest.TestCase):
    def test_pixels_are_shared_surface_reuses_buffer_and_empty_frame_hides_window(self):
        sink=GdiSink(500,500,position=(10000,10000))
        try:
            renderer=EspRenderer(sink)
            address=sink.pixels.value
            renderer.begin((500,500))
            renderer.player(1,sample_pose(250,70,300),100,None,palette='Beyaz / Mavi',
                            silhouette=True,skeleton=False,boxes=False,health_bar=False,labels=False)
            renderer.end()
            self.assertTrue(sink.visible)
            self.assertEqual(sink.surface.get_at((250,70))[:3],(36,50,71))
            self.assertEqual(sink.surface.get_at((1,1))[:3],(0,0,0))

            offset=(70*500+250)*4
            self.assertEqual(C.string_at(address+offset,4),bytes((71,50,36,255)))
            for i in range(8):
                renderer.begin((500,500))
                renderer.player(1,sample_pose(245+i,70,300),100,None,
                                silhouette=True,skeleton=False,boxes=False,health_bar=False,labels=False)
                renderer.end()
                self.assertEqual(address,sink.pixels.value)
                self.assertEqual(len(sink.items),1)
            renderer.begin((500,500));renderer.end()
            self.assertFalse(sink.visible)
        finally:
            sink.close();sink.close()
        self.assertIsNone(sink.surface)
        self.assertIsNone(sink.hwnd)

    def test_gdi_resources_are_released_across_repeated_open_close(self):
        get_count=bind(u,'GetGuiResources',W.DWORD,W.HANDLE,W.DWORD)
        before=get_count(C.c_void_p(-1),0)
        for _ in range(8):
            sink=GdiSink(64,64,position=(10000,10000));sink.close()
        self.assertLessEqual(get_count(C.c_void_p(-1),0),before+1)


if __name__=='__main__':unittest.main()
