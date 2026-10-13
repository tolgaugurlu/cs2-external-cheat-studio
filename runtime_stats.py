"""Bounded local diagnostics. CPU/memory describe this app, never game FPS."""
from collections import deque
import ctypes
from ctypes import wintypes
import math
import os
import threading
import time


class RuntimeStats:
    def __init__(self):
        self.lock=threading.Lock();self.states={};self.events=deque(maxlen=30)
        self.timings={};self.last_sample=None;self.last_cpu=None;self.metrics={}

    def status(self,area,message):
        with self.lock:
            if self.states.get(area)!=message:
                self.states[area]=message
                self.events.append((time.strftime('%H:%M:%S'),area,message))

    def timing(self,area,elapsed,now=None):
        if not math.isfinite(elapsed) or elapsed<0:return
        with self.lock:
            self.timings.setdefault(area,deque(maxlen=240)).append((time.monotonic() if now is None else now,elapsed*1000))

    def sample(self,now=None,cpu=None,memory=None,cores=None):
        now=time.monotonic() if now is None else now
        if self.last_sample is not None and now-self.last_sample<.95:return self.metrics
        cpu=time.process_time() if cpu is None else cpu
        cores=max(1,(os.cpu_count() or 1) if cores is None else cores)
        percent=(100*max(0,cpu-self.last_cpu)/(now-self.last_sample)/cores if self.last_sample is not None else None)
        if memory is None:
            try:memory=process_memory()
            except OSError:memory=(None,None)
        self.last_cpu,self.last_sample=cpu,now
        with self.lock:
            stages={}
            for key,rows in self.timings.items():
                values=sorted(value for stamp,value in rows if now-stamp<=3)
                stages[key]={'mean':sum(values)/len(values),'p95':values[max(0,math.ceil(len(values)*.95)-1)]} if values else None
            self.metrics={'cpu':percent,'rss':memory[0],'private':memory[1],'stages':stages}
        return self.metrics

    def snapshot(self):
        with self.lock:return dict(self.states),list(self.events)


class MemoryCounters(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
        (name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]


def process_memory():
    counters=MemoryCounters();counters.cb=ctypes.sizeof(counters)
    fn=ctypes.windll.psapi.GetProcessMemoryInfo
    fn.argtypes=(wintypes.HANDLE,ctypes.POINTER(MemoryCounters),wintypes.DWORD)
    fn.restype=wintypes.BOOL
    if not fn(wintypes.HANDLE(-1),ctypes.byref(counters),counters.cb):raise ctypes.WinError()
    return counters.WorkingSetSize/1048576,counters.PrivateUsage/1048576
