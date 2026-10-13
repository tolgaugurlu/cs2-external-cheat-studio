"""Installed-map collision rays. Unknown/stale maps never authorize an aim point."""
import hashlib
import hmac
import json
import math
import mmap
import os
from pathlib import Path
import re
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from offset_manager import installed_build

NODE = struct.Struct('<6f4i')
TRI = struct.Struct('<9f')
MAP_NAME = re.compile(r'^(?:de|cs|ar)_[a-z0-9_]+$')


def segment_distance_sq(p,q,a,b):
    """Exact segment/capsule test, including spheres and parallel segments."""
    u=tuple(q[i]-p[i] for i in range(3));v=tuple(b[i]-a[i] for i in range(3))
    w=tuple(p[i]-a[i] for i in range(3))
    dot=lambda x,y:sum(x[i]*y[i] for i in range(3))
    clamp=lambda x:max(0.,min(1.,x))
    aa,ee,cc,ff=dot(u,u),dot(v,v),dot(u,w),dot(v,w)
    if aa<1e-12:
        s,t=0.,clamp(ff/ee) if ee>1e-12 else 0.
    elif ee<1e-12:
        s,t=clamp(-cc/aa),0.
    else:
        bb=dot(u,v);den=aa*ee-bb*bb
        s=clamp((bb*ff-cc*ee)/den) if den>1e-12 else 0.
        t=(bb*s+ff)/ee
        if t<0: t=0.;s=clamp(-cc/aa)
        elif t>1: t=1.;s=clamp((bb-cc)/aa)
    return sum((w[i]+s*u[i]-t*v[i])**2 for i in range(3))


