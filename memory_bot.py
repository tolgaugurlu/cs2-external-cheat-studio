import pymem
import pymem.process
import time
import math
import ctypes
import struct
import os
import threading
import tkinter as tk
from tkinter import ttk
import logging
import json

import sys
from offset_manager import field_offset, update_offsets, OffsetError
from esp_visuals import PALETTES
from model_glow import ModelGlow, GlowMonitor
from targeting import current_target, team_allowed
from fire_control import FireControl
from flick_shot import FLICK_KEYS
from control_panel import ControlPanel
from focus_engine import aim_loop
from map_visibility import MapVisibility
from visual_context import view_context
from runtime_stats import RuntimeStats
from settings_profiles import ProfileStore, WeaponRuntime


try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
except: ctypes.windll.user32.SetProcessDPIAware()


# V10.5 — Build-matched offset snapshots

_PROC = 'cs2.exe'
_MOD = 'client.dll'
APP_TITLE = 'CS2 Studio'


if getattr(sys, 'frozen', False):

    _BASE_DIR = os.path.dirname(sys.executable)
else:

    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE    = os.path.join(_BASE_DIR, "ayar.json")


class Config:
    enabled=False; fov=120; smooth=12.0; speed_cap=40
    team_mode=1; target_bone=100; aim_key=0x10
    rcs_enabled=True; ghost_esp=False; radar_hack=True; vis_check=True
    rcs_scale=100; rcs_yaw_scale=100; rcs_tuning_version=1
    trigger_enabled=False; trigger_delay=10; trigger_mode="BURST"
    bhop_enabled=True; awp_mode=False
    wall_lock_active=False
    glow_chams=False
    flick_enabled=False; flick_key=0x06
    flick_knife_key=0x33; flick_fov=90; flick_bone=6; flick_version=1
    flick_rearm_key=0x51
    weapon_profiles_enabled=True
    mode_name="STABLE"
    aim_response="Akıcı takip"
    aim_settle_ms=90; aim_max_speed=720; aim_tuning_version=1
    esp_profile="Dengeli"; esp_palette="Koral / Mavi"; esp_text_scale=110
    esp_render_mode="Otomatik"
    esp_skeleton=False; esp_boxes=False; esp_health=True; esp_labels=True

    @staticmethod
    def set_preset(name, sync_fn=None):
        Config.mode_name=name

        p={"ESPOR":(85,16.0,6,45),"LEGIT":(120,18.0,100,40),
           "FOCUS":(160,8.0,6,55),"RAGE":(400,1.5,6,200)}
        if name in p: Config.fov,Config.smooth,Config.target_bone,Config.speed_cap=p[name]
        Config.save();
        if sync_fn: sync_fn()

    @staticmethod
    def load():
        loaded = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, encoding='utf-8-sig') as f:
                    loaded = json.load(f)
                    [setattr(Config,k,v) for k,v in loaded.items()]
            except: pass


        if not isinstance(loaded,dict): loaded = {}
        if loaded.get('aim_tuning_version',0) < 1:
            Config.aim_response = 'Akıcı takip'
            Config.aim_settle_ms, Config.aim_max_speed = 90,720
            Config.aim_tuning_version = 1
        Config.wall_lock_active = False
        Config.vis_check = True


        if loaded.get('rcs_tuning_version',0) < 1:
            Config.rcs_scale = Config.rcs_yaw_scale = 100
            Config.rcs_tuning_version = 1
        if loaded.get('flick_version',0) < 1:
            if not loaded.get('flick_enabled',False) or Config.flick_key not in FLICK_KEYS.values():
                Config.flick_key = 0x06
            Config.flick_knife_key, Config.flick_fov, Config.flick_bone = 0x33,90,6
            Config.flick_version = 1

    @staticmethod
    def save():
        try:
            from settings_profiles import atomic_json
            d={k:v for k,v in Config.__dict__.items()
               if not k.startswith("__") and not callable(v) and k!="enabled"}
            atomic_json(CONFIG_FILE,d)
            return True
        except (OSError,ValueError,TypeError):
            logging.exception('Settings save failed')
            return False


KEY_MAP={"SHIFT":0x10,"ALT":0x12,"CTRL":0x11,"SOL MOUSE":0x01,"SAĞ MOUSE":0x02,"MOUSE4":0x05,"MOUSE5":0x06}
B_MAP  ={"AKILLI":100,"KAFA":6,"BOYUN":5,"GÖVDE":4}
S_BONES=[(5,4),(4,2),(5,8),(8,9),(9,11),(5,13),(13,14),(14,16),
         (2,22),(22,23),(23,24),(2,25),(25,26),(27,26)]

