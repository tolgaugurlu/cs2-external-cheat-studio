from pathlib import Path
import struct
import tempfile
import time
import unittest

from map_visibility import CollisionMap, MapVisibility, MapSignalServer, segment_distance_sq
from focus_engine import aim_angles,step_angles,visible_sample


def fixture(path,low=-2,high=2):

    triangles = [((10,low,-100),(10,high,-100),(10,high,100)),
                 ((10,low,-100),(10,high,100),(10,low,100))]
    data = b'CS2BVH01'+struct.pack('<II',1,2)
    data += struct.pack('<6f4i',10,low,-100,10,high,100,-1,-1,0,2)
    for a,b,c in triangles:
        data += struct.pack('<9f',*a,*(b[i]-a[i] for i in range(3)),*(c[i]-a[i] for i in range(3)))
    path.write_bytes(data)
    return CollisionMap(path)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'wall.bvh'
        self.geometry = fixture(self.path)
        self.addCleanup(self.geometry.close)

    def test_wall_blocks_both_directions_and_zero_thickness(self):
        self.assertFalse(self.geometry.visible((0,0,4),(20,0,4)))
        self.assertFalse(self.geometry.visible((20,0,4),(0,0,4)))
        self.assertTrue(self.geometry.visible((0,0,4),(5,0,4)))
        self.assertTrue(self.geometry.visible((0,0,4),(20,8,4)))

    def test_parallel_and_degenerate_rays(self):
        self.assertTrue(self.geometry.visible((5,0,4),(5,5,4)))
        self.assertFalse(self.geometry.visible((0,0,4),(0,0,4)))
        self.assertFalse(self.geometry.visible((0,0,4),(float('nan'),0,4)))

    def test_hidden_head_selects_exposed_arm_without_crosshair_condition(self):
        project=lambda point:(point[0],point[1])
        pose={6:(20,0,7),4:(20,0,4),9:(20,8,4)}
        result=visible_sample(pose,6,(0,0,4),project,self.geometry,(0,0),100)
        self.assertEqual(result[0],9)
        pose[9]=(20,0,4)
        self.assertIsNone(visible_sample(pose,6,(0,0,4),project,self.geometry,(0,0),100))

    def test_fov_is_enforced_even_when_point_is_clear(self):
        self.assertIsNone(visible_sample({6:(20,8,4)},6,(0,0,4),lambda p:(999,999),
                                         self.geometry,(0,0),100))

    def test_truncated_geometry_is_rejected(self):
        data = self.path.read_bytes()[:-1]
        self.geometry.close()
        self.path.write_bytes(data)
        with self.assertRaises(ValueError): CollisionMap(self.path)

    def test_spheres_and_capsules_block_without_flat_polygon_gaps(self):
        data=self.path.read_bytes()
        data=b'CS2BVH02'+data[8:]+struct.pack('<I7f',1,5,8,0,5,8,10,1)
        self.geometry.close()
        self.path.write_bytes(data)
        mesh=CollisionMap(self.path)
        self.addCleanup(mesh.close)
        self.assertFalse(mesh.visible((0,8,4),(20,8,4)))
        self.assertTrue(mesh.visible((0,10,4),(20,10,4)))
        self.assertEqual(segment_distance_sq((0,0,0),(10,0,0),(5,1,0),(5,1,0)),1)
        self.assertEqual(segment_distance_sq((0,0,0),(10,0,0),(0,2,0),(10,2,0)),4)

    def test_stale_or_changed_map_never_reuses_old_geometry(self):
        service=MapVisibility(self.temp.name)
        service.name='de_dust2';service.geometry=self.geometry
        service.accept_state({'map':{'name':'de_dust2'}})
        self.assertIs(service.snapshot(),self.geometry)
        service.accept_state({'map':{'name':'de_mirage'}})
        self.assertIsNone(service.snapshot())
        service.accept_state({'map':{'name':'de_dust2'}})
        service.last_signal=time.monotonic()-4
        self.assertIsNone(service.snapshot())
        service.accept_state({'map':{'name':'../../de_dust2'}})
        self.assertIsNone(service.snapshot())


class SignalOwnershipTests(unittest.TestCase):
    def test_second_listener_cannot_take_the_same_local_port(self):
        from http.server import BaseHTTPRequestHandler
        with MapSignalServer(('127.0.0.1',0),BaseHTTPRequestHandler) as first:
            with self.assertRaises(OSError):
                MapSignalServer(first.server_address,BaseHTTPRequestHandler)


class AngleTests(unittest.TestCase):
    def test_exact_angles_and_recoil(self):
        self.assertEqual(aim_angles((0,0,0),(10,0,0)),(0,0))
        self.assertEqual(aim_angles((0,0,0),(0,10,0)),(0,90))
        self.assertAlmostEqual(aim_angles((0,0,0),(10,0,10))[0],-45)
        self.assertEqual(aim_angles((0,0,0),(10,0,0),(2,3)),(-4,-6))

    def test_sharp_mode_has_no_hidden_speed_cap(self):
        self.assertEqual(step_angles((0,0),(20,90),.002,True,50,.1),(20,90))

    def test_soft_mode_shortest_yaw_and_frame_independence(self):
        value=step_angles((0,179),(0,-179),.01,False,10,100)
        self.assertGreater(value[1],179)
        once=step_angles((0,0),(10,10),.02,False,10,100)
        twice=step_angles(step_angles((0,0),(10,10),.01,False,10,100),(10,10),.01,False,10,100)
        self.assertAlmostEqual(once[0],twice[0])