class CollisionMap:
    def __init__(self, path):
        with Path(path).open('rb') as source:
            if os.fstat(source.fileno()).st_size < 16:
                raise ValueError('Incomplete collision header')
            self.data = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            self._validate()
        except Exception:
            self.close()
            raise

    def close(self):
        self.data.close()

    def _validate(self):
        version = self.data[:8]
        if version not in (b'CS2BVH01',b'CS2BVH02'):
            raise ValueError('Invalid collision format')
        nodes, triangles = struct.unpack_from('<II', self.data, 8)
        self.tri_offset = 16 + nodes * NODE.size
        geometry_end = self.tri_offset + triangles * TRI.size
        expected_end = geometry_end
        self.curves = []
        if version == b'CS2BVH02':
            if len(self.data) < geometry_end+4: raise ValueError('Missing primitives')
            count = struct.unpack_from('<I',self.data,geometry_end)[0]
            expected_end += 4+count*28
            if len(self.data) != expected_end: raise ValueError('Incomplete primitives')
            self.curves = [struct.unpack_from('<7f',self.data,geometry_end+4+i*28) for i in range(count)]
            if any(not all(math.isfinite(v) for v in curve) or curve[6]<=0 for curve in self.curves):
                raise ValueError('Invalid primitive')
        self.curve_bounds = [tuple(min(c[i],c[i+3])-c[6] for i in range(3))
                             +tuple(max(c[i],c[i+3])+c[6] for i in range(3)) for c in self.curves]
        if not 0 < nodes < 5_000_000 or len(self.data) != expected_end:
            raise ValueError('Incomplete collision data')
        self.bounds = NODE.unpack_from(self.data,16)
        self.node_count = nodes
        for index in range(nodes):
            node = NODE.unpack_from(self.data,16+index*NODE.size)
            if not all(math.isfinite(x) for x in node[:6]):
                raise ValueError('Invalid collision bounds')
            left, right, start, count = node[6:]
            if count:
                if start < 0 or start + count > triangles:
                    raise ValueError('Invalid collision leaf')
            elif not index < left < nodes or not index < right < nodes:
                raise ValueError('Invalid collision tree')
            if index and index % 4096 == 0:
                time.sleep(.001)
        self.triangle_count = triangles

    def visible(self, origin, point):
        if not all(math.isfinite(v) and abs(v) < 100000 for v in (*origin, *point)):
            return False
        ox, oy, oz = origin
        dx, dy, dz = (point[i] - origin[i] for i in range(3))
        if dx*dx + dy*dy + dz*dz < .01:
            return False

        bounds = self.bounds
        if any(origin[i] < bounds[i]-128 or origin[i] > bounds[i+3]+128 for i in range(3)):
            return False
        ray_min=tuple(min(origin[i],point[i]) for i in range(3))
        ray_max=tuple(max(origin[i],point[i]) for i in range(3))
        for curve,box in zip(self.curves,self.curve_bounds):
            if (box[0]>ray_max[0] or box[3]<ray_min[0] or box[1]>ray_max[1]
                    or box[4]<ray_min[1] or box[2]>ray_max[2] or box[5]<ray_min[2]):
                continue
            if segment_distance_sq(origin,point,curve[:3],curve[3:6]) <= curve[6]**2:
                return False
        direction = (dx, dy, dz)
        inverse = tuple(1/d if abs(d) > 1e-12 else 0 for d in direction)
        stack = [0]
        while stack:
            node = NODE.unpack_from(self.data,16+stack.pop()*NODE.size)
            lo, hi = 0.0, 1.0
            hit = True
            for axis in range(3):
                if not inverse[axis]:
                    if not node[axis] <= origin[axis] <= node[axis+3]:
                        hit = False
                        break
                else:
                    a = (node[axis]-origin[axis])*inverse[axis]
                    b = (node[axis+3]-origin[axis])*inverse[axis]
                    if a > b: a, b = b, a
                    lo, hi = max(lo,a), min(hi,b)
                    if lo > hi:
                        hit = False
                        break
            if not hit:
                continue
            left, right, start, count = node[6:]
            if not count:
                stack.extend((right,left))
                continue
            for i in range(start, start+count):
                ax,ay,az, ex,ey,ez, fx,fy,fz = TRI.unpack_from(self.data,self.tri_offset+i*TRI.size)
                px,py,pz = dy*fz-dz*fy, dz*fx-dx*fz, dx*fy-dy*fx
                det = ex*px+ey*py+ez*pz
                if abs(det) < 1e-9:
                    continue
                tx,ty,tz = ox-ax,oy-ay,oz-az
                u = (tx*px+ty*py+tz*pz)/det
                if u < -1e-7 or u > 1.0000001:
                    continue
                qx,qy,qz = ty*ez-tz*ey,tz*ex-tx*ez,tx*ey-ty*ex
                v = (dx*qx+dy*qy+dz*qz)/det
                if v < -1e-7 or u+v > 1.0000001:
                    continue
                t = (fx*qx+fy*qy+fz*qz)/det
                if 1e-7 < t < .9999999:
                    return False
        return True


def source_signature(path):
    info = path.stat()
    return {'size': info.st_size, 'mtime_ns': info.st_mtime_ns}


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare_map(base, game_dir, name):
    if not MAP_NAME.fullmatch(name):
        raise ValueError('Unsupported map name')
    base, game_dir = Path(base), Path(game_dir)
    source = game_dir / 'maps' / (name + '.vpk')
    signature = source_signature(source)
    cache = base / 'map-cache'
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / (name + '.bvh')
    metadata = cache / (name + '.json')
    if destination.is_file() and metadata.is_file():
        saved = json.loads(metadata.read_text(encoding='utf-8'))
        if (saved.get('source') == signature and saved.get('format') in (1,2)
                and saved.get('sha256') == file_digest(destination)):
            return destination, saved
    helper = base / 'map-tools' / 'MapGeometry.dll'
    dotnet = Path(os.environ.get('ProgramW6432', r'C:\Program Files')) / 'dotnet/dotnet.exe'
    if not dotnet.is_file() or not helper.is_file():
        raise OSError('Harita dönüştürücüsü veya .NET 10 bulunamadı')
    result = subprocess.run([str(dotnet), str(helper), str(source), str(destination)],
                            capture_output=True, text=True, encoding='utf-8', timeout=180,
                            creationflags=(getattr(subprocess,'CREATE_NO_WINDOW',0)
                                           | getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0)))
    if result.returncode:
        raise OSError('Harita çarpışması çıkarılamadı: ' + result.stderr.strip()[-220:])
    saved = dict(json.loads(result.stdout.strip().splitlines()[-1]), source=signature, format=2,
                 sha256=file_digest(destination))
    metadata.write_text(json.dumps(saved,indent=2),encoding='utf-8')
    return destination, saved


