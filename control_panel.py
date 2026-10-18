"""Desktop controls and static contour preview; no input automation in this module."""
import ctypes
import logging
import time
import tkinter as tk
from tkinter import ttk

from visual_style import PALETTES, sample_pose
from app_version import APP_NAME, APP_VERSION
from hotkeys import HotkeyEdges
from flick_shot import FLICK_KEYS, KNIFE_KEYS, REARM_KEYS
from settings_profiles import ProfileStore, WeaponRuntime
from runtime_stats import RuntimeStats
from studio_panels import StudioPanels

BG = '#0C111B'
CARD = '#151E2D'
EDGE = '#29374B'
FG = '#EDF2F8'
MUTED = '#9CAEC5'
ACCENT = '#FF9C88'
BLUE = '#88CFFF'


class ControlPanel(StudioPanels):
    def __init__(self, root, engine, config, key_map, bone_map, trigger_modes,
                 live=True):
        self.root, self.eng, self.cfg = root, engine, config
        self.key_map, self.bone_map, self.trigger_modes = key_map, bone_map, trigger_modes
        self.live, self.closing, self.initializing = live, False, True
        self.vars, self.scales, self.scale_labels = {}, {}, {}
        self.save_token=None
        self.scale_suffixes={}
        if not hasattr(config,'weapon_profiles_enabled'):config.weapon_profiles_enabled=True
        if not hasattr(engine,'stats'):engine.stats=RuntimeStats()
        if not hasattr(engine,'profiles'):engine.profiles=ProfileStore(None,config,persist=False)
        if not hasattr(engine,'runtime_config'):engine.runtime_config=WeaponRuntime(config,engine.profiles)
        root.title(f'{APP_NAME} {APP_VERSION}')
        from ctypes import wintypes
        area=wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(48,0,ctypes.byref(area),0)
        width=min(980,max(820,area.right-area.left-32))
        height=min(650,max(560,area.bottom-area.top-64))
        root.geometry(f'{width}x{height}+{max(0,area.left+(area.right-area.left-width)//2)}+{max(0,area.top+(area.bottom-area.top-height-32)//2)}')
        root.minsize(width,height)
        root.configure(bg=BG)
        root.option_add('*Font',('Segoe UI',-13))
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=CARD, foreground=MUTED,
                        padding=(16, 7), font=('Segoe UI', -14, 'bold'))
        style.map('TNotebook.Tab', background=[('selected', EDGE)], foreground=[('selected', FG)])
        style.configure('TCombobox', fieldbackground=EDGE, background=EDGE,
                        foreground=FG, arrowcolor=FG, padding=4,font=('Segoe UI',-13))
        style.configure('TEntry',fieldbackground=EDGE,foreground=FG,padding=4,font=('Segoe UI',-13))
        root.option_add('*TCombobox*Listbox.font',('Segoe UI',-13))
        style.map('TCombobox', fieldbackground=[('readonly', EDGE)],
                  foreground=[('readonly', FG)], selectbackground=[('readonly', EDGE)])
        style.configure('Horizontal.TScale', background=CARD, troughcolor=EDGE)
        root.option_add('*TCombobox*Listbox.background', CARD)
        root.option_add('*TCombobox*Listbox.foreground', FG)
        root.option_add('*TCombobox*Listbox.selectBackground', EDGE)

        header = tk.Frame(root, bg=BG)
        header.pack(fill='x', padx=18, pady=(12, 8))
        self.text(header, APP_NAME, 20, FG, True).pack(side='left')
        self.text(header, f'v{APP_VERSION} · WINDOWS', 10, MUTED).pack(side='left', padx=14)
        self.state_label = self.text(header, 'DURAKLATILDI', 10, BLUE, True)
        self.state_label.pack(side='right')

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill='both', expand=True, padx=18)
        appearance = tk.Frame(self.tabs, bg=BG)
        controls = tk.Frame(self.tabs, bg=BG)
        flick = tk.Frame(self.tabs, bg=BG)
        profiles=tk.Frame(self.tabs,bg=BG)
        dashboard=tk.Frame(self.tabs,bg=BG)
        self.tabs.add(appearance, text='Görünüm')
        self.tabs.add(controls, text='Kontroller')
        self.tabs.add(flick, text='Flick shot')
        self.tabs.add(profiles,text='Profiller')
        self.tabs.add(dashboard,text='Durum / Performans')
        self.appearance(appearance)
        self.controls(controls)
        self.flick_controls(flick)
        self.profiles_page(profiles)
        self.dashboard(dashboard)

        footer = tk.Frame(root, bg=BG)
        footer.pack(side='bottom', before=self.tabs, fill='x', padx=18, pady=10)
        left = tk.Frame(footer, bg=BG)
        left.pack(side='left', fill='x', expand=True)
        self.offset_label = self.text(left, engine.offset_status, 9, MUTED)
        self.offset_label.pack(anchor='w')
        self.guard_label = self.text(left, 'Harita duvar testi hazırlanıyor', 9, BLUE)
        self.guard_label.pack(anchor='w', pady=(5, 0))
        self.offset_label.configure(wraplength=700,justify='left')
        self.guard_label.configure(wraplength=700,justify='left')
        self.btn = tk.Button(footer, command=self.toggle, text='BAŞLAT  ·  F2', bg=ACCENT,
                             fg=BG, activebackground='#FFB6A7', font=('Segoe UI', -14, 'bold'),
                             bd=0, padx=20, pady=10, cursor='hand2')
        self.btn.pack(side='right')
        self.initializing = False
        self.draw_preview()
        self.update_status()
        self.update_dashboard()
        if live:
            self.hotkey_edges = HotkeyEdges(ctypes.windll.user32.GetAsyncKeyState)
            self.poll_hotkeys()

    @staticmethod
    def text(parent, text, size=10, color=FG, bold=False):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI', -round(size*1.35), 'bold' if bold else 'normal'), anchor='w')

    def card(self, parent, title, subtitle=None):
        box = tk.Frame(parent, bg=CARD, padx=12, pady=10, highlightbackground=EDGE, highlightthickness=1)
        self.text(box, title, 11, FG, True).pack(anchor='w', pady=(0, 7))
        if subtitle:
            self.text(box, subtitle, 9, MUTED).pack(anchor='w', pady=(0, 9))
        return box

    def check(self, parent, title, key):
        var = tk.BooleanVar(value=bool(getattr(self.cfg, key)))
        self.vars[key] = var
        tk.Checkbutton(parent, text=title, variable=var, command=self.save_controls,
                       bg=CARD, fg=FG, activebackground=CARD, activeforeground=FG,
                       selectcolor=EDGE, font=('Segoe UI', -13), bd=0,
                       cursor='hand2', anchor='w').pack(fill='x', pady=2)

    def combo(self, parent, title, key, values, mapping=None):
        self.text(parent, title, 9, MUTED).pack(anchor='w', pady=(6, 3))
        current = getattr(self.cfg, key)
        display = next((k for k, v in mapping.items() if v == current), values[0]) if mapping else current
        if display not in values:
            display = values[0]
        var = tk.StringVar(value=display)
        self.vars[key] = (var, mapping) if mapping else var
        widget = ttk.Combobox(parent, textvariable=var, values=values, state='readonly', font=('Segoe UI', -13),width=12)
        widget.pack(fill='x')
        widget.bind('<<ComboboxSelected>>', self.save_controls)

    def slider(self, parent, title, key, low, high, suffix=''):
        self.scale_suffixes[key]=suffix
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill='x', pady=(7, 0))
        self.text(row, title, 9, MUTED).pack(side='left')
        value_label = self.text(row, f'{getattr(self.cfg, key):g}{suffix}', 9, BLUE, True)
        value_label.pack(side='right')
        self.scale_labels[key] = value_label
        scale = ttk.Scale(parent, from_=low, to=high,
                          command=lambda v: self.slider_changed(key, v, suffix))
        scale.set(getattr(self.cfg, key))
        scale.pack(fill='x', pady=(3, 0))
        self.scales[key] = scale

    def appearance(self, page):
        page.columnconfigure(0, weight=1, uniform='appearance')
        page.columnconfigure(1, weight=2, uniform='appearance')
        page.rowconfigure(0, weight=1)
        model = self.card(page, 'Oyun konturu')
        model.grid(row=0, column=0, sticky='nsew', pady=8, padx=(0, 12))
        self.check(model, 'Oyun konturu / Glow', 'glow_chams')
        self.combo(model, 'Renk paleti', 'esp_palette', list(PALETTES))
        note = self.text(model, 'Karakterin oyun içindeki konturunu kullanır. Ayrı ESP penceresi, siluet, iskelet, kutu ve etiket çizimi kaldırıldı.', 10, MUTED)
        note.configure(wraplength=265, justify='left')
        note.pack(anchor='w', pady=18)
        self.glow_label = self.text(model, '', 10, BLUE)
        self.glow_label.configure(wraplength=265, justify='left')
        self.glow_label.pack(anchor='w', pady=8)
        note = self.text(model, 'Oyun kontur değerlerini yeniden yazarsa yanıp sönme yine oluşabilir.', 9, MUTED)
        note.configure(wraplength=265, justify='left')
        note.pack(anchor='w', pady=12)
        preview = self.card(page, 'Renk önizlemesi', 'Şematik örnek · oyun görüntüsü değildir')
        preview.grid(row=0, column=1, sticky='nsew', pady=8)
        self.preview = tk.Canvas(preview, bg='#101825', highlightthickness=0, width=220, height=160)
        self.preview.pack(fill='both', expand=True)
        self.preview.bind('<Configure>', lambda event: self.draw_preview())
        self.text(preview, 'RAKİP: vurgu rengi · TAKIM: mavi', 9, MUTED).pack(anchor='w', pady=(8, 0))
        self.text(preview, 'F2 Başlat / durdur   F3 Gizle   F4 Tetik', 9, MUTED).pack(anchor='w', pady=(4, 0))

    def controls(self, page):
        cols = [tk.Frame(page, bg=BG) for _ in range(3)]
        for i, col in enumerate(cols):
            col.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 12, 0), pady=8)
            page.columnconfigure(i, weight=1, uniform='controls')
        page.rowconfigure(0, weight=1)
        aim = self.card(cols[0], 'Nişan ayarları')
        aim.pack(fill='x')
        self.combo(aim, 'Tepki biçimi', 'aim_response', ['Akıcı takip', 'Keskin kilit', 'Ayarlanabilir'])
        self.slider(aim, 'FOV', 'fov', 10, 600, ' px')
        tuning = tk.Frame(aim,bg=CARD)
        tuning.pack(fill='x')
        self.aim_tuning_frames = {name:tk.Frame(tuning,bg=CARD) for name in ('Akıcı takip','Ayarlanabilir')}
        self.slider(self.aim_tuning_frames['Akıcı takip'],'Yerleşme süresi','aim_settle_ms',40,200,' ms')
        self.slider(self.aim_tuning_frames['Akıcı takip'],'Dönüş hızı sınırı','aim_max_speed',120,1440,' °/sn')
        self.slider(self.aim_tuning_frames['Ayarlanabilir'], 'Yumuşatma', 'smooth', 1, 50)
        self.slider(self.aim_tuning_frames['Ayarlanabilir'], 'Hız sınırı', 'speed_cap', 5, 250)
        self.aim_mode_note = self.text(aim, '', 9, BLUE)
        self.aim_mode_note.configure(wraplength=260, justify='left')
        self.aim_mode_note.pack(anchor='w', pady=(6, 0))
        self.sync_aim_tuning()
        self.combo(aim, 'Nişan tuşu', 'aim_key', list(self.key_map), self.key_map)
        self.combo(aim, 'Hedef noktası', 'target_bone', list(self.bone_map), self.bone_map)
        teams = {'Sadece rakipler': 1, 'Herkes / FFA': 0, 'Sadece takım': 2}
        self.combo(aim, 'Takım filtresi', 'team_mode', list(teams), teams)
        helpers = self.card(cols[1], 'Yardımcılar')
        helpers.pack(fill='x')
        self.check(helpers, 'Geri tepme düzeltmesi', 'rcs_enabled')
        self.check(helpers, 'BunnyHop', 'bhop_enabled')
        self.check(helpers, 'AWP: gövde noktası', 'awp_mode')
        trigger = self.card(cols[1], 'Tetik')
        trigger.pack(fill='x', pady=(12, 0))
        self.check(trigger, 'Otomatik tetik / F4', 'trigger_enabled')
        self.combo(trigger, 'Atış biçimi', 'trigger_mode', list(self.trigger_modes), self.trigger_modes)
        self.slider(trigger, 'Gecikme', 'trigger_delay', 0, 200, ' ms')
        guard = self.card(cols[2], 'Hedef doğrulaması')
        guard.pack(fill='x')
        self.text(guard,'Görünür nokta doğrulanır.\nTam siperde kilit bırakılır.\nHarita otomatik algılanır.',10,FG).pack(anchor='w',pady=5)
        self.text(guard,'Test sabit harita çarpışmasına dayanır.\nHareketli kapılar ve duman dahil değildir.',9,'#E5BF80').pack(anchor='w',pady=8)
        self.text(guard,'Silah profilleri: Profiller sekmesinde.\nKayıt yoksa genel ayarların kullanılır.',9,BLUE).pack(anchor='w',pady=8)
        recoil = self.card(cols[2], 'Geri tepme gücü')
        recoil.pack(fill='x', pady=(12, 0))
        self.slider(recoil, 'Dikey düzeltme', 'rcs_scale', 0, 150, '%')
        self.slider(recoil, 'Yatay düzeltme', 'rcs_yaw_scale', 0, 150, '%')
        self.text(recoil, '100%: tam düzeltme · ilk atıştan\nitibaren. Silah değişince sıfırlanır.', 9, MUTED).pack(anchor='w', pady=(8,0))

    def flick_controls(self, page):
        left = self.card(page, 'Tek basışlık Flick shot')
        left.pack(side='left', fill='y', padx=(0,14), pady=8)
        self.check(left, 'Flick shot etkin', 'flick_enabled')
        self.combo(left, 'Flick tuşu', 'flick_key', list(FLICK_KEYS), FLICK_KEYS)
        self.combo(left, 'Oyundaki bıçak tuşun', 'flick_knife_key', list(KNIFE_KEYS), KNIFE_KEYS)
        self.combo(left, 'Oyundaki önceki silah tuşun', 'flick_rearm_key', list(REARM_KEYS), REARM_KEYS)
        bones = {'Kafa':6, 'Gövde':4}
        self.combo(left, 'Atış noktası', 'flick_bone', list(bones), bones)
        self.slider(left, 'Arama açısı ±', 'flick_fov', 1, 180, '°')
        self.text(left, '90°: ön taraf · 180°: her yön\nNormal aim FOV ayarından bağımsız.',9,MUTED).pack(anchor='w',pady=(8,0))
        self.text(left, 'MOUSE4 / MOUSE5: yan tuşlar.\nÜst / alt sırası fareye göre değişir.',9,MUTED).pack(anchor='w',pady=(18,0))
        right = self.card(page, 'Dön · tek atış · geri dön · bıçak')
        right.pack(side='left', fill='both', expand=True, pady=8)
        for line in ('1   F2 ile sistemi başlat, oyuna dön.',
                     '2   Seçtiğin Flick tuşuna bir kez bas.',
                     '3   Açık hedef doğrulanınca tek atış gönderilir.',
                     '4   Atış gerçekleşince eski bakışa dönülür.',
                     '5   Seçtiğin bıçak tuşuna basılır.'):
            self.text(right,line,11,FG).pack(anchor='w',pady=5)
        self.text(right,'Bıçaktayken tekrar bas: önceki silah çekilir,\nhazır olunca flick yapılıp bıçağa dönülür.\nTuşu basılı tutmak tekrarlamaz; bırakıp bas.\nOtomatik tetik bu sıra boyunca bekler.',10,BLUE).pack(anchor='w',pady=(14,0))
        self.text(right,'Sıfır kaçırma / tek mermiyle öldürme garantisi yoktur.\nHareket, saçılım ve gecikme sonucu etkiler.\nHedef kapalıysa veya silah hazır değilse ateşlenmez.\nR8 ve silahın üçlü atış modu bu akışta desteklenmez.',9,'#E5BF80').pack(anchor='w',pady=(18,0))
        self.flick_label = self.text(right,'Hazır',10,BLUE,True)
        self.flick_label.configure(wraplength=540,justify='left')
        self.flick_label.pack(anchor='w',pady=(12,0))


    def draw_preview(self):
        if not hasattr(self, 'preview') or self.closing:
            return
        cv = self.preview
        width, height = max(180, cv.winfo_width()), max(140, cv.winfo_height())
        cv.delete('scene')
        cv.create_rectangle(0, height * .67, width, height, fill='#172235', outline='', tags='scene')
        for i in range(1, 7):
            cv.create_line(0, height * .67 + i * 22, width, height * .67 + i * 22, fill='#223047', tags='scene')
        for x in range(0, int(width) + 1, 60):
            cv.create_line(width / 2, height * .55, x, height, fill='#223047', tags='scene')
        colors = PALETTES.get(self.cfg.esp_palette, PALETTES['Koral / Mavi'])
        for index, (x, size) in enumerate(((width * .31, height * .58), (width * .76, height * .40))):
            pose = sample_pose(x, height * .19 + (height * .58 - size), size)
            color = colors[index]
            for a, b in ((5, 8), (8, 9), (9, 11), (5, 13), (13, 14), (14, 16),
                         (2, 22), (22, 23), (23, 24), (2, 25), (25, 26), (26, 27), (5, 2)):
                thickness = size * (.20 if (a, b) == (5, 2) else .09)
                if self.cfg.glow_chams:
                    cv.create_line(*pose[a], *pose[b], fill=color, width=thickness + 5,
                                   capstyle='round', tags='scene')
                cv.create_line(*pose[a], *pose[b], fill='#35465D', width=thickness,
                               capstyle='round', tags='scene')
            hx, hy = pose[6]
            radius = size * .065
            cv.create_oval(hx - radius, hy - radius, hx + radius, hy + radius,
                           fill='#43536A', outline=color if self.cfg.glow_chams else '#52647C', width=3, tags='scene')

    def slider_changed(self, key, value, suffix):
        if self.initializing:
            return
        number = round(float(value), 1) if key == 'smooth' else int(float(value))
        setattr(self.cfg, key, number)
        if key in ('smooth','speed_cap'):
            self.cfg.aim_response = 'Ayarlanabilir'
            self.vars['aim_response'].set('Ayarlanabilir')
        elif key in ('aim_settle_ms','aim_max_speed'):
            self.cfg.aim_response = 'Akıcı takip'
            self.vars['aim_response'].set('Akıcı takip')
        self.sync_aim_tuning()
        self.scale_labels[key].configure(text=f'{number:g}{suffix}')
        self.queue_settings_save()
        self.draw_preview()

    def save_controls(self, event=None):
        if self.initializing:
            return
        for key, value in self.vars.items():
            result = value[1][value[0].get()] if isinstance(value, tuple) else value.get()
            setattr(self.cfg, key, result)
        self.cfg.vis_check, self.cfg.wall_lock_active = True, False
        self.sync_aim_tuning()
        self.queue_settings_save()
        self.draw_preview()

    def queue_settings_save(self):
        if self.save_token is not None:self.root.after_cancel(self.save_token)
        self.save_token=self.root.after(200,self.flush_settings)

    def flush_settings(self):
        if self.save_token is not None:
            self.root.after_cancel(self.save_token)
            self.save_token=None
            if self.cfg.save() is False:
                self.eng.stats.status('Ayar','Ayar dosyası kaydedilemedi')
                raise OSError('Ayar dosyası kaydedilemedi')

    def refresh_controls(self):
        self.initializing=True
        try:
            for key,item in self.vars.items():
                value=getattr(self.cfg,key)
                if isinstance(item,tuple):
                    var,mapping=item
                    var.set(next((label for label,v in mapping.items() if v==value),next(iter(mapping))))
                else:item.set(value)
            for key,scale in self.scales.items():
                value=getattr(self.cfg,key);scale.set(value)
                self.scale_labels[key].configure(text=f'{value:g}{self.scale_suffixes[key]}')
            self.sync_aim_tuning()
        finally:self.initializing=False
        self.draw_preview()

    def sync_aim_tuning(self):
        if hasattr(self, 'aim_mode_note'):
            notes = {'Akıcı takip': 'Süre ve hız sınırıyla yumuşak takip.',
                     'Keskin kilit': 'Anlık dönüş; yumuşatma uygulanmaz.',
                     'Ayarlanabilir': 'Yumuşatma ve hız ayarları uygulanır.'}
            self.aim_mode_note.config(text=notes.get(self.cfg.aim_response, ''))
        for name,frame in self.aim_tuning_frames.items():
            if name == self.cfg.aim_response:
                if not frame.winfo_manager(): frame.pack(fill='x')
            else:
                frame.pack_forget()

    def update_status(self):
        if self.closing:
            return
        self.offset_label.config(text=self.eng.offset_status, fg=MUTED if self.eng.ready else '#E5BF80')
        self.glow_label.config(text=self.eng.glow_status)
        if hasattr(self,'flick_label'):
            self.flick_label.config(text=getattr(self.eng,'flick_status','Hazır') if self.cfg.flick_enabled else 'Flick shot kapalı')
        runtime=self.eng.runtime_config;runtime.view()
        states,_=self.eng.stats.snapshot()
        phase=states.get('Nişan','Nişan tuşu bekleniyor') if self.cfg.enabled else 'Duraklatıldı · F2 ile başlat'
        self.guard_label.config(text=phase+' · Profil: '+runtime.active_name)
        if self.cfg.enabled:
            state, button = 'AKTİF', 'DURDUR  ·  F2'
        elif self.eng.ready:
            state, button = 'DURAKLATILDI', 'BAŞLAT  ·  F2'
        elif getattr(self.eng,'loading',False):
            state, button = 'HAZIRLANIYOR', 'DOSYALAR KONTROL EDİLİYOR'
        else:
            state, button = 'BAŞLATILAMADI', 'YENİDEN DENE  ·  F2'
        self.state_label.config(text=state)
        self.btn.config(text=button)
        self.root.after(200, self.update_status)

    def poll_hotkeys(self):
        if self.closing:
            return
        try:
            actions = {0x71:self.toggle,0x72:self.toggle_ui,0x73:self.toggle_trigger}
            for key in self.hotkey_edges.poll():
                logging.info('Hotkey F%d', key-0x6f)
                actions[key]()
        except Exception:
            logging.exception('Function-key action failed')
        finally:
            if not self.closing:
                self.root.after(16,self.poll_hotkeys)

    def toggle(self):
        if self.cfg.enabled or self.eng.ready:
            self.cfg.enabled = not self.cfg.enabled
            logging.info('Enabled=%s',self.cfg.enabled)
        elif not getattr(self.eng,'loading',False):
            import threading
            self.eng.loading = True
            self.eng.offset_status = 'Dosyalar yeniden kontrol ediliyor...'
            threading.Thread(target=self.eng.fetch,daemon=True).start()
        else:
            logging.info('Start waiting: %s',self.eng.offset_status)

    def toggle_ui(self):
        self.root.deiconify() if self.root.state() == 'withdrawn' else self.root.withdraw()

    def toggle_trigger(self):
        self.cfg.trigger_enabled = not self.cfg.trigger_enabled
        self.vars['trigger_enabled'].set(self.cfg.trigger_enabled)
        self.queue_settings_save()
        self.trigger_notify_time = time.monotonic()


    def close(self):
        try:self.flush_settings()
        except OSError:logging.exception('Settings could not be saved on close')
        self.closing = True
        self.cfg.enabled = False
        self.eng.stop_event.set()
        if hasattr(self.eng,'visibility'):
            self.eng.visibility.close()
        if self.live:
            if getattr(self.eng,'aim_thread',None):
                self.eng.aim_thread.join(timeout=.5)
            if self.eng.trigger_thread:
                self.eng.trigger_thread.join(timeout=.5)
            if self.eng.glow_thread:
                self.eng.glow_thread.join(timeout=.8)
        if hasattr(self.eng,'fire_control'):
            self.eng.fire_control.close()
        self.root.destroy()
