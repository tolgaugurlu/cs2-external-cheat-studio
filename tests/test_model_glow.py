import unittest

from model_glow import ModelGlow, wait_contour_frame
from offset_manager import field_offset


class GlowTests(unittest.TestCase):
    def setUp(self):
        self.schema = {
            'C_BaseModelEntity': {'fields': {'m_Glow': 200}},
            'CGlowProperty': {'fields': {'m_iGlowType': 48, 'm_glowColorOverride': 64,
                'm_bGlowing': 81, 'm_bFlashing': 68, 'm_flGlowTime': 72, 'm_flGlowStartTime': 76}}
        }
        self.offset = lambda cls, name: field_offset(self.schema, cls, name)
        self.memory = bytearray(16000)
        self.identity = (100, 200, 1000)
        self.writes = []
        self.is_valid = True
        def write(address, data):
            self.writes.append((address, bytes(data)))
            self.memory[address:address + len(data)] = data
        self.glow = ModelGlow(lambda a, n: bytes(self.memory[a:a + n]), write,
                              self.offset, lambda identity: self.is_valid)

    def test_writes_only_declared_fields_in_schema_fixture(self):
        self.glow.apply(self.identity, '#FF8C79')
        base = 1000 + self.offset('C_BaseModelEntity', 'm_Glow')
        self.assertEqual(self.writes, [
            (base + self.offset('CGlowProperty', 'm_iGlowType'), b'\x03\0\0\0'),
            (base + self.offset('CGlowProperty', 'm_glowColorOverride'), b'\xff\x8c\x79\xff'),
            (base + self.offset('CGlowProperty', 'm_bGlowing'), b'\x01')])
        self.assertNotIn(base + 0x52, [a for a, data in self.writes])

    def test_restore_preserves_nonzero_original_and_color_changes(self):
        address = 1000 + self.glow.fields['m_glowColorOverride']
        self.memory[address:address + 4] = b'\x10\x20\x30\x40'
        original = bytes(self.memory)
        self.glow.apply(self.identity, '#FF8C79')
        self.glow.apply(self.identity, '#75CAFF')
        self.glow.restore_except()
        self.assertEqual(bytes(self.memory), original)

    def test_no_restore_write_into_recycled_entity(self):
        self.glow.apply(self.identity, '#FF8C79')
        self.writes.clear()
        self.is_valid = False
        self.glow.restore_except()
        self.assertEqual(self.writes, [])

    def test_does_not_overwrite_new_game_value_on_restore(self):
        self.glow.apply(self.identity, '#FF8C79')
        address = 1000 + self.glow.fields['m_glowColorOverride']
        self.memory[address:address + 4] = b'abcd'
        self.glow.restore_except()
        self.assertEqual(bytes(self.memory[address:address + 4]), b'abcd')

    def test_flashing_and_timed_effect_are_disabled_then_restored(self):
        import struct
        base=1000
        flashing=base+self.glow.fields['m_bFlashing']
        timer=base+self.glow.fields['m_flGlowTime']
        self.memory[flashing]=1
        self.memory[timer:timer+4]=struct.pack('<f',15.5)
        original=bytes(self.memory)
        self.glow.apply(self.identity,'#FF8C79')
        self.assertEqual(self.memory[flashing],0)
        self.assertEqual(self.memory[timer:timer+4],b'\0'*4)
        self.glow.restore_except()
        self.assertEqual(bytes(self.memory),original)

    def test_short_read_gap_does_not_toggle_model_off(self):
        self.glow.apply(self.identity,'#FF8C79')
        self.writes.clear()
        self.glow.restore_except((),grace=.2)
        self.assertEqual(self.writes,[])
        self.is_valid=None
        self.glow.restore_except()
        self.assertEqual(self.writes,[])
        self.assertIn(self.identity,self.glow.saved)

    def test_updates_use_one_snapshot_without_rewriting_unchanged_fields(self):
        from unittest.mock import Mock
        self.glow.read = Mock(wraps=self.glow.read)
        self.glow.apply(self.identity,'#FF8C79')
        self.assertEqual(self.glow.read.call_count,1)
        self.glow.read.reset_mock()
        self.writes.clear()
        self.glow.apply(self.identity,'#FF8C79')
        self.assertEqual(self.glow.read.call_count,1)
        self.assertEqual(self.writes,[])

    def test_short_snapshot_does_not_partially_write_glow(self):
        self.glow.read = lambda a,n:b'\0'
        with self.assertRaises(OSError): self.glow.apply(self.identity,'#FF8C79')
        self.assertEqual(self.writes,[])

    def test_unknown_identity_is_a_read_gap_and_keeps_original_snapshot(self):
        self.glow.apply(self.identity,'#FF8C79')
        saved=dict(self.glow.saved[self.identity])
        self.writes.clear()
        self.is_valid=None
        with self.assertRaises(OSError): self.glow.apply(self.identity,'#FF8C79')
        self.assertEqual(self.writes,[])
        self.assertEqual(self.glow.saved[self.identity],saved)

    def test_engine_overwrites_are_counted_once_per_player_update(self):
        self.glow.apply(self.identity,'#FF8C79')
        for name,n in (('m_iGlowType',4),('m_glowColorOverride',4),('m_bGlowing',1)):
            address=1000+self.glow.fields[name]
            self.memory[address:address+n]=b'\0'*n
        self.glow.apply(self.identity,'#FF8C79')
        self.assertEqual(self.glow.effect_resets,1)
        self.assertEqual(self.glow.last_overwrites['m_glowColorOverride'],'00000000')
        self.glow.apply(self.identity,'#FF8C79')
        self.assertEqual(self.glow.effect_resets,1)

    def test_permanently_unreadable_identity_does_not_leak_saved_snapshots(self):
        from unittest.mock import patch
        with patch('model_glow.time.monotonic',return_value=1):
            self.glow.apply(self.identity,'#FF8C79')
        self.is_valid=None
        self.writes.clear()
        with patch('model_glow.time.monotonic',return_value=7):
            self.glow.restore_except()
        self.assertFalse(self.glow.saved)
        self.assertFalse(self.glow.last_seen)
        self.assertEqual(self.writes,[])

    def test_game_start_time_is_never_reset_or_restored(self):
        import struct
        address=1000+self.offset('C_BaseModelEntity','m_Glow')+self.offset('CGlowProperty','m_flGlowStartTime')
        for value in (1000.,1000.1,1000.2):
            expected=struct.pack('<f',value)
            self.memory[address:address+4]=expected
            self.glow.apply(self.identity,'#FF8C79')
            self.assertEqual(self.memory[address:address+4],expected)
        self.glow.restore_except()
        self.assertEqual(self.memory[address:address+4],expected)

    def test_overwrite_temporarily_increases_repair_rate_then_returns_to_idle_rate(self):
        from unittest.mock import patch
        with patch('model_glow.time.monotonic',return_value=1):
            self.glow.apply(self.identity,'#FF8C79')
            self.assertEqual(self.glow.interval(),1/240)
        with patch('model_glow.time.monotonic',return_value=2):
            self.glow.apply(self.identity,'#FF8C79')
            self.assertEqual(self.glow.interval(),1/60)
            address=1000+self.glow.fields['m_bGlowing']
            self.memory[address]=0
            self.glow.apply(self.identity,'#FF8C79')
            self.assertEqual(self.glow.interval(),1/240)
        with patch('model_glow.time.monotonic',return_value=3):
            self.assertEqual(self.glow.interval(),1/60)

    def test_pacer_subtracts_work_and_never_busy_spins_or_sleeps_after_stop(self):
        from unittest.mock import Mock,patch
        stop=Mock();stop.is_set.return_value=False
        with patch('model_glow.time.monotonic',return_value=1.002),patch('model_glow.time.sleep') as sleep:
            wait_contour_frame(stop,1.,1/240)
            self.assertAlmostEqual(sleep.call_args.args[0],1/240-.002)
            wait_contour_frame(stop,.5,1/240)
            sleep.assert_called_with(.001)
            stop.is_set.return_value=True;sleep.reset_mock()
            wait_contour_frame(stop,1.,1/240)
            sleep.assert_not_called()
