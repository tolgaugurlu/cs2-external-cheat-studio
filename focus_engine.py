"""Point-wise map visibility and frame-independent view-angle targeting."""
import ctypes
import math
import logging
import struct
import time

from esp_visuals import BONE_IDS
from targeting import team_allowed, current_target
from smooth_lock import SmoothLock, normalized
from recoil_control import RecoilControl
from flick_shot import FlickShot, FlickAbort, ShotSnapshot


def eye_position(engine, local):
    origin = struct.unpack('<3f', engine.read_bytes(local + engine._f('C_BasePlayerPawn','m_vOldOrigin'),12))
    offset = struct.unpack('<3f', engine.read_bytes(local + engine._f('C_BaseModelEntity','m_vecViewOffset'),12))
    if (all(math.isfinite(v) for v in (*origin,*offset)) and abs(offset[0]) < 32
            and abs(offset[1]) < 32 and 25 < offset[2] < 90):
        return tuple(origin[i]+offset[i] for i in range(3))
    raise ValueError('Kamera yüksekliği doğrulanamadı')


def aim_angles(eye, point, punch=(0,0)):
    dx,dy,dz = (point[i]-eye[i] for i in range(3))
    pitch = -math.degrees(math.atan2(dz,math.hypot(dx,dy))) - punch[0]*2
    yaw = math.degrees(math.atan2(dy,dx)) - punch[1]*2
    return max(-89,min(89,pitch)), (yaw+180)%360-180


def step_angles(current, desired, dt, sharp, smooth, max_degrees):
    if sharp:
        return desired
    alpha = 1-math.exp(-max(.001,min(.05,dt))*120/max(1,smooth))
    delta = (desired[0]-current[0], (desired[1]-current[1]+180)%360-180)
    limit = max(.05,max_degrees)*max(.001,min(.05,dt))*120
    step = [max(-limit,min(limit,d*alpha)) for d in delta]
    return max(-89,min(89,current[0]+step[0])), (current[1]+step[1]+180)%360-180


def aim_samples(bones, preferred, eye):
    """Interior samples: preferred bone first, then exposed limbs/shoulders."""
    order = [preferred] if preferred != 100 else []
    order += [6,5,4,2,8,13,9,14,11,16,22,25,23,26,24,27]
    for bone in dict.fromkeys(order):
        if bone not in bones: continue
        point = bones[bone]
        yield bone, (0.,0.,0.), point
        if bone in (6,4,8,13,22,25):
            vx,vy = point[0]-eye[0], point[1]-eye[1]
            length = math.hypot(vx,vy)
            if length < 1: continue
            radius = 1.6 if bone == 6 else 2.0
            side = (-vy/length*radius, vx/length*radius, 0.)
            for sign in (1,-1):
                offset = tuple(sign*v for v in side)
                yield bone, offset, tuple(point[i]+offset[i] for i in range(3))
            if bone == 6:
                offset = (0.,0.,1.6)
                yield bone, offset, (point[0],point[1],point[2]+1.6)


def visible_sample(bones, preferred, eye, project, geometry, center, fov):
    for bone,offset,point in aim_samples(bones,preferred,eye):
        screen = project(point)
        if screen is None or math.hypot(screen[0]-center[0],screen[1]-center[1]) > fov:
            continue
        if geometry.visible(eye,point):
            return bone,offset,point,math.dist(screen,center)
    return None


