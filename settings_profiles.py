"""Separate, atomic profile storage. Runtime overrides never mutate base settings."""
import copy
import json
import math
import os
from pathlib import Path
import struct
import tempfile


WEAPONS = {1:'Desert Eagle',2:'Dual Berettas',3:'Five-SeveN',4:'Glock-18',7:'AK-47',8:'AUG',9:'AWP',
           10:'FAMAS',11:'G3SG1',13:'Galil AR',14:'M249',16:'M4A4',17:'MAC-10',19:'P90',23:'MP5-SD',
           24:'UMP-45',25:'XM1014',26:'PP-Bizon',27:'MAG-7',28:'Negev',29:'Sawed-Off',30:'Tec-9',
           32:'P2000',33:'MP7',34:'MP9',35:'Nova',36:'P250',38:'SCAR-20',39:'SG 553',40:'SSG 08',
           60:'M4A1-S',61:'USP-S',63:'CZ75-Auto',64:'R8 Revolver'}
GROUPS = {'Tabancalar':(1,2,3,4,30,32,36,61,63,64), 'Keskin nişancı':(9,11,38,40),
          'Tüfekler':(7,8,10,13,16,39,60), 'Hafif makineli':(17,19,23,24,26,33,34),
          'Pompalılar':(25,27,29,35), 'Ağır makineli':(14,28)}
CHOICES = {**{f'Grup · {g}':'group:'+g for g in GROUPS},
           **{name:'weapon:'+str(i) for i,name in sorted(WEAPONS.items(),key=lambda p:p[1])}}
RANGES = {'fov':(10,600), 'smooth':(1,50), 'speed_cap':(5,250), 'aim_settle_ms':(40,200),
          'aim_max_speed':(120,1440), 'rcs_scale':(0,150),'rcs_yaw_scale':(0,150),
          'trigger_delay':(0,200),'flick_fov':(1,180),'esp_text_scale':(80,150)}
ENUMS = {'aim_response':('Akıcı takip','Keskin kilit','Ayarlanabilir'), 'target_bone':(100,6,5,4),
         'trigger_mode':('TAP','BURST','SPRAY_FULL','SPRAY','LEGIT','AWP','PISTOL_MACRO'),
         'flick_bone':(6,4), 'team_mode':(0,1,2)}
WEAPON_FIELDS = ('aim_response','fov','target_bone','aim_settle_ms','aim_max_speed','smooth','speed_cap',
                 'rcs_enabled','rcs_scale','rcs_yaw_scale','trigger_mode','trigger_delay','awp_mode',
                 'flick_bone','flick_fov')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def settings_snapshot(cfg):
    return {key:copy.deepcopy(value) for key in dir(cfg) if not key.startswith('_') and key!='enabled'
            and isinstance((value:=getattr(cfg,key)),(bool,int,float,str,list,dict,type(None)))}


def validate_values(values, baseline, weapon=False):
    if not isinstance(values,dict):raise ValueError('Profil ayarları geçersiz')
    result={}
    for key,value in values.items():
        if weapon and key not in WEAPON_FIELDS:raise ValueError('Silah profili yalnızca nişan ayarları içerebilir')
        if key=='enabled' or key not in baseline or (weapon and key not in WEAPON_FIELDS):continue
        original=baseline[key]
        if isinstance(original,bool):valid=isinstance(value,bool)
        elif isinstance(original,(float,int)):
            valid=isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)
            if valid and isinstance(original,int):valid=int(value)==value
        else:valid=isinstance(value,type(original))
        if not valid:raise ValueError(f'{key}: değer türü geçersiz')
        if key in RANGES and not RANGES[key][0]<=value<=RANGES[key][1]:raise ValueError(f'{key}: değer aralık dışında')
        if key in ENUMS and value not in ENUMS[key]:raise ValueError(f'{key}: seçenek geçersiz')
        result[key]=copy.deepcopy(value)
    return result