T_MODES = {
    "TAP (Tekli)": "TAP",
    "BURST (Kısa)": "BURST",
    "FULL SPRAY (AK47)": "SPRAY_FULL",
    "SPRAY (Normal)": "SPRAY",
    "LEGIT (Karışık)": "LEGIT",
    "AWP (Hızlı)": "AWP",
    "SMART PISTOL (Makro)": "PISTOL_MACRO"
}


WEAPON_NAMES = {
    1:  "Desert Eagle",  2: "Dual Berettas", 3: "Five-SeveN",
    4:  "Glock-18",      7: "AK-47",         8: "AUG",
    9:  "AWP",          10: "FAMAS",         11: "G3SG1",
    13: "Galil AR",     14: "M249",          16: "M4A4",
    17: "MAC-10",       19: "P90",           20: "Zone Repulsor",
    23: "MP5-SD",       24: "UMP-45",        25: "XM1014",
    26: "PP-Bizon",     27: "MAG-7",         28: "Negev",
    29: "Sawed-Off",    30: "Tec-9",         31: "Zeus x27",
    32: "P2000",        33: "MP7",           34: "MP9",
    35: "Nova",         36: "P250",          38: "SCAR-20",
    39: "SG 553",       40: "SSG 08",        60: "M4A1-S",
    61: "USP-S",        63: "CZ75-Auto",     64: "R8 Revolver",
    43: "Flashbang",    44: "HE Grenade",    45: "Smoke Grenade",
    46: "Molotov",      47: "Decoy",         48: "Incendiary",
    49: "C4",
}


def _get_field(cls_data, cls_name, field_name):
    """Parse both a2x (int) and sezzyaep ({'offset':N}) field formats."""
    try:
        v = cls_data[cls_name]["fields"][field_name]
        return v["offset"] if isinstance(v, dict) else v
    except: return None


def adaptive_smooth(px_dist, base_smooth):
    """
    Adaptif Smooth: Hedefin piksel mesafesine gore dinamik aim hizi.
    - Cok yakin (< 15px): Ultra hassas, titremez
    - Orta mesafe (15-80px): Normal smooth
    - Uzak (> 80px): Hizli yaklasir, sonra yavaslar
    Bu sayede AWP flick aninda, son milimetre ultra hassas gelir.
    """

    if base_smooth <= 1.0:
        return 1.0

    if px_dist < 15:

        return max(1.0, base_smooth * 1.5)
    elif px_dist < 80:
        return max(1.0, base_smooth)
    else:

        factor = max(0.4, 1.0 - (px_dist - 80) / 600.0)
        return max(1.0, base_smooth * factor)


DUST2_ZONES = {
    "B SITE":    (-2500, -700,  1000, 3000),
    "B TUNI":    (-2500, -700,  -200, 1000),
    "MID":       (-700,   700,  -800,  800),
    "UPPER MID": (-700,   700,   800, 2200),
    "A SITE":    ( 700,  2500,   800, 3000),
    "LONG A":    ( 700,  2500,  -800,  800),
    "CT SPAWN":  ( 700,  2500, -3000, -800),
    "T SPAWN":   (-2500, -700, -3000, -800),
}


