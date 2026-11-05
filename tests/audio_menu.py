"""Mixer layout with many devices and long labels, in a private Wayland session."""
import configparser
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import time

repo=Path(__file__).resolve().parent.parent


def ui():
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,Gdk,GLib
    from unittest.mock import patch
    api=runpy.run_path(str(repo/'scripts/madway-panel'))
    scope=api['AudioMixer'].__init__.__globals__;errors=[];messages=[]
    groups=[('Outputs',[dict(kind='sink',id=index,label='HDA NVidia Pro '+str(index)+' — long HDMI output name',
        volume=value,mute=False,default=index==1,adjustable=True) for index,value in enumerate((25,85,100,97),1)]),
        ('Inputs',[dict(kind='source',id=1,label='Built-in Audio Analog Stereo microphone',volume=70,mute=False,default=True,adjustable=True)]),
        ('Applications · playback',[dict(kind='sink-input',id=index,label='Browser video stream — '+('long application title '*5),
        volume=50,mute=False,default=False,adjustable=True) for index in range(8)]),('Applications · recording',[])]
    bounds=Gdk.Display.get_default().get_monitor(0).get_geometry()
    for theme in ('argent','argent-dark','black'):
        cfg=api['settings']();cfg['appearance']['theme']=theme
        provider=Gtk.CssProvider();provider.load_from_data(api['api']['theme_style'](api['CSS'].decode(),cfg).encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        with patch.dict(scope,settings=lambda:cfg,send=lambda name,**values:messages.append((name,values))),patch.dict(api['api'],audio_snapshot=lambda:groups):
            menu=api['DesktopMenu'](bounds.x+bounds.width-20,bounds.y+22,'Audio')
            def check(stage=0):
                try:
                    mixer=menu.mixer;scroll=mixer.scroll
                    assert len(mixer.rows)==13
                    assert menu.window.get_allocated_width()<=bounds.width
                    assert menu.window.get_allocated_height()<=bounds.height-22
                    assert api['Layer'].get_margin(menu.window,api['Layer'].Edge.LEFT)+menu.window.get_allocated_width()<=bounds.width
                    assert api['Layer'].get_margin(menu.window,api['Layer'].Edge.TOP)+menu.window.get_allocated_height()<=bounds.height
                    heights=[]
                    for key,(slider,_,mute,_,default) in mixer.rows.items():
                        line=slider.get_parent();card=line.get_parent();header=card.get_children()[0]
                        value=mixer.values[key];s,v=slider.get_allocation(),value.get_allocation()
                        h,l=header.get_allocation(),line.get_allocation()
                        assert h.y+h.height<=l.y and s.x+s.width+6<=v.x
                        assert v.width>=38 and slider.get_allocated_width()>100
                        assert mute.get_allocated_width()>=34 and mute.get_allocated_height()<=26
                        assert not slider.get_draw_value()
                        # Every caption and control stays inside its card.
                        for widget in header.get_children():
                            rect=widget.get_allocation()
                            point=widget.translate_coordinates(header,0,0)
                            assert point[0]>=0 and point[0]+rect.width<=header.get_allocated_width(),(theme,point,rect.width,header.get_allocated_width())
                        color=value.get_style_context().get_color(Gtk.StateFlags.NORMAL)
                        if theme=='argent':assert max(color.red,color.green,color.blue)<.25,'Light-theme value is unreadable'
                        else:assert min(color.red,color.green,color.blue)>.65
                        heights.append(card.get_allocated_height())
                        if stage==0:
                            point=card.translate_coordinates(scroll,0,0)
                            if 0<=point[1]<scroll.get_allocated_height():
                                assert point[1]+card.get_allocated_height()<=scroll.get_allocated_height(),'Popup opens on a clipped device row'
                    assert max(heights)-min(heights)<=2 and max(heights)<=60,heights
                    adjustment=scroll.get_vadjustment()
                    assert adjustment.get_upper()>adjustment.get_page_size(),'Many devices must scroll'
                    footer=menu.box.get_children()[-1];pos=scroll.translate_coordinates(menu.box,0,0)
                    assert pos[1]+scroll.get_allocated_height()<=footer.get_allocation().y
                    if stage==0:
                        slider,_,mute,_,default=mixer.rows[('sink',2)]
                        slider.set_value(62);mixer.release(('sink',2));mute.set_active(True);default.clicked()
                        mixer.update(groups,None)
                        assert mixer.values[('sink',2)].get_text()=='62%' and mute.get_active()
                        artifacts=os.environ.get('MADWAY_TEST_ARTIFACTS')
                        if artifacts:
                            target=Path(artifacts);target.mkdir(parents=True,exist_ok=True)
                            subprocess.run(['grim',str(target/('audio-'+theme+'.png'))],check=True,timeout=5)
                        adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size())
                        GLib.timeout_add(120,lambda:check(1));return False
                    last=mixer.rows[('sink-input',7)][0].get_parent().get_parent()
                    pos=last.translate_coordinates(scroll,0,last.get_allocated_height())
                    assert 0<pos[1]<=scroll.get_allocated_height(),'Last application cannot be reached'
                    assert any(name=='audio-control' and values.get('operation')=='volume' and values.get('value')==62 for name,values in messages)
                    assert any(values.get('operation')=='default' for name,values in messages)
                except BaseException as error:errors.append(error)
                menu.window.destroy();return False
            GLib.timeout_add(350,check);Gtk.main()
        Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),provider)
    if errors:raise AssertionError('Audio menu layout regression') from errors[0]
    print('PASS: light/dark/black mixer, long labels, 13 device/app rows, value contrast, separate control bounds, bottom scrolling and edit retention.',flush=True)


def session():
    with tempfile.TemporaryDirectory(prefix='madway-audio-menu-') as tmp:
        root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
        config=root/'config';(config/'madway').mkdir(parents=True)
        (config/'madway/settings.ini').write_text('[output:HEADLESS-1]\nmode=640x480@60000\n')
        env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_RUNTIME_DIR':str(runtime),
            'WLR_BACKENDS':'headless','WLR_RENDERER':'pixman','GDK_BACKEND':'wayland','GIO_USE_VFS':'local',
            'DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus')}
        for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_SESSION','MADWAY_NATIVE','LD_PRELOAD'):env.pop(key,None)
        with (root/'server.log').open('w') as log:
            server=subprocess.Popen([str(repo/'build/madway')],env=env,stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    text=(root/'server.log').read_text();match=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text)
                    if match:break
                    assert server.poll() is None,text
                    time.sleep(.02)
                else:raise AssertionError('Private compositor did not start')
                subprocess.run([sys.executable,str(Path(__file__).resolve()),'--ui'],env={**env,'WAYLAND_DISPLAY':match[1]},check=True,timeout=15)
            finally:
                server.terminate()
                try:server.wait(timeout=5)
                except subprocess.TimeoutExpired:server.kill();server.wait()
                assert server.returncode==0,(root/'server.log').read_text()


if __name__=='__main__':
    ui() if '--ui' in sys.argv else session()
