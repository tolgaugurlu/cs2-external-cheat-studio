"""Open the real UI with synthetic data, without game access or settings writes."""
import threading
from types import SimpleNamespace
import tkinter as tk

from memory_bot import Config, KEY_MAP, B_MAP, T_MODES
from control_panel import ControlPanel
from settings_profiles import settings_snapshot, ProfileStore, WeaponRuntime
from runtime_stats import RuntimeStats


def main():
    cfg = SimpleNamespace(**settings_snapshot(Config), enabled=False)
    cfg.save = lambda: True
    cfg.glow_chams = True
    cfg.esp_render_mode = 'Kararlı siluet'
    eng = SimpleNamespace(ready=True, offset_status='DEMO · Oyun bağlantısı ve gerçek girdiler kapalı',
        glow_status='Önizleme · örnek karakter çizimi', flick_status='Demo · gerçek atış yapılmaz',
        stop_event=threading.Event(), glow_thread=None, visibility=SimpleNamespace(
            status='Demo · harita bağlantısı yok', close=lambda: None))
    eng.stats = RuntimeStats()
    eng.profiles = ProfileStore(None, cfg)
    eng.profiles.save_weapon('weapon:9', {'fov': 90, 'target_bone': 4})
    eng.profiles.save_settings('Örnek profil', cfg)
    eng.runtime_config = WeaponRuntime(cfg, eng.profiles)
    eng.runtime_config.select(9)
    eng.stats.status('Nişan', 'Demo · oyun girdisi kapalı')
    eng.stats.status('Profil', 'Örnek AWP profili seçildi')
    root = tk.Tk()
    panel = ControlPanel(root, eng, cfg, KEY_MAP, B_MAP, T_MODES, live=False)
    root.title('CS2 Studio — Documentation demo')
    panel.btn.configure(state='disabled', text='DEMO')
    root.mainloop()


if __name__ == '__main__':
    main()