class CS2Engine:
    # CEntityIdentity entry size verified against the running build 14190.
    ENTITY_STRIDE = 0x70

    def __init__(self):
        self.pm=None; self.client=None
        self.stop_event = threading.Event()
        self.glow_status = "Model silueti bekliyor"
        self.glow_thread = None
        self.trigger_thread = None
        self.aim_thread = None
        self.flick_status = 'Hazır · tek basış, tek işlem'
        self.stats = RuntimeStats()
        user32 = ctypes.windll.user32
        self.fire_control = FireControl(
            lambda: user32.mouse_event(0x0002,0,0,0,0),
            lambda: user32.mouse_event(0x0004,0,0,0,0),
            lambda key: user32.keybd_event(key,user32.MapVirtualKeyW(key,0),0,0),
            lambda key: user32.keybd_event(key,user32.MapVirtualKeyW(key,0),2,0))
        self.visibility = MapVisibility(_BASE_DIR)
        self.off={}; self.cls={}
        self.sx=ctypes.windll.user32.GetSystemMetrics(0)
        self.sy=ctypes.windll.user32.GetSystemMetrics(1)
        self.old_punch=[0.0,0.0]; self.target_id=-1
        self.mouse_accum_x = 0.0; self.mouse_accum_y = 0.0
        self.p_cache = {}
        self.last_cache_time = 0
        self.sim_times = {}
        self.vis_start = {}

        self.last_vis_time = {}
        self.last_sim_val = {}
        self.ready=False
        self.loading=True
        self.offset_status = "Offsetler kontrol ediliyor..."
        self.offset_info = {}
        self.lp_idx = -1

        self._off_h = 0; self._off_t = 0; self._off_ph = 0
        self._off_id = 0; self._off_sp = 0; self._off_gsn = 0; self._off_ms = 0


        self._rpm = ctypes.windll.kernel32.ReadProcessMemory
        self._phandle = None
        self.is_firing = False
        self._off_wpn = 0


    def fetch(self):
        """Load a complete snapshot matching the installed game's build."""
        self.ready = False
        self.loading = True
        try:
            def log(message):
                logging.info('[Offsets] %s', message)
                print(f'[Offsets] {message}')
            # A build-matched, hash-verified snapshot can start immediately.
            # Network lookup is needed only when that snapshot is unavailable.
            try:
                snapshot = update_offsets(_BASE_DIR, offline=True, log=log)
            except (OSError, ValueError, KeyError, TypeError, OffsetError):
                self.offset_status = 'Yerel dosyalar uygun değil; güncelleme indiriliyor...'
                snapshot = update_offsets(_BASE_DIR, log=log)
            self.off = snapshot["offsets"]["client.dll"]
            self.cls = snapshot["classes"]
            self.offset_info = snapshot["info"]
            self._off_h = self._f("C_BaseEntity", "m_iHealth")
            self._off_t = self._f("C_BaseEntity", "m_iTeamNum")
            self._off_ph = self._f("CCSPlayerController", "m_hPlayerPawn")
            self._off_id = self._f("C_CSPlayerPawn", "m_iIDEntIndex")
            self._off_sp = self._f("C_CSPlayerPawn", "m_entitySpottedState")
            self._off_gsn = self._f("C_BaseEntity", "m_pGameSceneNode")
            self._off_ms = self._f("CSkeletonInstance", "m_modelState")

            self._off_wpn = 0
            self.offset_status = f"Offsetler hazir: {snapshot['source']} / build {self.offset_info['build_number']}"
            self.ready = True
            logging.info(self.offset_status)
            print(f"[Offsets] {self.offset_status}")
            return True
        except Exception as error:
            self.off = {}; self.cls = {}
            self.offset_status = f"Offsetler yuklenemedi: {error}"
            logging.exception('Offset initialization failed')
            print(f"[Offsets] {self.offset_status}")
            return False
        finally:
            self.loading = False


    def attach(self):
        try:
            self.pm=pymem.Pymem(_PROC)
            self.client=pymem.process.module_from_name(
                self.pm.process_handle,_MOD).lpBaseOfDll
            self._phandle = self.pm.process_handle
            print("[V10] Baglandi! client:0x{:X}".format(self.client))
            return True
        except Exception as e:
            print("[V10] Attach hatasi:",e); return False

    def read_bytes(self, addr, size):
        value = (ctypes.c_char * size)()
        count = ctypes.c_size_t()
        ok = self._rpm(ctypes.c_void_p(self._phandle), ctypes.c_void_p(addr),
                       value, size, ctypes.byref(count))
        if not ok or count.value != size:
            raise OSError(f"Bellek okunamadi: {addr:#x} ({size} bayt)")
        return value.raw

    def read_int(self, addr):
        return struct.unpack('<i', self.read_bytes(addr, 4))[0]

    def read_uint(self, addr):
        return struct.unpack('<I', self.read_bytes(addr, 4))[0]

    def read_team(self, entity):

        return self.read_bytes(entity + self._off_t,1)[0]

    def read_float(self, addr):
        return struct.unpack('<f', self.read_bytes(addr, 4))[0]

    def read_longlong(self, addr):
        return struct.unpack('<Q', self.read_bytes(addr, 8))[0]

    def write_bytes(self, addr, data):
        value = ctypes.create_string_buffer(data)
        count = ctypes.c_size_t()
        ok = ctypes.windll.kernel32.WriteProcessMemory(
            ctypes.c_void_p(self._phandle), ctypes.c_void_p(addr), value,
            len(data), ctypes.byref(count))
        if not ok or count.value != len(data):
            raise OSError(f"Bellek yazilamadi: {addr:#x}")

    def write_float(self, addr, val):
        self.write_bytes(addr, struct.pack('<f', val))

    def is_game_foreground(self):
        if not self.pm:
            return False
        pid = ctypes.c_ulong()
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == self.pm.process_id

    def _f(self, cls, field):
        """Resolve schema fields without silently substituting old constants."""
        return field_offset(self.cls, cls, field)

    def entity_from_index(self, entity_list, index):
        """Resolve both entity indexes and serialized handles consistently."""
        if not entity_list or index <= 0 or index == 0xFFFFFFFF:
            return 0
        index &= 0x7FFF
        chunk = self.read_longlong(entity_list + 0x10 + 8 * (index >> 9))
        if not chunk:
            return 0
        return self.read_longlong(chunk + self.ENTITY_STRIDE * (index & 0x1FF))

    def get_bones(self, pawn, bone_ids):
        """Snapshot the requested bone span with one ReadProcessMemory call."""
        try:
            bone_ids = sorted(set(bone_ids))
            if not bone_ids or bone_ids[0] < 0 or bone_ids[-1] > 255:
                return {}
            gsn = self.read_longlong(pawn + self._off_gsn)
            if not gsn: return {}


            ba = 0
            for bone_ptr_off in [0x80, 0x78, 0x88, 0x70]:
                temp = self.read_longlong(gsn + self._off_ms + bone_ptr_off)
                if temp:
                    ba = temp
                    break
            if not ba: return {}


            first, last = bone_ids[0], bone_ids[-1]
            data = self.read_bytes(ba + first * 32, (last-first)*32 + 12)
            res = {}
            for bid in bone_ids:
                bone = struct.unpack_from('<3f', data, (bid-first)*32)
                if bone != (0.0, 0.0, 0.0) and all(abs(v) < 100000 for v in bone):
                    res[bid] = bone
            return res
        except: return {}

    def get_bone(self, pawn, bone_id):
        res = self.get_bones(pawn, [bone_id])
        return res.get(bone_id, None)

    def w2s(self, m, p):
        w = m[12]*p[0]+m[13]*p[1]+m[14]*p[2]+m[15]
        if w < 0.01: return None
        return ((self.sx/2)*(1+(m[0]*p[0]+m[1]*p[1]+m[2]*p[2]+m[3])/w),
                (self.sy/2)-(self.sy/2*(m[4]*p[0]+m[5]*p[1]+m[6]*p[2]+m[7])/w))