class TargetScan:
    """Resume unfinished negative scans; never cache a positive visibility result."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.resume_key = None
        self.resume_sample = 0
        self.lock_key = None
        self.point_token = None
        self.last_visible = 0
        self.promote_token = None
        self.promote_since = 0
        self.preferred = None

    def choose(self, candidates, preferred, eye, project, geometry, center, fov,
               locked=-1, seconds=.002, max_rays=24, clock=time.perf_counter):
        deadline = clock() + seconds
        now = time.monotonic()
        if self.preferred != preferred:
            self.reset()
            self.preferred = preferred
        ordered = []
        for candidate, bones in candidates:
            samples = []
            variants = {}
            for bone, offset, point in aim_samples(bones, preferred, eye):
                token = (bone,variants.get(bone,0))
                variants[bone] = token[1]+1
                screen = project(point)
                if screen is not None and (distance := math.dist(screen,center)) <= fov:
                    samples.append((bone,offset,point,distance,token))
            if samples:

                ordered.append((candidate,samples,samples[0][3]))
        ordered.sort(key=lambda row:row[2])


        for i, (candidate, _, _) in enumerate(ordered):
            if candidate[:4] == self.resume_key:
                ordered = ordered[i:] + ordered[:i]
                break
        identity = self.lock_key if now-self.last_visible <= .12 else None
        if identity is not None and not any(row[0][:4] == identity for row in ordered):
            identity = self.lock_key = None
            self.point_token = None
        ordered.sort(key=lambda row:row[0][:4] != identity if identity else row[0][0] != locked)
        rays = 0
        tested = set()
        def available():
            return rays < max_rays and (not rays or clock() < deadline)
        def cast(key,sample):
            nonlocal rays
            tested.add((key,sample[4]))
            rays += 1
            return geometry.visible(eye,sample[2])
        def select(candidate,sample):
            if self.lock_key != candidate[:4] or self.point_token != sample[4]:
                self.promote_token = None
            self.resume_key, self.resume_sample = None,0
            self.lock_key, self.point_token, self.last_visible = candidate[:4],sample[4],now
            return (*candidate,sample[:4])


        if ordered and ordered[0][0][:4] == identity:
            candidate,samples,_ = ordered[0]
            anchor = next((s for s in samples if s[4] == self.point_token),None)
            if anchor is not None and available() and cast(identity,anchor):
                desired = samples[0]
                if desired[4] != anchor[4] and available() and cast(identity,desired):
                    if self.promote_token != desired[4]:
                        self.promote_token,self.promote_since = desired[4],now
                    elif now-self.promote_since >= .06:
                        return select(candidate,desired)
                else:
                    self.promote_token = None
                return select(candidate,anchor)
            self.promote_token = None
        for candidate, samples, _ in ordered:
            key = candidate[:4]
            start = self.resume_sample % len(samples) if key == self.resume_key else 0
            for position in range(start,len(samples)):
                sample = samples[position]
                if (key,sample[4]) in tested:
                    continue
                if not available():
                    self.resume_key, self.resume_sample = key, position
                    return None
                if cast(key,sample):
                    return select(candidate,sample)
            self.resume_key, self.resume_sample = None, 0
            if key == self.lock_key:
                self.lock_key,self.point_token = None,None
        return None


def refresh_players(eng, local, entity_list):
    cache = {}
    for index in range(1,65):
        try:
            ctrl = eng.entity_from_index(entity_list,index)
            if not ctrl: continue
            handle = eng.read_uint(ctrl+eng._off_ph)
            pawn = eng.entity_from_index(entity_list,handle)
            if pawn and pawn != local:
                cache[index] = (pawn,ctrl,handle & 0x7FFF)
        except OSError:
            # Keep this identity for one roster cycle on an incomplete read.
            if index in eng.p_cache: cache[index] = eng.p_cache[index]
    eng.p_cache = cache


class GameFlickPort:
    """Fresh game reads and guarded actions for the input-independent sequence."""
    GUNS = frozenset((1,2,3,4,7,8,9,10,11,13,14,16,17,19,23,24,25,26,27,
                     28,29,30,32,33,34,35,36,38,39,40,60,61,63))

    def __init__(self, eng, cfg):
        self.eng, self.cfg = eng, cfg
        # Lazy: disabled flick adds no schema, weapon or visibility reads.
        self.fields = {}
        self.scanner = TargetScan()
        self.geometry = None
        self.last_angle = None

    @property
    def fire(self):
        return self.eng.fire_control

    def f(self, cls, name):
        if (cls,name) not in self.fields:
            self.fields[cls,name] = self.eng._f(cls,name)
        return self.fields[cls,name]

    def key_down(self, key):
        return bool(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000)

    def manual_fire_down(self):
        with self.fire.lock:
            return self.key_down(1) and not self.fire.trigger.held

    def status(self, message):
        self.eng.flick_status = message
        if hasattr(self.eng,'stats'):self.eng.stats.status('Flick',message)

    def player(self):
        eng = self.eng
        if (eng.stop_event.is_set() or not self.cfg.enabled or not self.cfg.flick_enabled
                or not eng.ready or not eng.pm or not eng.is_game_foreground()):
            raise FlickAbort('İşlem durduruldu')
        local = eng.read_longlong(eng.client+eng.off['dwLocalPlayerPawn'])
        if not local or eng.read_int(local+eng._off_h) <= 0:
            raise FlickAbort('Canlı oyuncu yok')
        return local

    def validate_player(self, original):
        if self.player() != original.identity[0]:
            raise FlickAbort('Oyuncu değişti')

    def identity(self):
        eng = self.eng
        local = self.player()
        services = eng.read_longlong(local+self.f('C_BasePlayerPawn','m_pWeaponServices'))
        if not services:
            raise FlickAbort('Silah bilgisi yok')
        handle = eng.read_uint(services+self.f('CPlayer_WeaponServices','m_hActiveWeapon'))
        entity_list = eng.read_longlong(eng.client+eng.off['dwEntityList'])
        weapon = eng.entity_from_index(entity_list,handle) if handle not in (0,0xFFFFFFFF) else 0
        if not weapon:
            raise FlickAbort('Aktif silah bulunamadı')
        return (local,handle,weapon), services

    def snapshot(self):
        eng = self.eng
        identity, services = self.identity()
        local, handle, weapon = identity
        gun = self.weapon_item(weapon)
        if gun not in self.GUNS:
            raise FlickAbort('Ateşli silah seç · R8 desteklenmiyor')
        if eng.read_bytes(weapon+self.f('C_CSWeaponBase','m_bBurstMode'),1) != b'\0':
            raise FlickAbort('Silahı burst modundan çıkar')
        clip = eng.read_int(weapon+self.f('C_BasePlayerWeapon','m_iClip1'))
        if not 0 <= clip <= 200:
            raise FlickAbort('Şarjör bilgisi doğrulanamadı')
        controller = eng.read_longlong(eng.client+eng.off['dwLocalPlayerController'])
        if not controller:
            raise FlickAbort('Oyuncu saati doğrulanamadı')
        ticks = eng.read_uint(controller+self.f('CBasePlayerController','m_nTickBase'))
        next_tick = eng.read_int(weapon+self.f('C_BasePlayerWeapon','m_nNextPrimaryAttackTick'))
        ratio = eng.read_float(weapon+self.f('C_BasePlayerWeapon','m_flNextPrimaryAttackTickRatio'))
        next_attack = eng.read_float(services+self.f('CCSPlayer_WeaponServices','m_flNextAttack'))
        if not all(math.isfinite(v) for v in (ratio,next_attack)) or not 0 <= ratio <= 1 or not ticks:
            raise FlickAbort('Silah zamanı doğrulanamadı')
        ready = (clip > 0 and next_tick+ratio <= ticks and next_attack <= ticks/64
                 and eng.read_bytes(weapon+self.f('C_CSWeaponBase','m_bInReload'),1) == b'\0')
        angles = struct.unpack('<2f',eng.read_bytes(eng.client+eng.off['dwViewAngles'],8))
        punch = (0.,0.)
        if eng.read_int(local+self.f('C_CSPlayerPawn','m_iShotsFired')) > 0:
            svc = eng.read_longlong(local+self.f('C_CSPlayerPawn','m_pAimPunchServices'))
            if not svc:
                raise FlickAbort('Geri tepme bilgisi yok')
            punch = struct.unpack('<2f',eng.read_bytes(svc+self.f('CCSPlayer_AimPunchServices','m_predictableBaseAngle'),8))
        if not all(math.isfinite(v) for v in (*angles,*punch)) or max(map(abs,punch)) > 30:
            raise FlickAbort('Geçersiz kamera / geri tepme')
        return ShotSnapshot(identity,angles,clip,ready,punch)

    def reset_scan(self):
        self.scanner.reset()
        self.last_angle = None
        self.geometry = self.eng.visibility.snapshot()
        if self.geometry is None:
            raise FlickAbort('Harita duvar testi hazır değil')

    def clear_scan(self):
        self.geometry = None
        self.last_angle = None
        self.scanner.reset()

    def knife_equipped(self):
        weapon = self.identity()[0][2]
        item = self.weapon_item(weapon)
        return item in (42,59) or 500 <= item < 600

    def weapon_item(self, weapon):
        definition = weapon+self.f('C_EconEntity','m_AttributeManager')
        definition += self.f('C_AttributeContainer','m_Item')+self.f('C_EconItemView','m_iItemDefinitionIndex')
        return struct.unpack('<H',self.eng.read_bytes(definition,2))[0]

    def validate_saved_weapon(self, saved):
        self.validate_player(saved)
        _, handle, weapon = saved.identity
        entity_list = self.eng.read_longlong(self.eng.client+self.eng.off['dwEntityList'])
        if (self.eng.entity_from_index(entity_list,handle) != weapon
                or self.weapon_item(weapon) not in self.GUNS):
            raise FlickAbort('Önceki silah değişti · ilk flick için silahını seç')
        if self.eng.read_int(weapon+self.f('C_BasePlayerWeapon','m_iClip1')) <= 0:
            raise FlickAbort('Şarjör boş · silahı doldur')

    def rearm_snapshot(self, saved):
        self.validate_saved_weapon(saved)
        identity, _ = self.identity()
        if identity == saved.identity:
            return self.snapshot()
        item = self.weapon_item(identity[2])
        if item in (42,59) or 500 <= item < 600:
            return None
        raise FlickAbort('Beklenen silah çekilmedi · silahını seçip tekrar dene')

    def acquire(self, snapshot, original):
        eng = self.eng
        local = snapshot.identity[0]
        geometry = eng.visibility.snapshot()
        if geometry is None or geometry is not self.geometry:
            raise FlickAbort('Harita değişti / hazır değil')
        eye = eye_position(eng,local)
        entity_list = eng.read_longlong(eng.client+eng.off['dwEntityList'])
        team = eng.read_team(local)
        bone = getattr(self.cfg,'flick_bone',6)
        if bone not in (4,6):
            raise FlickAbort('Flick hedef noktası geçersiz')
        candidates = []
        for index,(pawn,ctrl,_) in eng.p_cache.items():
            try:
                handle = eng.read_uint(ctrl+eng._off_ph)
                if (pawn == local or eng.entity_from_index(entity_list,handle) != pawn
                        or eng.read_int(pawn+eng._off_h) <= 0
                        or not team_allowed(self.cfg.team_mode,team,eng.read_team(pawn))):
                    continue
                candidates.append(((index,pawn,ctrl,handle,handle & 0x7FFF),eng.get_bones(pawn,(bone,))))
            except (OSError,ValueError):
                continue
        def project(point):
            pitch,yaw = aim_angles(eye,point)
            return pitch-original[0], (yaw-original[1]+180)%360-180
        fov = float(getattr(self.cfg,'flick_fov',90))
        if not math.isfinite(fov):
            raise FlickAbort('Arama açısı geçersiz')
        fov = max(1,min(180,fov))
        return self.scanner.choose(candidates,bone,eye,project,geometry,(0,0),
                                   float('inf') if fov == 180 else fov)

    def align(self, snapshot, selected):
        eng = self.eng
        index,pawn,ctrl,handle,entity_index,(bone,offset,_,_) = selected
        local = snapshot.identity[0]
        entity_list = eng.read_longlong(eng.client+eng.off['dwEntityList'])
        if (eng.read_uint(ctrl+eng._off_ph) != handle
                or eng.entity_from_index(entity_list,handle) != pawn
                or eng.read_int(pawn+eng._off_h) <= 0
                or not team_allowed(self.cfg.team_mode,eng.read_team(local),eng.read_team(pawn))):
            raise FlickAbort('Hedef artık geçerli değil')
        fresh = eng.get_bone(pawn,bone)
        if fresh is None:
            raise FlickAbort('Hedef noktası okunamadı')
        point = tuple(fresh[i]+offset[i] for i in range(3))
        eye = eye_position(eng,local)
        if (eng.visibility.snapshot() is not self.geometry or self.geometry is None
                or not self.geometry.visible(eye,point)):
            raise FlickAbort('Hedef sipere geçti')
        desired = aim_angles(eye,point,snapshot.punch)


        error = (math.hypot(self.last_angle[0]-snapshot.angles[0],
                           (self.last_angle[1]-snapshot.angles[1]+180)%360-180)
                 if self.last_angle is not None else float('inf'))
        confirmed = error <= .06 and bool(current_target(eng,self.cfg,entity_index,pawn))
        if self.identity()[0] != snapshot.identity or eng.visibility.snapshot() is not self.geometry:
            raise FlickAbort('Atış koşulları değişti')
        eng.write_bytes(eng.client+eng.off['dwViewAngles'],struct.pack('<2f',*desired))
        self.last_angle = desired
        eng.target_id = index
        return confirmed

    def restore(self, original):
        if self.identity()[0] != original.identity:
            raise FlickAbort('Eski bakış geri yüklenemedi: silah / oyuncu değişti')
        self.eng.write_bytes(self.eng.client+self.eng.off['dwViewAngles'],struct.pack('<2f',*original.angles))
        self.eng.target_id = -1


def aim_loop(eng,cfg):
    flick = FlickShot(GameFlickPort(eng,cfg))
    try:
        _aim_loop(eng,cfg,flick)
    finally:
        if hasattr(eng,'fire_control'):
            flick.suspend()


def _aim_loop(eng,cfg,flick):
    base_cfg=cfg
    runtime=getattr(eng,'runtime_config',None)
    stats=getattr(eng,'stats',None)
    def status(message):
        if stats:stats.status('Nişan',message)
    while not eng.ready:
        if eng.stop_event.wait(.1): return
    shots_off = eng._f('C_CSPlayerPawn','m_iShotsFired')
    punch_off = eng._f('C_CSPlayerPawn','m_pAimPunchServices')
    punch_angle_off = eng._f('CCSPlayer_AimPunchServices','m_predictableBaseAngle')
    weapon_services_off = eng._f('C_BasePlayerPawn','m_pWeaponServices')
    active_weapon_off = eng._f('CPlayer_WeaponServices','m_hActiveWeapon')
    last_roster, last_time, last_error = 0, time.monotonic(), 0
    scanner = TargetScan()
    motion = SmoothLock()
    recoil_control = RecoilControl()
    def same_shooter(local, weapon):
        if (not cfg.enabled or not eng.is_game_foreground()
                or eng.read_longlong(eng.client+eng.off['dwLocalPlayerPawn']) != local
                or eng.read_int(local+eng._off_h) <= 0):
            return False
        services = eng.read_longlong(local+weapon_services_off)
        return bool(services) and eng.read_uint(services+active_weapon_off) == weapon
    while not eng.stop_event.is_set():
        frame_started = time.monotonic()
        geometry = None
        acted = False
        recoil_delta = None
        measure=False
        try:
            cfg=base_cfg
            now = time.monotonic()
            dt, last_time = now-last_time, now
            if not cfg.enabled:
                status('Duraklatıldı · F2 ile başlat')
                if runtime:runtime.clear()
                if flick.down is not None: flick.suspend()
                eng.target_id = -1
                scanner.reset(); motion.reset(); recoil_control.reset()
                time.sleep(.025); continue
            if not eng.pm and not eng.attach():
                status('Oyun bağlantısı bekleniyor')
                if runtime:runtime.clear()
                time.sleep(.5); continue
            local = eng.read_longlong(eng.client+eng.off['dwLocalPlayerPawn'])
            if not eng.is_game_foreground():
                status('Oyun arka planda')
                if flick.down is not None: flick.suspend()
                eng.target_id = -1
                eng.old_punch = [0.,0.]
                scanner.reset(); motion.reset(); recoil_control.reset()
                time.sleep(.015); continue
            entity_list = eng.read_longlong(eng.client+eng.off['dwEntityList'])
            if now-last_roster > .1:
                refresh_players(eng,local,entity_list)
                last_roster = now


            if not local or eng.read_int(local+eng._off_h) <= 0:
                status('Canlı oyuncu bekleniyor')
                if runtime:runtime.clear()
                flick.last_weapon = None
                if flick.down is not None: flick.suspend()
                eng.target_id = -1
                eng.old_punch = [0.,0.]
                scanner.reset(); motion.reset(); recoil_control.reset()
                eng.stop_event.wait(.025)
                continue
            measure=True
            weapon_services = eng.read_longlong(local+weapon_services_off)
            weapon = eng.read_uint(weapon_services+active_weapon_off) if weapon_services else 0
            if runtime:
                runtime.observe(eng,local,weapon,entity_list,now)
                cfg=runtime.view()
                flick.port.cfg=cfg
            if flick.tick(now):
                status('Flick işlemi · '+getattr(eng,'flick_status','bekleniyor'))


                scanner.reset(); motion.reset(); recoil_control.reset()
                acted = True
                continue
            local_team = eng.read_team(local)
            aim_key = bool(ctypes.windll.user32.GetAsyncKeyState(cfg.aim_key)&0x8000)
            angle_addr = eng.client+eng.off['dwViewAngles']
            if not weapon or weapon == 0xFFFFFFFF:
                status('Aktif silah bekleniyor')
                recoil_control.reset(); scanner.reset(); motion.reset()
                eng.target_id=-1
                continue
            shots = eng.read_int(local+shots_off) if cfg.rcs_enabled else 0
            punch = (0.,0.)
            svc = eng.read_longlong(local+punch_off) if shots else 0
            if shots and not svc:
                raise OSError('Recoil services temporarily unavailable')
            if svc:
                punch = struct.unpack('<2f',eng.read_bytes(svc+punch_angle_off,8))
            recoil, recoil_delta = recoil_control.sample((local,weapon),shots,punch,now,
                getattr(cfg,'rcs_scale',100),getattr(cfg,'rcs_yaw_scale',100))
            if not aim_key:
                status('Nişan tuşu bekleniyor')
                eng.target_id = -1
                scanner.reset(); motion.reset()
                continue
            geometry = eng.visibility.snapshot()
            if geometry is None:
                status('Harita duvar testi hazır değil')
                eng.target_id = -1
                scanner.reset(); motion.reset()
                time.sleep(.01); continue
            eye = eye_position(eng,local)
            matrix = struct.unpack('<16f',eng.read_bytes(eng.client+eng.off['dwViewMatrix'],64))
            preferred = 4 if cfg.awp_mode else cfg.target_bone
            candidates = []
            roster = sorted(eng.p_cache.items(),key=lambda item:item[0]!=eng.target_id)
            for index,(pawn,ctrl,entity_index) in roster:
                try:
                    handle = eng.read_uint(ctrl+eng._off_ph)
                    if eng.entity_from_index(entity_list,handle)!=pawn or eng.read_int(pawn+eng._off_h)<=0:
                        continue
                    if not team_allowed(cfg.team_mode,local_team,eng.read_team(pawn)):
                        continue
                    bones = eng.get_bones(pawn,BONE_IDS)
                    candidates.append(((index,pawn,ctrl,handle,entity_index),bones))
                except (OSError,ValueError): continue
            selected = scanner.choose(candidates,preferred,eye,lambda p:eng.w2s(matrix,p),geometry,
                                      (eng.sx/2,eng.sy/2),cfg.fov,eng.target_id)
            if selected is None:
                status('FOV içinde görünür hedef bulunamadı')
                eng.target_id=-1
                motion.reset()
                continue
            index,pawn,ctrl,handle,entity_index,(bone,offset,point,_) = selected
            # Fresh identity, position and ray immediately before applying an angle.
            if not cfg.enabled or not eng.is_game_foreground() or eng.visibility.snapshot() is not geometry:
                eng.target_id=-1;continue
            if (eng.read_uint(ctrl+eng._off_ph)!=handle or eng.entity_from_index(entity_list,handle)!=pawn
                    or eng.read_int(pawn+eng._off_h)<=0):
                eng.target_id=-1;continue
            fresh = eng.get_bone(pawn,bone)
            if fresh is None: eng.target_id=-1;continue
            eye = eye_position(eng,local)
            point = tuple(fresh[i]+offset[i] for i in range(3))
            if not geometry.visible(eye,point):
                status('Hedef sipere geçti')
                eng.target_id=-1;continue
            current = struct.unpack('<2f',eng.read_bytes(angle_addr,8))
            if not all(math.isfinite(v) for v in current):
                raise ValueError('Invalid camera angles')


            visual_current = normalized(tuple(current[i]-recoil_delta[i]+recoil[i] for i in range(2)))
            desired = aim_angles(eye,point)
            if cfg.aim_response == 'Akıcı takip' and not cfg.awp_mode:


                identity = (pawn,ctrl,handle,scanner.point_token)
                tracked = motion.step(identity,visual_current,desired,dt,
                                      cfg.aim_settle_ms,cfg.aim_max_speed)
            else:
                motion.reset()
                tracked = step_angles(visual_current,desired,dt,cfg.aim_response=='Keskin kilit' or cfg.awp_mode,
                                     cfg.smooth,cfg.speed_cap*90/max(1,eng.sx))
            result = normalized(tuple(tracked[i]-recoil[i] for i in range(2)))
            if not same_shooter(local,weapon):
                recoil_delta=None; recoil_control.reset()
                eng.target_id=-1
                continue
            eng.write_bytes(angle_addr,struct.pack('<2f',*result))
            acted = True
            eng.target_id=index
            status('Görünür hedef takip ediliyor')
        except Exception as error:
            status('Okuma / işlem hatası · yeniden deneniyor')
            if runtime:runtime.clear()
            if flick.down is not None: flick.suspend()
            eng.target_id=-1
            motion.reset()
            recoil_control.reset(); recoil_delta=None
            if time.monotonic()-last_error>5:
                logging.warning('[Focus] %s: %s',type(error).__name__,error)
                last_error=time.monotonic()
        finally:
            # Exactly one camera writer per frame. A held aim key / hidden target
            # does not disable standalone recoil control. This never selects or

            if not acted and recoil_delta is not None and any(recoil_delta):
                try:
                    if cfg.rcs_enabled and same_shooter(local,weapon):
                        current = struct.unpack('<2f',eng.read_bytes(angle_addr,8))
                        if not all(math.isfinite(v) for v in current):
                            raise ValueError('Invalid camera angles')
                        result = normalized(tuple(current[i]-recoil_delta[i] for i in range(2)))
                        eng.write_bytes(angle_addr,struct.pack('<2f',*result))
                    else:
                        recoil_control.reset()
                except (OSError,ValueError):
                    recoil_control.reset()


            geometry = None
            if not acted:
                motion.reset()
            if stats and measure:stats.timing('Nişan',time.monotonic()-frame_started)
            eng.stop_event.wait(max(.001,1/120-(time.monotonic()-frame_started)))
