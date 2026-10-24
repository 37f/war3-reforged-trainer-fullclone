"""Exercise actual main GUI/current-map search; only directory queries reach game."""
import argparse
import json
from pathlib import Path
import sys
import time
import subprocess
import ctypes as C
from ctypes.wintypes import RECT
import tkinter as tk
from tkinter import ttk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import war3_reforged_trainer as app

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid',type=int,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)

class ProbeTrainer(app.War3Trainer):
    def _start_persistent_bootstrap(self): pass

trainer=ProbeTrainer(args.pid)
# Keep the hook owner (this GUI/test thread) alive across async UI workers.
trainer.current_map_catalog_client().query(318)
root=tk.Tk();captured={};report={}
original_class=app.CampaignCatalogUI
def capture(*a,**kw):
    captured['ui']=original_class(*a,**kw);return captured['ui']
app.CampaignCatalogUI=capture
tk.Tk=lambda:root

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

def screenshot(path,bounds):
    x,y,right,bottom=bounds;quoted=str(path).replace("'","''")
    script=(f"Add-Type -AssemblyName System.Drawing; $bitmap=New-Object System.Drawing.Bitmap({right-x},{bottom-y}); "
            f"$graphics=[System.Drawing.Graphics]::FromImage($bitmap); $graphics.CopyFromScreen({x},{y},0,0,$bitmap.Size); "
            f"$bitmap.Save('{quoted}',[System.Drawing.Imaging.ImageFormat]::Png); $graphics.Dispose(); $bitmap.Dispose()")
    subprocess.run(['powershell.exe','-NoProfile','-Command',script],check=True,capture_output=True)

def run_checks():
    # Prevent main's automatic bootstrap/resource/hotkey jobs. Only the catalog
    # controller is restarted, using its normal widgets and callbacks.
    for job in root.tk.call('after','info'):root.after_cancel(job)
    ui=captured['ui'];ui.set_runtime_client(trainer.current_map_catalog_client());ui._poll()
    tab=ui._panels['unit'].master;tab.master.select(tab)
    ui.modes['unit'].set('runtime');ui._source_changed('unit');ui.detect_runtime()
    deadline=time.monotonic()+15
    while ui._busy and time.monotonic()<deadline:root.update();time.sleep(.01)
    assert ui.runtime_snapshot is not None,ui.status.get()
    report['counts']={k:len(ui.rows(k,'')) for k in ('unit','item','ability')}
    assert report['counts']=={'unit':64,'item':14,'ability':33}
    entry=next(w for w in descendants(tab) if isinstance(w,ttk.Entry) and not isinstance(w,ttk.Combobox))
    entry.insert(0,'H600');entry.focus_force();entry.event_generate('<KeyRelease>',keysym='H');root.update()
    tree=next(w for w in descendants(tab) if isinstance(w,ttk.Treeview))
    assert tree.get_children()==('H600',),tree.get_children()
    tree.selection_set('H600')
    copy=next(w for w in descendants(tab) if isinstance(w,ttk.Button) and w.cget('text')=='复制 ID')
    copy.invoke();assert root.clipboard_get()=='H600'
    report['search_copy']={'id':root.clipboard_get(),'name':tree.item('H600','values')[1]}
    root.attributes('-topmost',True);root.update();time.sleep(.1)
    # DWM bounds are physical pixels, unlike Tk's DPI-virtualized coordinates.
    user=C.WinDLL('user32');user.GetAncestor.argtypes=[C.c_void_p,C.c_uint];user.GetAncestor.restype=C.c_void_p
    outer=user.GetAncestor(root.winfo_id(),2);rectangle=RECT()
    dwm=C.WinDLL('dwmapi');dwm.DwmGetWindowAttribute.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint]
    assert dwm.DwmGetWindowAttribute(outer,9,C.byref(rectangle),C.sizeof(rectangle))==0
    bounds=(rectangle.left,rectangle.top,rectangle.right,rectangle.bottom)
    screenshot(args.output/'r21-current-map-unit.png',bounds)
    ui.check_runtime()
    while ui._busy:root.update();time.sleep(.01)
    # Use the existing language selector, preserving the author's object names.
    combos=[w for w in descendants(root) if isinstance(w,ttk.Combobox) and 'English' in tuple(w.cget('values'))]
    if combos:
        combo=combos[0];combo.set('English');combo.event_generate('<<ComboboxSelected>>');root.update()
        assert tree.heading('name')['text']=='Name'
        assert tree.item('H600','values')[1]==report['search_copy']['name']
        report['english']=True
        screenshot(args.output/'r21-current-map-english.png',bounds)
    else:raise AssertionError('Language selector was not found')
    ui.modes['unit'].set('general');ui._source_changed('unit');root.update()
    assert ui.runtime_snapshot is None
    report['general_restored']=len(tree['columns'])==4
    report['ok']=True
    (args.output/'main-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

root.mainloop=run_checks
try:app.run_gui()
finally:
    trainer.close()
    root.destroy()