def trigger_worker(eng):
    fire = eng.fire_control
    try:
        while not eng.stop_event.is_set():
            try:
                runtime=getattr(eng,'runtime_config',None)
                cfg=runtime.view() if runtime else Config
                if not (cfg.enabled and cfg.trigger_enabled and eng.ready and eng.pm):
                    fire.cancel_trigger()
                    eng.is_firing = False
                    eng.stop_event.wait(.025)
                    continue
                target = current_target(eng, cfg)
                eng.is_firing = fire.update_trigger(time.monotonic(), target, cfg.trigger_enabled,
                                                   cfg.trigger_mode, cfg.trigger_delay)
            except Exception:
                fire.cancel_trigger()
                eng.is_firing = False
            eng.stop_event.wait(.002)
    finally:
        fire.cancel_trigger()
        eng.is_firing = False


def glow_worker(eng):
    while not eng.ready:
        if eng.stop_event.wait(.25):
            return
    controller = None
    try:
        def valid(identity):
            try:
                ctrl, handle, pawn = identity
                entity_list = eng.read_longlong(eng.client + eng.off['dwEntityList'])
                return (eng.read_uint(ctrl + eng._off_ph) == handle
                        and eng.entity_from_index(entity_list, handle) == pawn)
            except OSError:
                return None

        controller = ModelGlow(eng.read_bytes, eng.write_bytes, eng._f, valid)
        monitor = GlowMonitor()
        previous_mode = None
        eng.glow_fallback = False
        last_diagnostic = time.monotonic()
        while not eng.stop_event.is_set():
            foreground = False
            try:
                active = set()
                enabled = Config.enabled and Config.glow_chams and eng.pm
                mode = getattr(Config,'esp_render_mode','Otomatik')
                if mode != previous_mode:
                    monitor.reset()
                    eng.glow_fallback = False
                    previous_mode = mode
                fallback = mode == 'Kararlı siluet' or (mode == 'Otomatik' and monitor.fallback)
                foreground = enabled and eng.is_game_foreground() and not fallback
                if not enabled:
                    controller.restore_except()
                    monitor.reset()
                    eng.glow_fallback = False
                    eng.glow_status = 'Model silueti kapalı'
                elif fallback:
                    controller.restore_except()
                    eng.glow_status = 'Kararlı siluet' + (' · otomatik geçiş' if mode == 'Otomatik' else '')
                elif foreground:
                    entity_list = eng.read_longlong(eng.client + eng.off['dwEntityList'])
                    context = view_context(eng,entity_list) if entity_list else None
                    if context:
                        colors = PALETTES.get(Config.esp_palette, PALETTES['Koral / Mavi'])
                        for pawn, ctrl, _ in tuple(eng.p_cache.values()):
                            try:
                                target_team = eng.read_team(pawn)
                                if context.excludes(pawn) or eng.read_int(pawn + eng._off_h) <= 0:
                                    continue
                                if target_team not in (2,3):
                                    raise OSError('Team state is transitioning')
                                if not team_allowed(Config.team_mode, context.team, target_team):
                                    continue
                                handle = eng.read_uint(ctrl + eng._off_ph)
                                identity = (ctrl, handle, pawn)
                                if controller.apply(identity, colors[0 if target_team != context.team else 1]):
                                    active.add(identity)
                            except OSError:

                                active.update(key for key in controller.saved if key[0]==ctrl and key[2]==pawn)
                                continue
                        controller.restore_except(active,grace=.75)
                        eng.glow_status = f'Model silueti: {len(active)} oyuncu'
                        if mode == 'Otomatik' and monitor.observe(controller.effect_resets,len(active),time.monotonic()):
                            eng.glow_fallback = True
                            logging.info('[Glow] Repeated engine overwrites: switching to independent silhouette')
                        controller.effect_resets = 0
                    else:
                        eng.glow_status = 'Model silueti: oyuncu / izleyici verisi bekleniyor'

                # every field. Explicit disable and shutdown still restore.
                if time.monotonic()-last_diagnostic >= 10:
                    logging.info('[Glow] tracked=%d repairs=%s removals=%d overwritten_bytes=%s fallback=%s',
                                 len(controller.saved),controller.repairs,controller.removals,
                                 controller.last_overwrites,eng.glow_fallback)
                    controller.repairs = dict.fromkeys(controller.repairs,0)
                    controller.removals = 0
                    controller.last_overwrites.clear()
                    last_diagnostic = time.monotonic()
            except Exception as error:
                eng.glow_status = f'Model silueti hatası: {error}'

            eng.stop_event.wait(1/60 if foreground else .1)
    except Exception as error:
        eng.glow_status = f'Model silueti kullanılamıyor: {error}'
    finally:
        if controller:
            try:
                controller.restore_except()
            except OSError:
                pass


