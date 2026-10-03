"""Capture every page using the shipped zipapp, GTK and the real read-only backend."""
import os,sys,time,cairo
sys.path.insert(0,os.path.abspath('dist/macout'))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
from macout_app import services,gui
from macout_app.gui_common import PAGES
OUT=os.environ.get('SHOTS','/tmp/visual-final');os.makedirs(OUT,exist_ok=True)
os.environ['MACOUT_HOME']=os.path.join(OUT,'data')
app=services.App();app.settings.data.update(first_run_done=True,theme='dark')
win=gui.MacOutWindow(app);win.resize(1200,800)
def pump(sec=.5):
 end=time.monotonic()+sec
 while time.monotonic()<end:
  while Gtk.events_pending():Gtk.main_iteration_do(False)
  time.sleep(.01)
def shot(name):
 pump();w=win.get_window();s=cairo.ImageSurface(cairo.FORMAT_ARGB32,w.get_width(),w.get_height());win.draw(cairo.Context(s));s.write_to_png(os.path.join(OUT,name+'.png'))
pump(3)
for i,page in enumerate(PAGES):
 win.goto(page);pump()
 if page=='MAC Control':
  win.vendor_search.set_text('Cisco');pump(.6);win.vendor_tv.get_selection().select_path(Gtk.TreePath.new_first())
 if page=='Diagnostics':win.run_diag();pump(4)
 if page=='Reports':
  win.export_report(os.path.join(OUT,'verified-report.html'));pump(20)
 shot('%02d-%s'%(i,page.lower().replace(' ','-')))
print('Captured all 12 pages',flush=True)
app.rotation.shutdown()
