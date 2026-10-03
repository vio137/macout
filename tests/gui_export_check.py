"""Exercise real GTK save/overwrite/cancel dialogs and vendor selection in the shipped zipapp.
Run on a desktop or Xvfb with: DISPLAY=:99 python3 tests/gui_export_check.py
"""
import os, sys, time, json, zipfile, stat
sys.path.insert(0, os.path.abspath('dist/macout'))
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk
from macout_app import services, gui, core
OUT = os.environ.get('SHOTS', '/tmp/export-check')
os.makedirs(OUT, exist_ok=True)
os.environ['MACOUT_HOME']=os.path.join(OUT,'data')
app=services.App()
app.settings.data.update(first_run_done=True,confirm_actions=True)
win=gui.MacOutWindow(app)
win.resize(1200,800)
results=[]
def pump(sec=.2):
    end=time.monotonic()+sec
    while time.monotonic()<end:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        time.sleep(.01)
def wait(cond, timeout=40):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        pump()
        if cond(): return True
    return False
def check(name, cond):
    results.append(bool(cond)); print(('PASS ' if cond else 'FAIL ')+name,flush=True)
def shot(name):
    pump(.4)
    w=win.get_window()
    import cairo
    surf=cairo.ImageSurface(cairo.FORMAT_ARGB32,w.get_width(),w.get_height())
    win.draw(cairo.Context(surf));surf.write_to_png(os.path.join(OUT,name+'.png'))
def auto_dialog(path=None, cancel=False):
    state={'set':False,'n':0}
    def handle():
        ds=[d for d in Gtk.Window.list_toplevels() if isinstance(d,Gtk.FileChooserDialog) and d.get_visible()]
        if not ds: return True
        d=ds[0]
        if cancel: d.response(Gtk.ResponseType.CANCEL); return False
        if not state['set']:
            d.set_current_folder(OUT); d.set_current_name(os.path.basename(path)); state['set']=True
            check('save dialog defaults to invoking user folder', os.path.isdir(services.export_folder()))
            return True
        state['n']+=1
        if state['n']>=3:
            d.response(Gtk.ResponseType.OK); return False
        return True
    GLib.timeout_add(200,handle)
wait(lambda: bool(win.snaps))
win.goto('Reports');pump()
for idx,fmt in enumerate(('html','txt','json','csv','zip')):
    win.rp_fmt.set_active(idx)
    path=os.path.join(OUT,'gui-report.'+fmt)
    auto_dialog(path); win.rp_export_btn.clicked()
    check(fmt+' save via real dialog',wait(lambda: win.last_export==path and win.rp_export_btn.get_sensitive()))
    check(fmt+' exists and private',os.path.isfile(path) and stat.S_IMODE(os.stat(path).st_mode)==0o600)
    check(fmt+' belongs to invoker',os.stat(path).st_uid==services.desktop_identity().pw_uid)
with zipfile.ZipFile(os.path.join(OUT,'gui-report.zip')) as z:
    check('ZIP four readable files',len(z.namelist())==4 and z.testzip() is None)
with open(os.path.join(OUT,'gui-report.json')) as f:
    check('JSON parses',json.load(f)['macout_version']==core.VERSION)
win.rp_fmt.set_active(0);auto_dialog(os.path.join(OUT,'name without suffix'));win.rp_export_btn.clicked()
check('missing extension appended',wait(lambda: win.last_export.endswith('name without suffix.html')))
previous=win.last_export
auto_dialog(cancel=True);win.rp_export_btn.clicked();pump()
check('cancel keeps last export',win.last_export==previous)
win.export_report('/not-a-real-folder/export.html')
check('unwritable folder visible error',wait(lambda: 'Export failed' in win.rp_msg.get_text()))
win.export_report(os.path.join(OUT,'gui-report.html'));wait(lambda: 'Saved:' in win.rp_msg.get_text())
shot('reports-fixed')
win.goto('MAC Control');win.vendor_search.set_text('Cisco');pump(.7)
win.vendor_tv.get_selection().select_path(Gtk.TreePath.new_first());pump()
check('select vendor produces 12 unique rows',len(win.candidate_store)==12 and len({r[0] for r in win.candidate_store})==12)
win.candidate_tv.get_selection().select_path(Gtk.TreePath.new_from_indices([6]));pump()
check('selected row matches candidate',win.vendor_candidate==win.candidate_store[6][0])
old=win.vendor_candidate
win.vendor_tv.get_selection().select_path(Gtk.TreePath.new_from_indices([1]));pump()
check('switching vendor clears stale MAC',win.vendor_candidate!=old and core.oui_of(win.vendor_candidate) in win.vendor_prefixes[win.vendor_pick[1]])
win.vendor_search.set_text('no-such-vendor-zzz');pump(.6)
check('empty search disables apply',win.vendor_candidate is None and not win.vendor_apply_btn.get_sensitive())
win.vendor_search.set_text('Cisco');pump(.6);win.vendor_tv.get_selection().select_path(Gtk.TreePath.new_first());pump()
shot('vendor-series')
win.toggle_theme();pump();shot('vendor-series-dark')
win.goto('Reports');pump();shot('reports-dark')
print('SUMMARY %d/%d passed' %(sum(results),len(results)),flush=True)
app.rotation.shutdown()
sys.exit(0 if all(results) else 1)