def bhop_worker(eng):
    """BunnyHop: PostMessage (Direct Inject) - Profesyonel Metot"""
    while not eng.ready:
        if eng.stop_event.wait(.5): return
    f_off = eng._f("C_BaseEntity", "m_fFlags")

    hwnd = ctypes.windll.user32.FindWindowW(None, "Counter-Strike 2")

    while not eng.stop_event.is_set():
        try:
            active = (Config.enabled and Config.bhop_enabled
                      and ctypes.windll.user32.GetAsyncKeyState(0x20) & 0x8000)
            if active and eng.is_game_foreground():

                if ctypes.windll.user32.GetAsyncKeyState(0x20) & 0x8000:
                    lp = eng.read_longlong(eng.client + eng.off["dwLocalPlayerPawn"])
                    if lp:
                        flags = eng.read_uint(lp + f_off)

                        if flags & 1:

                            ctypes.windll.user32.PostMessageW(hwnd, 0x0100, 0x20, 0)
                            time.sleep(0.015)
                            ctypes.windll.user32.PostMessageW(hwnd, 0x0101, 0x20, 0)
            eng.stop_event.wait(.004 if active else .016)
        except Exception: eng.stop_event.wait(1)


class NebulaUI(ControlPanel):
    def __init__(self, root, eng, **options):
        super().__init__(root, eng, Config, KEY_MAP, B_MAP, T_MODES, **options)


