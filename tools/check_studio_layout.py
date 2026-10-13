"""Exercise our own offscreen Tk window; no game connection or desktop capture."""
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from memory_bot import Config,KEY_MAP,B_MAP,T_MODES
from control_panel import ControlPanel
from settings_profiles import settings_snapshot


def main():
    output=Path('build/studio-preview');output.mkdir(parents=True,exist_ok=True)
    reports=[]
    for scaling in (96/72,120/72,144/72):
        cfg=SimpleNamespace(**settings_snapshot(Config),enabled=False)
        for key,value in json.loads(Path('examples/default-settings.json').read_text(encoding='utf-8')).items():setattr(cfg,key,value)
        cfg.save=lambda:True
        before=settings_snapshot(cfg)
        eng=SimpleNamespace(ready=True,offset_status='Offsetler hazır: sezzyaep / build 14190',
            glow_status='Model konturu: etkin',flick_status='Önceki silah çekiliyor · hazır olması bekleniyor',
            stop_event=threading.Event(),glow_thread=None,visibility=SimpleNamespace(status='Duvar testi hazır · de_dust2',close=lambda:None))
        root=tk.Tk();root.withdraw();root.tk.call('tk','scaling',scaling)
        panel=ControlPanel(root,eng,cfg,KEY_MAP,B_MAP,T_MODES,live=False)
        root.geometry('980x650+10000+10000');root.deiconify();root.update()
        eng.stats.status('Nişan','FOV içinde görünür hedef bulunamadı')
        panel.update_dashboard();root.update()
        report={'dpi':round(scaling*72),'size':[root.winfo_width(),root.winfo_height()],'clipped':[],'text_cut':[]}
        def inspect(widget):
            if widget.winfo_ismapped() and widget is not root:
                parent=widget.nametowidget(widget.winfo_parent())
                x=widget.winfo_rootx()-parent.winfo_rootx();y=widget.winfo_rooty()-parent.winfo_rooty()
                if x < -1 or y < -1 or x+widget.winfo_width()>parent.winfo_width()+1 or y+widget.winfo_height()>parent.winfo_height()+1:
                    report['clipped'].append([tab,str(widget),widget.winfo_class(),x,y,widget.winfo_width(),widget.winfo_height()])
                if widget.winfo_class() in ('Label','Button','Checkbutton'):
                    if widget.winfo_reqwidth()>widget.winfo_width()+2 or widget.winfo_reqheight()>widget.winfo_height()+2:
                        report['text_cut'].append([tab,widget.cget('text'),widget.winfo_reqwidth(),widget.winfo_width(),widget.winfo_reqheight(),widget.winfo_height()])
            for child in widget.winfo_children():inspect(child)
        for tab in range(5):
            panel.tabs.select(tab);root.update();inspect(root)
            assert panel.btn.winfo_ismapped(), 'Activation button must remain visible'
            assert panel.guard_label.winfo_ismapped(), 'Footer status must remain visible'
            if tab==3:
                assert panel.weapon_feedback.winfo_ismapped(), 'Weapon save result must be visible'
                panel.profile_tabs.select(1);root.update();inspect(root)
                panel.profile_tabs.select(0)
        report['initial_settings_preserved']=settings_snapshot(cfg)==before

        panel.weapon_selection.set('AWP');panel.load_weapon_editor()
        panel.weapon_vars['fov'][0].set('45');panel.save_weapon_editor()
        eng.runtime_config.select(9)
        assert eng.runtime_config.view().fov==45 and cfg.fov==before['fov']
        panel.settings_name.set('UI test');panel.save_settings_profile()
        cfg.fov=400;cfg.aim_response='Ayarlanabilir'
        changed=settings_snapshot(cfg)
        panel.settings_selection.set('UI test');panel.load_settings_profile();root.update()
        assert settings_snapshot(cfg)==before
        panel.load_settings_profile(undo=True);root.update()
        assert settings_snapshot(cfg)==changed
        report['profile_buttons']=True
        for callback in root.tk.call('after','info'):root.after_cancel(callback)
        panel.close();reports.append(report)
    (output/'layout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(reports,ensure_ascii=True))
    return 1 if any(r['clipped'] or r['text_cut'] or not r['initial_settings_preserved'] for r in reports) else 0


if __name__=='__main__':sys.exit(main())
