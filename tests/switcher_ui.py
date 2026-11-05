"""Switcher layout/lifecycle checks on desktop_smoke.py's private display."""
import json
from pathlib import Path
import runpy
import tempfile
from unittest.mock import patch
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GdkPixbuf','2.0')
from gi.repository import Gtk,Gdk,GLib,GdkPixbuf

api=runpy.run_path(str(Path(__file__).resolve().parent.parent/'scripts/madway-panel'))
scope=api['WindowSwitcher'].__init__.__globals__
errors=[]
with tempfile.TemporaryDirectory(prefix='madway-switcher-ui-') as tmp:
    root=Path(tmp);(root/'previews').mkdir()
    rows=[dict(id=index,title=f'Window {index} — '+('long title ' * 12),app_id='org.madway.Fixture',
               focused=index==1,minimized=index==3,preview=1) for index in range(1,19)]
    for row in rows:
        if row['id']==2:continue  # Missing previews still produce usable cards.
        image=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,480,300)
        image.fill(0x304050ff);image.savev(str(root/'previews'/f"{row['id']}.png"),'png',[],[])
    for theme in ('black','argent','argent-dark'):
        cfg=api['settings']();cfg['appearance']['theme']=theme
        state=dict(switcher=True,output_x=0,output_y=0,windows=[dict(row) for row in rows])
        def write():(root/'desktop.json').write_text(json.dumps(state))
        write()
        with patch.dict(scope,runtime_directory=lambda:root,settings=lambda:cfg):
            switcher=api['WindowSwitcher']();original={}
            def check(stage=0):
                try:
                    if stage==0:
                        bounds=Gdk.Display.get_default().get_monitor(0).get_geometry()
                        assert switcher.window.get_allocated_width()<=bounds.width
                        assert switcher.window.get_allocated_height()<=bounds.height
                        assert switcher.box.get_style_context().has_class('switcher-surface')
                        assert not switcher.box.get_style_context().has_class('menu')
                        assert len(switcher.cards)==18 and switcher.count.get_text()=='1 / 18'
                        fallback=switcher.cards[2].get_child().get_children()[0]
                        assert fallback.get_storage_type()==Gtk.ImageType.ICON_NAME
                        original.update(switcher.cards)
                        for row in state['windows']:row['focused']=row['id']==18
                        write();switcher.refresh()
                        assert all(switcher.cards[key] is button for key,button in original.items()),'Cycling rebuilt preview cards'
                        assert switcher.count.get_text()=='18 / 18'
                        assert sum(button.get_style_context().has_class('selected') for button in switcher.cards.values())==1
                    elif stage==1:
                        adjustment=switcher.scroll.get_vadjustment();position=switcher.cards[18].translate_coordinates(switcher.items,0,0)
                        assert adjustment.get_value()>0,'Selected row was not revealed'
                        assert position[1]>=adjustment.get_value()-1
                        assert position[1]+switcher.cards[18].get_allocated_height()<=adjustment.get_value()+adjustment.get_page_size()+1
                        state['windows']=[row for row in state['windows'] if row['id']!=2]
                        write();switcher.refresh();assert len(switcher.cards)==17
                    else:
                        state['switcher']=False;write();assert not switcher.refresh()
                        assert switcher.closed and switcher.refresh_source==0 and not switcher.previews
                        return False
                    GLib.timeout_add(100,lambda:check(stage+1))
                except BaseException as error:
                    errors.append(error);switcher.window.destroy()
                return False
            GLib.timeout_add(150,check);Gtk.main()
    if errors:raise AssertionError('Switcher UI regression') from errors[0]
print('PASS: three-theme switcher bounds, missing previews, stable cards while cycling, scroll-to-selection, removal and cleanup.',flush=True)
