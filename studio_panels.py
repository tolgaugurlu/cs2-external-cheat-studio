"""Compact profile editing and local diagnostics panels; no game input."""
import tkinter as tk
from tkinter import ttk

from settings_profiles import CHOICES, ENUMS, WEAPON_FIELDS, WEAPONS

BG='#0C111B';CARD='#151E2D';FG='#EDF2F8';MUTED='#9CAEC5';BLUE='#88CFFF';EDGE='#29374B'


class StudioPanels:
    def action_button(self,parent,title,command):
        button=tk.Button(parent,text=title,command=command,bg=EDGE,fg=FG,activebackground='#35465D',
                         activeforeground=FG,bd=0,padx=10,pady=7,font=('Segoe UI',-13),cursor='hand2')
        button.pack(side='left',padx=(0,6),pady=5)
        return button

    def profiles_page(self,page):
        book=ttk.Notebook(page)
        book.pack(fill='both',expand=True,pady=(4,0))
        self.profile_tabs=book
        weapons=tk.Frame(book,bg=BG);settings=tk.Frame(book,bg=BG)
        book.add(weapons,text='Silaha özel');book.add(settings,text='Ayar profilleri')
        self.weapon_page(weapons)
        self.settings_page(settings)

    def weapon_page(self,page):
        left=self.card(page,'Silah profili')
        left.pack(side='left',fill='y',padx=(0,10),pady=4)
        left.configure(width=240)
        self.check(left,'Otomatik profil geçişi','weapon_profiles_enabled')
        self.weapon_selection=tk.StringVar(value='AWP')
        selector=ttk.Combobox(left,textvariable=self.weapon_selection,values=list(CHOICES),state='readonly',width=23)
        selector.pack(fill='x',pady=8)
        selector.bind('<<ComboboxSelected>>',lambda event:self.load_weapon_editor())
        self.weapon_note=self.text(left,'',9,BLUE)
        self.weapon_note.configure(wraplength=220,justify='left')
        self.weapon_note.pack(anchor='w',pady=8)
        self.text(left,'Silah profili genel ayarlarını\ndeğiştirmez. Kaydedilmemiş\nsilahlar genel / grup ayarını kullanır.\n\nÖncelik: silah → grup → genel.\nSağdaki alanlar Kaydet düğmesine\nbasana kadar uygulanmaz.',9,MUTED).pack(anchor='w',pady=8)
        buttons=tk.Frame(left,bg=CARD);buttons.pack(fill='x',pady=5)
        self.action_button(buttons,'Eldeki silah',self.select_current_weapon)
        right=self.card(page,'Bu silahın nişan ayarları')
        right.pack(side='left',fill='both',expand=True,pady=4)
        grid=tk.Frame(right,bg=CARD);grid.pack(fill='x')
        self.weapon_vars={}
        labels={'aim_response':'Tepki biçimi','fov':'FOV (px)','target_bone':'Hedef noktası',
                'aim_settle_ms':'Yerleşme (ms)','aim_max_speed':'Hız (°/sn)','smooth':'Yumuşatma',
                'speed_cap':'Ayarlı hız sınırı','rcs_enabled':'Geri tepme','rcs_scale':'Dikey RCS (%)',
                'rcs_yaw_scale':'Yatay RCS (%)','trigger_mode':'Tetik biçimi','trigger_delay':'Tetik gecikmesi (ms)',
                'awp_mode':'AWP modu','flick_bone':'Flick noktası','flick_fov':'Flick açısı (°)'}
        mappings={'target_bone':{'Akıllı':100,'Kafa':6,'Boyun':5,'Gövde':4},
                  'flick_bone':{'Kafa':6,'Gövde':4},'rcs_enabled':{'Açık':True,'Kapalı':False},
                  'awp_mode':{'Açık':True,'Kapalı':False},'trigger_mode':self.trigger_modes}
        for i,key in enumerate(WEAPON_FIELDS):
            cell=tk.Frame(grid,bg=CARD);cell.grid(row=i//3,column=i%3,sticky='ew',padx=(0,8),pady=1)
            grid.columnconfigure(i%3,weight=1,uniform='weapon-fields')
            self.text(cell,labels[key],9,MUTED).pack(anchor='w',pady=(0,3))
            var=tk.StringVar();mapping=mappings.get(key)
            options=list(mapping) if mapping else ENUMS.get(key)
            if options:
                widget=ttk.Combobox(cell,textvariable=var,values=options,state='readonly',width=12)
            else:widget=ttk.Entry(cell,textvariable=var,width=12)
            widget.pack(fill='x')
            self.weapon_vars[key]=(var,mapping)
        buttons=tk.Frame(right,bg=CARD);buttons.pack(fill='x',pady=(8,0))
        self.action_button(buttons,'Profili kaydet',self.save_weapon_editor)
        self.action_button(buttons,'Genelden kopyala',lambda:self.load_weapon_editor(base=True))
        self.action_button(buttons,'Özel ayarı kaldır',self.remove_weapon_editor)
        self.weapon_feedback=self.text(right,'',9,BLUE)
        self.weapon_feedback.configure(wraplength=610,justify='left')
        self.weapon_feedback.pack(anchor='w',pady=3)
        self.load_weapon_editor()

    def select_current_weapon(self):
        name=WEAPONS.get(self.eng.runtime_config.weapon_id)
        if name:
            self.weapon_selection.set(name);self.load_weapon_editor()
        else:self.weapon_feedback.config(text='Önce oyunda desteklenen bir silah seç.')

    def load_weapon_editor(self,base=False):
        key=CHOICES[self.weapon_selection.get()]
        values=({name:getattr(self.cfg,name) for name in WEAPON_FIELDS} if base else self.eng.profiles.weapon_values(key,self.cfg))
        for name,(var,mapping) in self.weapon_vars.items():
            value=values[name]
            var.set(next((label for label,v in mapping.items() if v==value),next(iter(mapping))) if mapping else str(value))
        self.weapon_note.config(text='Kayıtlı özel profil' if key in self.eng.profiles.data['weapons'] else 'Henüz özel profil yok')
        if hasattr(self,'weapon_feedback'):self.weapon_feedback.config(text='Genel ayarlar forma kopyalandı; kaydetmeden uygulanmaz.' if base else '')

    def save_weapon_editor(self):
        try:
            values={}
            for key,(var,mapping) in self.weapon_vars.items():
                raw=var.get()
                values[key]=mapping[raw] if mapping else raw if key in ENUMS else float(raw.replace(',','.'))
            self.eng.profiles.save_weapon(CHOICES[self.weapon_selection.get()],values)
            self.load_weapon_editor()
            self.weapon_feedback.config(text='Kaydedildi. Bu silah seçildiğinde otomatik uygulanır.')
            self.eng.stats.status('Profil',self.weapon_selection.get()+' profili kaydedildi')
        except (OSError,ValueError,KeyError) as error:self.weapon_feedback.config(text=str(error))

    def remove_weapon_editor(self):
        try:
            self.eng.profiles.remove_weapon(CHOICES[self.weapon_selection.get()])
            self.load_weapon_editor();self.weapon_feedback.config(text='Özel ayar kaldırıldı; grup / genel ayarı kullanılır.')
        except (OSError,ValueError) as error:self.weapon_feedback.config(text=str(error))

    def settings_page(self,page):
        box=self.card(page,'Ayarlarını isimle sakla')
        box.pack(fill='both',expand=True,pady=8)
        self.text(box,'Genel ayarlar ve silah profilleri birlikte kaydedilir. Başlat / durdur durumu kaydedilmez.',10,MUTED).pack(anchor='w')
        row=tk.Frame(box,bg=CARD);row.pack(fill='x',pady=(18,8))
        self.settings_selection=tk.StringVar(value='Başlangıç ayarlarım')
        self.settings_combo=ttk.Combobox(row,textvariable=self.settings_selection,
                values=list(self.eng.profiles.data['settings']),state='readonly',width=35)
        self.settings_combo.pack(side='left',padx=(0,12))
        self.action_button(row,'Yükle',self.load_settings_profile)
        self.action_button(row,'Yüklemeyi geri al',lambda:self.load_settings_profile(undo=True))
        self.action_button(row,'Sil',self.delete_settings_profile)
        self.text(box,'Yeni profil adı / güncellenecek profil',9,MUTED).pack(anchor='w',pady=(16,5))
        row=tk.Frame(box,bg=CARD);row.pack(fill='x')
        self.settings_name=tk.StringVar()
        ttk.Entry(row,textvariable=self.settings_name,width=35).pack(side='left',padx=(0,12))
        self.action_button(row,'Mevcut ayarları kaydet',self.save_settings_profile)
        self.profile_feedback=self.text(box,'Başlangıç ayarların korumalıdır; üzerine yazılmaz.',10,BLUE)
        self.profile_feedback.configure(wraplength=860,justify='left')
        self.profile_feedback.pack(anchor='w',pady=18)
        self.text(box,'“Yüklemeyi geri al” son profil yüklemesinden önceki ayarları geri getirir.\nAynı adla kaydetmek o profili günceller. Silaha özel kayıtlar genel ayar dosyasından ayrı tutulur.',10,MUTED).pack(anchor='w',pady=8)

    def refresh_profile_list(self):
        names=list(self.eng.profiles.data['settings'])
        self.settings_combo.configure(values=names)
        if self.settings_selection.get() not in names:self.settings_selection.set(names[0])

    def save_settings_profile(self):
        try:
            self.flush_settings()
            name=self.settings_name.get().strip()
            self.eng.profiles.save_settings(name,self.cfg)
            self.refresh_profile_list();self.settings_selection.set(name)
            self.profile_feedback.config(text='Profil kaydedildi: '+name)
        except (OSError,ValueError) as error:self.profile_feedback.config(text=str(error))

    def load_settings_profile(self,undo=False):
        try:
            self.flush_settings()
            name=self.settings_selection.get()
            self.eng.profiles.apply_settings(name,self.cfg,undo=undo)
            self.refresh_controls();self.load_weapon_editor()
            message='Önceki ayarlar geri yüklendi.' if undo else 'Profil yüklendi: '+name
            self.profile_feedback.config(text=message);self.eng.stats.status('Profil',message)
        except (OSError,ValueError,KeyError) as error:self.profile_feedback.config(text=str(error))

    def delete_settings_profile(self):
        try:
            self.eng.profiles.remove_settings(self.settings_selection.get())
            self.refresh_profile_list();self.profile_feedback.config(text='Profil silindi; mevcut ayarlar değişmedi.')
        except (OSError,ValueError) as error:self.profile_feedback.config(text=str(error))

    def dashboard(self,page):
        cols=[tk.Frame(page,bg=BG) for _ in range(2)]
        for i,col in enumerate(cols):
            col.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 10,0),pady=8)
            page.columnconfigure(i,weight=1,uniform='diagnostics')
        page.rowconfigure(0,weight=1)
        status=self.card(cols[0],'Canlı durum');status.pack(fill='x')
        self.status_text=self.text(status,'',10,FG)
        self.status_text.configure(wraplength=420,justify='left');self.status_text.pack(anchor='w')
        history=self.card(cols[0],'Son durum değişiklikleri');history.pack(fill='both',expand=True,pady=(10,0))
        self.event_list=tk.Text(history,bg=CARD,fg=MUTED,bd=0,highlightthickness=0,font=('Segoe UI',-12),height=8,width=20,wrap='word',state='disabled')
        self.event_list.pack(fill='both',expand=True)
        perf=self.card(cols[1],'Uygulama performansı');perf.pack(fill='both',expand=True)
        self.perf_text=self.text(perf,'Ölçüm hazırlanıyor…',12,BLUE,True)
        self.perf_text.configure(justify='left');self.perf_text.pack(anchor='w',pady=6)
        self.stage_text=self.text(perf,'',10,FG)
        self.stage_text.configure(justify='left');self.stage_text.pack(anchor='w',pady=16)
        self.text(perf,'CPU: bu uygulamanın toplam işlemci kapasitesindeki payı.\nBellek: çalışan uygulama süreci; oyun belleği dahil değil.\n\nSüreler son 3 saniyedeki döngülerin ortalaması / P95.\nP95: örneklerin %95’inin altında kaldığı süre.\nBu değerler oyun FPS’si veya ağ gecikmesi değildir.\nÖlçüm saniyede bir yenilenir.',9,MUTED).pack(anchor='w',pady=8)

    def update_dashboard(self):
        if self.closing:return
        eng=self.eng;runtime=eng.runtime_config;runtime.view()
        stats=eng.stats;metrics=stats.sample()
        states,events=stats.snapshot()
        trigger=('Flick için bekliyor' if eng.fire_control.owner else 'Açık' if self.cfg.trigger_enabled else 'Kapalı') if hasattr(eng,'fire_control') else 'Kapalı'
        self.status_text.config(text='Nişan: '+states.get('Nişan','Oyun / nişan tuşu bekleniyor')+
            '\nSilah: '+runtime.weapon_name+'\nEtkin profil: '+runtime.active_name+'\nTetik: '+trigger+
            '\nHarita: '+getattr(getattr(eng,'visibility',None),'status','Bekleniyor')+
            '\nGörünüm: '+getattr(eng,'glow_status','Bekleniyor'))
        self.event_list.configure(state='normal');self.event_list.delete('1.0','end')
        for stamp,area,message in events[-4:]:self.event_list.insert('end',f'{stamp}  {area}: {message}\n')
        self.event_list.configure(state='disabled')
        fmt=lambda value,unit:'—' if value is None else f'{value:.1f} {unit}'
        self.perf_text.config(text='CPU   '+fmt(metrics.get('cpu'),'%')+'\nBellek (RAM)   '+fmt(metrics.get('rss'),'MiB')+
                                   '\nÖzel ayrılan bellek   '+fmt(metrics.get('private'),'MiB'))
        rows=[]
        for key in ('Nişan','ESP'):
            value=metrics.get('stages',{}).get(key)
            rows.append(f'{key}:  {value["mean"]:.2f} / {value["p95"]:.2f} ms' if value else key+':  bekliyor')
        self.stage_text.config(text='Döngü süreleri · ortalama / P95\n\n'+'\n'.join(rows))
        if eng.profiles.error:self.profile_feedback.config(text=eng.profiles.error)
        self.root.after(1000,self.update_dashboard)
