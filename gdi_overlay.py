"""Reusable Win32 drawing surface for the independent pose silhouette.

Only owns a click-through window and its bitmap; no game handles or input.
Draws directly into a fixed DIB; no per-frame pixel copies or Tk item churn.
"""
import ctypes as C
from ctypes import wintypes as W
import os
import time
import math
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
import pygame


class Header(C.Structure):
    _fields_ = [('size',W.DWORD),('width',W.LONG),('height',W.LONG),
                ('planes',W.WORD),('bits',W.WORD),('compression',W.DWORD),
                ('image_size',W.DWORD),('xppm',W.LONG),('yppm',W.LONG),
                ('colors',W.DWORD),('important',W.DWORD)]


class BitmapInfo(C.Structure):
    _fields_ = [('header',Header),('colors',W.DWORD*1)]


WNDPROC=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,C.c_size_t,C.c_ssize_t)


class WindowClass(C.Structure):
    _fields_ = [('style',W.UINT),('proc',WNDPROC),('extra',C.c_int),('window_extra',C.c_int),
                ('instance',W.HINSTANCE),('icon',W.HICON),('cursor',W.HANDLE),
                ('background',W.HBRUSH),('menu',W.LPCWSTR),('name',W.LPCWSTR)]


u=C.WinDLL('user32',use_last_error=True)
g=C.WinDLL('gdi32',use_last_error=True)
k=C.WinDLL('kernel32',use_last_error=True)


def bind(dll,name,returns,*args):
    function=getattr(dll,name)
    function.restype=returns
    function.argtypes=args
    return function


bind(k,'GetModuleHandleW',W.HMODULE,W.LPCWSTR)
bind(u,'DefWindowProcW',C.c_ssize_t,W.HWND,W.UINT,C.c_size_t,C.c_ssize_t)
bind(u,'RegisterClassW',W.ATOM,C.POINTER(WindowClass))
bind(u,'CreateWindowExW',W.HWND,W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,
     C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p)
bind(u,'DestroyWindow',W.BOOL,W.HWND)
bind(u,'ShowWindow',W.BOOL,W.HWND,C.c_int)
bind(u,'UpdateLayeredWindow',W.BOOL,W.HWND,W.HDC,C.POINTER(W.POINT),C.POINTER(W.SIZE),
     W.HDC,C.POINTER(W.POINT),W.DWORD,C.c_void_p,W.DWORD)
bind(g,'CreateCompatibleDC',W.HDC,W.HDC)
bind(g,'DeleteDC',W.BOOL,W.HDC)
bind(g,'CreateDIBSection',W.HBITMAP,W.HDC,C.POINTER(BitmapInfo),W.UINT,
     C.POINTER(C.c_void_p),W.HANDLE,W.DWORD)
bind(g,'SelectObject',W.HANDLE,W.HDC,W.HANDLE)
bind(g,'DeleteObject',W.BOOL,W.HANDLE)
bind(g,'GdiFlush',W.BOOL)


@WNDPROC
def window_proc(hwnd,message,wparam,lparam):
    if message==0x84: return -1
    if message==0x21: return 3
    return u.DefWindowProcW(hwnd,message,wparam,lparam)


_registered=False
_class_name=f'CS2Tool.Silhouette.{os.getpid()}'
_CIRCLE=tuple((math.cos(i*math.tau/20),math.sin(i*math.tau/20)) for i in range(20))


