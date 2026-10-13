"""Desktop controls and overlay presentation; no input automation in this module."""
import ctypes
import math
import logging
import struct
import time
import tkinter as tk
from tkinter import ttk

from esp_visuals import CanvasSink, EspRenderer, PROFILES, PALETTES, BONE_IDS, sample_pose
from targeting import team_allowed
from hotkeys import HotkeyEdges
from visual_context import view_context
from gdi_overlay import GdiSink
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
        self.last_overlay_error = 0
        self.pose_cache = {}
        self.save_token=None
        self.scale_suffixes={}
        if not hasattr(config,'weapon_profiles_enabled'):config.weapon_profiles_enabled=True
        if not hasattr(engine,'stats'):engine.stats=RuntimeStats()
        if not hasattr(engine,'profiles'):engine.profiles=ProfileStore(None,config,persist=False)
        if not hasattr(engine,'runtime_config'):engine.runtime_config=WeaponRuntime(config,engine.profiles)
        root.title('CS2 Studio')
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
        self.text(header, 'CS2 Studio', 20, FG, True).pack(side='left')
        self.text(header, 'PYTHON · WINDOWS', 10, MUTED).pack(side='left', padx=14)
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
            self.setup_overlay()
            self.draw_overlay()

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
        cols=[tk.Frame(page,bg=BG) for _ in range(3)]
        for i,col in enumerate(cols):
            col.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 10,0),pady=8)
            page.columnconfigure(i,weight=1 if i<2 else 2,uniform='appearance')
        page.rowconfigure(0,weight=1)
        model=self.card(cols[0],'Karakter modeli');model.pack(fill='both',expand=True)
        self.check(model,'Model silueti / Glow','glow_chams')
        self.combo(model,'Siluet yöntemi','esp_render_mode',['Otomatik','Kararlı siluet','Oyun konturu'])
        self.combo(model,'Renk paleti','esp_palette',list(PALETTES))
        note=self.text(model,'Otomatik: Glow çakışırsa bağımsız çizime geçer. Kararlı siluet yaklaşık vücut çizimidir; birebir model kaplaması değildir.',9,MUTED)
        note.configure(wraplength=185,justify='left');note.pack(anchor='w',pady=12)
        self.glow_label=self.text(model,'',9,BLUE)
        self.glow_label.configure(wraplength=185,justify='left');self.glow_label.pack(anchor='w',pady=8)
        info=self.card(cols[1],'Bilgi katmanı');info.pack(fill='both',expand=True)
        for text,key in [('Bilgi katmanı','ghost_esp'),('Köşe çerçeveleri','esp_boxes'),('İskelet çizgileri','esp_skeleton'),('Can çubuğu','esp_health'),('Mesafe etiketleri','esp_labels')]:
            self.check(info,text,key)
        self.combo(info,'Çizim profili','esp_profile',list(PROFILES))
        self.slider(info,'Yazı boyutu','esp_text_scale',80,150,'%')
        preview=self.card(cols[2],'Görünüm önizlemesi','Şematik örnek · oyun görüntüsü değildir')
        preview.pack(fill='both',expand=True)
        self.preview=tk.Canvas(preview,bg='#101825',highlightthickness=0,width=220,height=160)
        self.preview.pack(fill='both',expand=True)
        self.preview_renderer=EspRenderer(CanvasSink(self.preview))
        self.preview.bind('<Configure>',lambda event:self.draw_preview())
        self.text(preview,'RAKİP: vurgu rengi · TAKIM: mavi',9,MUTED).pack(anchor='w',pady=(8,0))
        self.text(preview,'F2 Başlat / durdur   F3 Gizle   F4 Tetik',9,MUTED).pack(anchor='w',pady=(4,0))

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
        self.sync_aim_tuning()
        self.combo(aim, 'Nişan tuşu', 'aim_key', list(self.key_map), self.key_map)
        self.combo(aim, 'Hedef noktası', 'target_bone', list(self.bone_map), self.bone_map)
        teams = {'Sadece rakipler': 1, 'Herkes / FFA': 0, 'Sadece takım': 2}
        self.combo(aim, 'Takım filtresi', 'team_mode', list(teams), teams)
        helpers = self.card(cols[1], 'Yardımcılar')
        helpers.pack(fill='x')
        self.check(helpers, 'Geri tepme düzeltmesi', 'rcs_enabled')
        self.check(helpers, 'BunnyHop', 'bhop_enabled')
        self.check(helpers, 'AWP modu', 'awp_mode')
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

    def renderer_options(self):
        return dict(profile=self.cfg.esp_profile, palette=self.cfg.esp_palette,
                    text_scale=self.cfg.esp_text_scale, skeleton=self.cfg.esp_skeleton,
                    boxes=self.cfg.esp_boxes, health_bar=self.cfg.esp_health, labels=self.cfg.esp_labels)

    def draw_preview(self):
        if not hasattr(self, 'preview_renderer') or self.closing:
            return
        cv = self.preview
        width, height = max(180, cv.winfo_width()), max(140, cv.winfo_height())
        cv.delete('scene')
        cv.create_rectangle(0, height * .67, width, height, fill='#172235', outline='', tags='scene')
        for i in range(1, 7):
            cv.create_line(0, height * .67 + i * 22, width, height * .67 + i * 22, fill='#223047', tags='scene')
        for x in range(0, int(width) + 1, 60):
            cv.create_line(width / 2, height * .55, x, height, fill='#223047', tags='scene')
        renderer = self.preview_renderer
        renderer.begin((width, height))
        colors = PALETTES.get(self.cfg.esp_palette, PALETTES['Koral / Mavi'])
        for index, (x, size, hp, distance) in enumerate(((width * .31, height * .58, 76, 18),
                                                       (width * .76, height * .40, 100, 34))):
            pose = sample_pose(x, height * .19 + (height * .58 - size), size)
            color = colors[index]
            silhouette = self.cfg.glow_chams and getattr(self.cfg,'esp_render_mode','Otomatik') != 'Oyun konturu'
            if not silhouette:
                # Deliberately schematic body, not a claim to preview the game's shader.
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
            if self.cfg.ghost_esp or silhouette:
                options=self.renderer_options()
                if not self.cfg.ghost_esp:
                    options.update(skeleton=False,boxes=False,health_bar=False,labels=False)
                renderer.player(index, pose, hp, distance, enemy=index == 0, silhouette=silhouette, **options)
        cv.tag_lower('scene')
        renderer.end()

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

    def setup_overlay(self):
        eng = self.eng
        self.ov = tk.Toplevel(self.root)
        self.ov.overrideredirect(True)
        self.ov.geometry(f'{eng.sx}x{eng.sy}+0+0')
        self.ov.attributes('-topmost', True, '-transparentcolor', 'black')
        self.ov.configure(bg='black')
        self.ov.update_idletasks()
        hwnd = int(self.ov.wm_frame(), 16)
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)

        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x08000000 | 0x80)
        self.cv = tk.Canvas(self.ov, bg='black', highlightthickness=0)
        self.cv.pack(fill='both', expand=True)
        self.renderer = EspRenderer(CanvasSink(self.cv))
        self.silhouette_renderer = EspRenderer(GdiSink(eng.sx,eng.sy))
        self.ov.withdraw()
        self.overlay_visible = False

    def draw_overlay(self):
        if self.closing:
            return
        eng, cfg, renderer = self.eng, self.cfg, self.renderer
        silhouette = cfg.glow_chams and (getattr(cfg,'esp_render_mode','Otomatik')=='Kararlı siluet'
                     or (getattr(cfg,'esp_render_mode','Otomatik')=='Otomatik' and getattr(eng,'glow_fallback',False)))
        players_visible = silhouette or (cfg.ghost_esp and any((cfg.esp_skeleton,cfg.esp_boxes,cfg.esp_health,cfg.esp_labels)))
        frame_time = time.monotonic()
        renderer.begin((eng.sx, eng.sy))
        self.silhouette_renderer.begin((eng.sx,eng.sy))
        try:
            if not (cfg.enabled and (cfg.ghost_esp or cfg.glow_chams)
                    and eng.pm and eng.ready and eng.is_game_foreground()):
                self.pose_cache.clear()
                return
            entity_list = eng.read_longlong(eng.client + eng.off['dwEntityList'])
            context = view_context(eng,entity_list) if entity_list else None
            if context is None:
                self.pose_cache.clear()
                return
            if players_visible:
                matrix = struct.unpack('16f', eng.read_bytes(eng.client + eng.off['dwViewMatrix'], 64))
                origin = eng._f('C_BasePlayerPawn', 'm_vOldOrigin')
                local_pos = (struct.unpack('3f',eng.read_bytes(context.camera_pawn + origin,12))
                             if context.camera_pawn else None)
                local_team = context.team
                bone_ids = BONE_IDS if silhouette or cfg.esp_skeleton else (6,2,24,27)
                options = self.renderer_options()
                if not cfg.ghost_esp:
                    options.update(skeleton=False,boxes=False,health_bar=False,labels=False)
                active=set()
                for index, (pawn, ctrl, entity_index) in sorted(tuple(eng.p_cache.items())):
                    try:
                        handle = eng.read_uint(ctrl + eng._off_ph)
                        if eng.entity_from_index(entity_list, handle) != pawn or context.excludes(pawn):
                            continue
                        hp, team = eng.read_int(pawn + eng._off_h), eng.read_team(pawn)
                        if hp <= 0 or not team_allowed(cfg.team_mode, local_team, team):
                            continue
                        key=(pawn,ctrl,handle)
                        active.add(key)
                        world = eng.get_bones(pawn, bone_ids)
                        if 2 in world and 6 in world and (24 in world or 27 in world):
                            self.pose_cache[key]=(frame_time,world)
                        elif key in self.pose_cache and frame_time-self.pose_cache[key][0] <= .1:

                            # camera, so read gaps never pin a figure to the screen.
                            world=self.pose_cache[key][1]
                        else:
                            continue
                        coords = {bone: point for bone, pos in world.items() if (point := eng.w2s(matrix, pos))}
                        distance = math.dist(local_pos,world[2]) * .0254 if local_pos else None
                        if silhouette:
                            self.silhouette_renderer.player((pawn,handle),coords,hp,distance,enemy=team!=local_team,
                                silhouette=True,palette=cfg.esp_palette,skeleton=False,boxes=False,health_bar=False,labels=False)
                        if cfg.ghost_esp:
                            renderer.player((pawn, handle), coords, hp, distance, enemy=team != local_team,
                                            targeted=index == eng.target_id, **options)
                    except (OSError, ValueError):
                        continue
                self.pose_cache={key:value for key,value in self.pose_cache.items()
                                 if key in active and frame_time-value[0] <= .1}
            self.draw_bomb(context.local)
            if time.monotonic() - getattr(self, 'trigger_notify_time', 0) < 2:
                renderer.banner('trigger', 'Tetik açık' if cfg.trigger_enabled else 'Tetik kapalı',
                                f'{cfg.trigger_delay} ms gecikme · F4', y=108, color=BLUE)
        except Exception as error:
            if time.monotonic() - self.last_overlay_error > 5:
                print(f'[Overlay] {type(error).__name__}: {error}')
                self.last_overlay_error = time.monotonic()
        finally:
            try:
                self.silhouette_renderer.end()
            except OSError:
                self.silhouette_renderer.sink.hide()
                logging.exception('Independent silhouette presentation failed')
            renderer.end()
            visible = bool(renderer.sink.items)
            if visible != self.overlay_visible:
                self.ov.deiconify() if visible else self.ov.withdraw()
                self.overlay_visible = visible

            drawing = visible or bool(self.silhouette_renderer.sink.items)
            if hasattr(eng,'stats'):eng.stats.timing('ESP',time.monotonic()-frame_time)
            self.root.after(33 if drawing and players_visible else 100, self.draw_overlay)

    def draw_bomb(self, local):
        """Compact timer, using schema fields and the current tick clock."""
        eng = self.eng
        try:
            holder = eng.read_longlong(eng.client + eng.off['dwPlantedC4'])
            bomb = eng.read_longlong(holder) if holder else 0
            field = lambda name: bomb + eng._f('C_PlantedC4', name)
            if not bomb or eng.read_bytes(field('m_bBombTicking'), 1) != b'\x01':
                self.bomb_defusing = False
                return
            controller = eng.read_longlong(eng.client + eng.off['dwLocalPlayerController'])
            ticks = eng.read_int(controller + eng._f('CBasePlayerController', 'm_nTickBase'))
            clock = ticks / 64
            remaining = eng.read_float(field('m_flC4Blow')) - clock
            length = eng.read_float(field('m_flTimerLength'))
            if not 0 < remaining <= 60 or length <= 0:
                return
            defusing = eng.read_bytes(field('m_bBeingDefused'), 1) == b'\x01'
            detail = 'Bomba aktif'
            if defusing:
                seconds = max(0, eng.read_float(field('m_flDefuseCountDown')) - clock)
                detail = f'Çözülüyor · {seconds:.1f} sn · ' + ('Süre yeterli' if seconds < remaining else 'Süre yetmiyor')
            elif getattr(self, 'bomb_defusing', False):
                self.bomb_cancelled_at = time.monotonic()
            if not defusing and time.monotonic() - getattr(self, 'bomb_cancelled_at', 0) < 3:
                detail = 'Çözme bırakıldı'
            self.bomb_defusing = defusing
            self.renderer.banner('bomb', f'C4  ·  {remaining:.1f} sn', detail, remaining / length,
                                 color=ACCENT if remaining < 10 else '#FFD27A')
        except (OSError, KeyError, ValueError):
            return

    def close(self):
        try:self.flush_settings()
        except OSError:logging.exception('Settings could not be saved on close')
        self.closing = True
        if hasattr(self,'silhouette_renderer'):
            self.silhouette_renderer.sink.close()
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