class ProfileStore:
    def __init__(self,path,cfg,persist=True):
        self.path=Path(path) if path else None
        self.baseline=settings_snapshot(cfg)
        self.error=''
        self.revision=0
        self.data={'version':1,'weapons':{},'settings':{'Başlangıç ayarlarım':self.bundle(cfg)},'undo':None}
        if self.path and self.path.exists():
            try:
                if self.path.stat().st_size>2_000_000:raise ValueError('Profil dosyası çok büyük')
                raw=json.loads(self.path.read_text(encoding='utf-8-sig'))
                if raw.get('version')!=1:raise ValueError('Profil dosyası sürümü desteklenmiyor')
                self._check_weapons(raw['weapons'])
                if not isinstance(raw['settings'],dict) or not 1<=len(raw['settings'])<=100:
                    raise ValueError('Profil listesi geçersiz')
                for name,bundle in raw['settings'].items():
                    self.name(name);self._check_bundle(bundle)
                if raw.get('undo') is not None:self._check_bundle(raw['undo'])
                self.data=raw
            except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
                self.error=f'Profil dosyası okunamadı: {error}'
        elif persist and self.path:
            try:atomic_json(self.path,self.data)
            except OSError as error:self.error=f'Profil kaydı yapılamadı: {error}'

    @staticmethod
    def name(name):
        if not isinstance(name,str) or not name.strip() or len(name.strip())>48:
            raise ValueError('Profil adı 1–48 karakter olmalı')
        return name.strip()

    def bundle(self,cfg):
        return {'values':settings_snapshot(cfg),'weapons':copy.deepcopy(getattr(self,'data',{}).get('weapons',{}))}

    def _check_weapons(self,rules):
        if not isinstance(rules,dict) or len(rules)>100:raise ValueError('Silah profilleri geçersiz')
        for key,values in rules.items():
            if key not in CHOICES.values():raise ValueError('Bilinmeyen silah profili')
            validate_values(values,self.baseline,True)

    def _check_bundle(self,bundle):
        validate_values(bundle['values'],self.baseline)
        self._check_weapons(bundle['weapons'])

    def _commit(self,data):
        if self.error:raise ValueError(self.error+' · özgün dosya korunuyor')
        if self.path:atomic_json(self.path,data)
        self.data=data
        self.revision+=1

    def weapon_values(self,key,cfg):
        values={name:getattr(cfg,name) for name in WEAPON_FIELDS}
        if key.startswith('weapon:'):
            item=int(key.split(':')[1])
            group=next((g for g,ids in GROUPS.items() if item in ids),None)
            values.update(self.data['weapons'].get('group:'+str(group),{}))
        values.update(self.data['weapons'].get(key,{}))
        return values

    def save_weapon(self,key,values):
        if key not in CHOICES.values():raise ValueError('Silah seç')
        values=validate_values(values,self.baseline,True)
        data=copy.deepcopy(self.data);data['weapons'][key]=values
        self._commit(data)

    def remove_weapon(self,key):
        data=copy.deepcopy(self.data);data['weapons'].pop(key,None)
        self._commit(data)

    def save_settings(self,name,cfg):
        name=self.name(name)
        if name=='Başlangıç ayarlarım':raise ValueError('Başlangıç profili korunur; başka bir ad seç')
        if name not in self.data['settings'] and len(self.data['settings'])>=100:raise ValueError('En fazla 100 profil')
        data=copy.deepcopy(self.data);data['settings'][name]=self.bundle(cfg)
        self._commit(data)

    def remove_settings(self,name):
        if name=='Başlangıç ayarlarım':raise ValueError('Başlangıç profili silinemez')
        data=copy.deepcopy(self.data);data['settings'].pop(name,None)
        self._commit(data)

    def apply_settings(self,name,cfg,undo=False):
        bundle=self.data.get('undo') if undo else self.data['settings'].get(name)
        if not bundle:raise ValueError('Yüklenecek profil yok')
        self._check_bundle(bundle)
        values=validate_values(bundle['values'],settings_snapshot(cfg))
        old=self.bundle(cfg)
        data=copy.deepcopy(self.data);data['undo']=old;data['weapons']=copy.deepcopy(bundle['weapons'])

        prior=self.data
        self._commit(data)
        for key,value in values.items():setattr(cfg,key,value)
        try:
            if cfg.save() is False:raise OSError('Ayar dosyası yazılamadı')
        except Exception:
            for key,value in old['values'].items():setattr(cfg,key,value)
            self._commit(prior)
            raise


class EffectiveConfig:
    def __init__(self,base,values):self.base,self.values=base,values
    def __getattr__(self,key):return self.values[key] if key in self.values else getattr(self.base,key)


class WeaponRuntime:
    def __init__(self,base,store):
        self.base,self.store=base,store
        self.weapon_id=None;self.weapon_name='Silah bekleniyor'
        self.active_name='Genel ayarlar';self.identity=None;self.failed_at=0.
        self.view_key=None;self.cached_view=None

    def select(self,item):
        self.weapon_id=item
        self.weapon_name=WEAPONS.get(item,'Bıçak / ekipman' if item else 'Silah bekleniyor')

    def view(self):
        token=(self.weapon_id,self.store.revision,getattr(self.base,'weapon_profiles_enabled',True))
        if token==self.view_key:return self.cached_view
        values={};name='Genel ayarlar'
        if getattr(self.base,'weapon_profiles_enabled',True) and self.weapon_id in WEAPONS:
            group=next((g for g,ids in GROUPS.items() if self.weapon_id in ids),None)
            for key,label in [('group:'+str(group),group),('weapon:'+str(self.weapon_id),self.weapon_name)]:
                if key in self.store.data['weapons']:
                    values.update(self.store.data['weapons'][key]);name=label
        self.active_name=name
        self.view_key=token;self.cached_view=EffectiveConfig(self.base,values)
        return self.cached_view

    def observe(self,eng,local,weapon,entity_list,now):
        identity=(local,weapon,entity_list,eng.client)
        if identity==self.identity or (identity==getattr(self,'failed_identity',None) and now-self.failed_at<.5):return
        try:
            pointer=eng.entity_from_index(entity_list,weapon) if weapon not in (0,0xFFFFFFFF) else 0
            if pointer:
                address=pointer+eng._f('C_EconEntity','m_AttributeManager')+eng._f('C_AttributeContainer','m_Item')+eng._f('C_EconItemView','m_iItemDefinitionIndex')
                item=struct.unpack('<H',eng.read_bytes(address,2))[0]
            else:item=None
            self.select(item);self.identity=identity
        except (OSError,ValueError,KeyError):
            self.select(None);self.identity=None;self.failed_identity=identity;self.failed_at=now

    def clear(self):
        self.select(None);self.identity=None