class GdiSink:
    def __init__(self,width,height,position=(0,0)):
        global _registered
        self.width,self.height=int(width),int(height)
        self.position=position
        self.destination=W.POINT(*position);self.source=W.POINT(0,0)
        self.size=W.SIZE(self.width,self.height)
        self.hwnd=self.dc=self.bitmap=self.old_bitmap=None
        self.visible=False;self.closed=False
        self.items=[];self.surface=None;self.pixel_buffer=None
        self.frames=0;self.draw_seconds=0.;self.upload_seconds=0.
        self.pixels=C.c_void_p()
        instance=k.GetModuleHandleW(None)
        if not _registered:
            cls=WindowClass(proc=window_proc,instance=instance,name=_class_name)
            if not u.RegisterClassW(C.byref(cls)):
                raise C.WinError(C.get_last_error())
            _registered=True
        try:
            self.hwnd=u.CreateWindowExW(0x80000|0x20|0x08000000|0x80|0x8,
                _class_name,'CS2Tool silhouette',0x80000000,*position,self.width,self.height,
                None,None,instance,None)
            self.dc=g.CreateCompatibleDC(None)
            info=BitmapInfo(header=Header(size=C.sizeof(Header),width=self.width,height=-self.height,
                                         planes=1,bits=32,image_size=self.width*self.height*4))
            self.bitmap=g.CreateDIBSection(self.dc,C.byref(info),0,C.byref(self.pixels),None,0)
            if not all((self.hwnd,self.dc,self.bitmap,self.pixels.value)):
                raise C.WinError(C.get_last_error())
            self.old_bitmap=g.SelectObject(self.dc,self.bitmap)
            self.pixel_buffer=(C.c_ubyte*(self.width*self.height*4)).from_address(self.pixels.value)
            self.surface=pygame.image.frombuffer(self.pixel_buffer,(self.width,self.height),'BGRA')
        except Exception:
            self.close()
            raise

    def begin(self):
        self.items=[]

    def draw_silhouette(self,key,coords,height,color):
        limit=max(self.width,self.height)*4
        if not coords or not all(math.isfinite(v) and abs(v)<limit for p in coords.values() for v in p):return
        border=max(1.,min(3.,height*.008))
        outer,inner=[],[]
        for a,b in ((6,5),(5,8),(8,9),(9,11),(5,13),(13,14),(14,16),
                    (2,22),(22,23),(23,24),(2,25),(25,26),(26,27)):
            if a not in coords or b not in coords:continue
            ax,ay=coords[a];bx,by=coords[b]
            length=math.hypot(bx-ax,by-ay)
            if length<.01:continue
            ux,uy=(bx-ax)/length,(by-ay)/length
            vx,vy=-uy,ux
            radius=max(1,min(35,height*(.073 if a in (22,25) else .055)/2))
            outside,inside=[],[]
            for x,y,sign in ((bx,by,1),(ax,ay,-1)):
                for along,side in ((0,1),(.707,.707),(1,0),(.707,-.707),(0,-1)):
                    dx,dy=sign*(ux*along+vx*side),sign*(uy*along+vy*side)
                    outside.append((x+dx*(radius+border),y+dy*(radius+border)))
                    inside.append((x+dx*radius,y+dy*radius))
            outer.append(outside);inner.append(inside)
        if all(b in coords for b in (5,13,25,22,8)):
            torso=[coords[b] for b in (5,13,25,22,8)]
            cx=sum(x for x,y in torso)/5;cy=sum(y for x,y in torso)/5
            inner.append(torso)
            outer.append([(x+border*(1 if x>cx else -1),y+border*(1 if y>cy else -1)) for x,y in torso])
        hx,hy=coords[6];radius=max(2,min(32,height*.047))
        outer.append([(hx+x*(radius+border),hy+y*(radius+border)) for x,y in _CIRCLE])
        inner.append([(hx+x*radius,hy+y*radius) for x,y in _CIRCLE])

        self.items.append(((outer,inner),color,border,
                           (min(p[0] for p in coords.values())-40,min(p[1] for p in coords.values())-40,
                            max(p[0] for p in coords.values())+40,max(p[1] for p in coords.values())+40)))

    def end(self):
        if self.closed:return
        if not self.items:
            self.hide()
            return
        started=time.perf_counter()


        left,top,right,bottom=self.width,self.height,0,0
        for _,_,_,bounds in self.items:
            left=min(left,bounds[0]);top=min(top,bounds[1])
            right=max(right,bounds[2]);bottom=max(bottom,bounds[3])
        left,top=max(0,int(left)),max(0,int(top))
        right,bottom=min(self.width,int(right)+1),min(self.height,int(bottom)+1)
        if right<=left or bottom<=top:
            self.hide();return
        self.source=W.POINT(left,top)
        self.destination=W.POINT(self.position[0]+left,self.position[1]+top)
        self.size=W.SIZE(right-left,bottom-top)
        self.surface.lock()
        try:
            self.surface.fill((0,0,0,0))
            for (outer,inner),color,_,_ in self.items:
                rgb=tuple(bytes.fromhex(color.lstrip('#')))+(255,)
                for polygons,fill in ((outer,rgb),(inner,(36,50,71,255))):
                    for polygon in polygons:pygame.draw.polygon(self.surface,fill,polygon)
        finally:
            self.surface.unlock()
        self.draw_seconds+=time.perf_counter()-started
        started=time.perf_counter()
        if not u.UpdateLayeredWindow(self.hwnd,None,C.byref(self.destination),C.byref(self.size),
                                     self.dc,C.byref(self.source),0,None,1):
            raise C.WinError(C.get_last_error())
        self.upload_seconds+=time.perf_counter()-started
        self.frames+=1
        if not self.visible:
            u.ShowWindow(self.hwnd,4)
            self.visible=True

    def hide(self):
        if self.visible and self.hwnd:u.ShowWindow(self.hwnd,0)
        self.visible=False

    def close(self):
        if self.closed:return
        self.closed=True
        self.hide()
        if self.dc and self.old_bitmap:g.SelectObject(self.dc,self.old_bitmap)
        self.surface=None
        self.pixel_buffer=None
        if self.bitmap:g.DeleteObject(self.bitmap)
        if self.dc:g.DeleteDC(self.dc)
        if self.hwnd:u.DestroyWindow(self.hwnd)
        self.hwnd=self.dc=self.bitmap=None