class MapVisibility:
    def __init__(self, base):
        self.base = Path(base)
        self.assets = self.base if (self.base/'map-tools').is_dir() else self.base/'dist'
        self.status = 'Harita sinyali bekleniyor'
        self.geometry = None
        self.name = None
        self.requested = None
        self.last_signal = 0
        self.stop = threading.Event()
        self.server = None
        self.signal_lock = threading.Lock()

    def accept_state(self, payload):
        name = payload.get('map',{}).get('name','')
        if not isinstance(name,str) or not MAP_NAME.fullmatch(name):
            name = None
        with self.signal_lock:
            self.requested, self.last_signal = name, time.monotonic()

    def snapshot(self):
        with self.signal_lock:
            if (self.name != self.requested or self.geometry is None
                    or time.monotonic()-self.last_signal > 3):
                return None
            return self.geometry

    def start(self):
        threading.Thread(target=self.run,daemon=True).start()

    def run(self):
        try:
            _, steam_inf = installed_build()
            game_dir = steam_inf.parent
            settings = json.loads((self.base/'gsi_config.json').read_text(encoding='utf-8'))
            owner = self
            class Handler(BaseHTTPRequestHandler):
                def do_POST(self):
                    try:
                        length = int(self.headers.get('Content-Length','0'))
                        if not 0 < length <= 65536: raise ValueError('size')
                        payload = json.loads(self.rfile.read(length))
                        supplied = payload.get('auth',{}).get('token','')
                        if not isinstance(supplied,str) or not hmac.compare_digest(supplied,settings['token']):
                            self.send_error(403); return
                        owner.accept_state(payload)
                        self.send_response(200);self.end_headers()
                    except (ValueError,TypeError,AttributeError):
                        self.send_error(400)
                def log_message(self,*args): pass
            self.server = ThreadingHTTPServer(('127.0.0.1', settings['port']), Handler)
            self.server.daemon_threads = True
            threading.Thread(target=self.server.serve_forever,daemon=True).start()
            attempt, last_attempt, verified_at = None, 0, 0
            while not self.stop.wait(.1):
                now = time.monotonic()
                with self.signal_lock:
                    requested, last_signal = self.requested, self.last_signal
                if now-last_signal > 3 or requested is None:
                    self.status = 'Harita sinyali bekleniyor · CS2 bağlantısı gerekli'
                    if requested is None or now-last_signal > 15:
                        self.geometry = None
                    continue
                if requested == self.name and self.geometry is not None:
                    self.status = f'Duvar testi hazır · {self.name}'
                    if now-verified_at > 5:
                        verified_at = now
                        if source_signature(game_dir/'maps'/(requested+'.vpk')) != self.signature:
                            self.geometry = None
                    continue
                if attempt == requested and now-last_attempt < 15:
                    continue
                attempt, last_attempt = requested, now
                self.geometry = None
                self.status = f'Harita hazırlanıyor · {requested}'
                try:
                    path, info = prepare_map(self.assets,game_dir,requested)
                    geometry = CollisionMap(path)
                    with self.signal_lock:
                        self.geometry, self.name = geometry, requested
                        self.signature = info['source']

                    del geometry
                except Exception as error:
                    self.status = f'Harita kullanılamıyor · {error}'
        except Exception as error:
            self.status = f'Harita bağlantısı kurulamadı · {error}'

    def close(self):
        self.stop.set()
        self.geometry = None
        if self.server:
            self.server.shutdown()
            self.server.server_close()
