"""Desktop grid and retargetable media animations on a private Wayland display."""
import json
from pathlib import Path
import runpy
import tempfile
from unittest.mock import patch
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway-desktop'));desktop=api['Desktop']();errors=[]
def inspect_grid():
    try:
        view=next(row['view'] for row in desktop.windows if len(row['view'].get_model()));cells=view.get_cells();positions=[]
        for index in range(len(view.get_model())):
            path=Gtk.TreePath.new_from_indices([index]);result=view.get_cell_rect(path,cells[0])
            if result[0]:positions.append(result[1])
        assert len(positions)>=12
        rows=sorted(set(rect.y for rect in positions));assert len(rows)>=2
        gaps=[b-a for a,b in zip(rows,rows[1:])];assert max(gaps)-min(gaps)<=1,('Unequal row pitch',gaps)
        centers={}
        for rect in positions:centers.setdefault(rect.y,[]).append(rect.x+rect.width/2)
        first=centers[rows[0]]
        for row in rows[1:]:assert centers[row]==first[:len(centers[row])],('Misaligned columns',centers)
    except BaseException as error:errors.append(error)
    desktop.close();return False
GLib.timeout_add(350,inspect_grid);Gtk.main()
if errors:raise errors[0]
print('PASS: fixed desktop icon centers and row pitch with long wrapped filenames.',flush=True)

panel=runpy.run_path(str(repo/'scripts/madway-panel'));scope=panel['MediaIndicator'].__init__.__globals__
with tempfile.TemporaryDirectory(prefix='madway-media-ui-') as tmp:
    root=Path(tmp);(root/'desktop.json').write_text('{}')
    data=dict(kind='volume',title='Volume 20%',value=20,serial=1,output_x=0,output_y=0)
    (root/'media.json').write_text(json.dumps(data))
    with patch.dict(scope,runtime_directory=lambda:root):
        indicator=panel['MediaIndicator']();first=[]
        def check(stage=0):
            try:
                if stage==0:
                    assert 0<indicator.visual<20,indicator.visual
                    first.append(indicator.visual)
                    data.update(value=80,serial=2);(root/'media.json').write_text(json.dumps(data));indicator.update(data)
                    assert indicator.origin<30,'Retargeting jumped to the old or new endpoint'
                elif stage==1:
                    assert first[0]<indicator.visual<80,indicator.visual
                else:
                    assert abs(indicator.visual-80)<.1
                    assert panel['Layer'].get_keyboard_mode(indicator.window)==panel['Layer'].KeyboardMode.NONE
                    (root/'desktop.json').write_text('{"locked":true}')
                    indicator.poll();assert indicator.closed
                    return False
                GLib.timeout_add(60 if stage==0 else 220,lambda:check(stage+1))
            except BaseException as error:errors.append(error);indicator.window.destroy()
            return False
        GLib.timeout_add(60,check);Gtk.main()
if errors:raise errors[0]
print('PASS: media bar animates at frame cadence, retargets from its current value, settles, and closes on lock.',flush=True)