if __name__ == "__main__":
    if '--demo' in sys.argv:
        from demo_mode import main
        main()
        sys.exit(0)
    if '--setup' in sys.argv:
        from setup_runtime import install
        from tkinter import messagebox
        setup_root = tk.Tk()
        setup_root.withdraw()
        try:
            installed_path = install(_BASE_DIR)
            messagebox.showinfo('CS2 Studio setup', f'Map configuration installed:\n{installed_path}\n\nRestart CS2 to load it.')
        except Exception as error:
            messagebox.showerror('CS2 Studio setup', str(error))
            setup_root.destroy()
            sys.exit(1)
        setup_root.destroy()
        sys.exit(0)
    from logging.handlers import RotatingFileHandler
    try:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                            handlers=[RotatingFileHandler(os.path.join(_BASE_DIR,'CS2Tool.log'),
                                      maxBytes=256*1024,backupCount=1,encoding='utf-8')])
    except OSError:
        logging.basicConfig(handlers=[logging.NullHandler()])
    logging.info('Starting Studio: %s', sys.executable)
    if '--startup-check' in sys.argv:
        # Hidden packaged-app diagnostic: no workers, game attach, OS key events

        from pathlib import Path
        from hotkeys import HotkeyEdges
        check_engine = CS2Engine()
        result = {'ready':check_engine.fetch(), 'status':check_engine.offset_status}
        check_root = tk.Tk()
        check_root.withdraw()
        check_panel = ControlPanel(check_root,check_engine,Config,KEY_MAP,B_MAP,T_MODES,live=False)
        result['flick_controls'] = (len(check_panel.tabs.tabs()) == 5
            and check_panel.vars['flick_key'][1][check_panel.vars['flick_key'][0].get()] == Config.flick_key
            and check_panel.vars['flick_knife_key'][1][check_panel.vars['flick_knife_key'][0].get()] == Config.flick_knife_key
            and check_panel.vars['flick_rearm_key'][1][check_panel.vars['flick_rearm_key'][0].get()] == Config.flick_rearm_key)
        original_fov=Config.fov
        check_engine.profiles.save_weapon('weapon:9',{'fov':45})
        check_engine.runtime_config.select(9)
        result['weapon_profiles']=(check_engine.runtime_config.view().fov==45 and Config.fov==original_fov)
        check_engine.profiles.remove_weapon('weapon:9')
        check_engine.runtime_config.clear()
        metrics=check_engine.stats.sample()
        result['performance_sample']=metrics.get('rss') is not None
        check_panel.btn.invoke()
        result['button_enabled'] = Config.enabled
        check_panel.btn.invoke()
        pressed = set()
        check_panel.hotkey_edges = HotkeyEdges(lambda key:0x8000 if key in pressed else 0)
        pressed.add(0x71)
        check_panel.poll_hotkeys()
        result['f2_enabled'] = Config.enabled
        check_panel.poll_hotkeys()
        result['held_key_does_not_repeat'] = Config.enabled
        from gdi_overlay import GdiSink
        from esp_visuals import EspRenderer,sample_pose
        check_sink=GdiSink(320,320,position=(10000,10000))
        try:
            check_renderer=EspRenderer(check_sink)
            check_renderer.begin((320,320))
            check_renderer.player(1,sample_pose(160,45,220),100,None,
                silhouette=True,skeleton=False,boxes=False,health_bar=False,labels=False)
            check_renderer.end()
            result['silhouette_surface']=check_sink.frames==1 and check_sink.visible
        finally:
            check_sink.close()
        check_panel.close()
        Path(_BASE_DIR,'startup-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        sys.exit(0 if all(result[key] for key in ('ready','button_enabled','f2_enabled','held_key_does_not_repeat','silhouette_surface','flick_controls','weapon_profiles','performance_sample')) else 1)
    # Two copies must not race over glow restoration, hotkeys or the local map port.
    ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
    _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\CS2Tool.Studio')
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(None, 'CS2Tool zaten açık. Paneli F3 ile gösterebilirsin.', 'CS2Tool', 0x40)
        sys.exit(0)
    Config.load()
    eng = CS2Engine()
    eng.profiles = ProfileStore(os.path.join(_BASE_DIR,'profiller.json'),Config)
    eng.runtime_config = WeaponRuntime(Config,eng.profiles)
    threading.Thread(target=eng.fetch, daemon=True).start()
    eng.visibility.start()
    eng.aim_thread = threading.Thread(target=aim_loop, args=(eng,Config), daemon=True)
    eng.aim_thread.start()
    eng.trigger_thread = threading.Thread(target=trigger_worker, args=(eng,), daemon=True)
    eng.trigger_thread.start()
    threading.Thread(target=bhop_worker, args=(eng,), daemon=True).start()
    eng.glow_thread = threading.Thread(target=glow_worker, args=(eng,), daemon=True)
    eng.glow_thread.start()
    root = tk.Tk()
    NebulaUI(root, eng)
    root.mainloop()
