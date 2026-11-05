"""Run on desktop_smoke's private display/HOME. Never trigger a real system action."""
import json
import os
import subprocess
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway-shell'))
widgets=runpy.run_path(str(repo/'scripts/madway_widgets.py'))
system=runpy.run_path(str(repo/'scripts/madway_system.py'))
errors=[];calls=[]
def capture(name):
    directory=os.environ.get('MADWAY_TEST_ARTIFACTS')
    if directory:
        path=Path(directory);path.mkdir(parents=True,exist_ok=True)
        subprocess.run(['grim','-o','HEADLESS-1',str(path/(name+'.png'))],check=True,timeout=5)


assert system['nm_rows'](r'Office\: WiFi:80:AA\:BB:usb\\wifi')==[['Office: WiFi','80','AA:BB','usb\\wifi']]

def command(args):
    calls.append(args)
    if args[0]=='bluetoothctl':
        return 'Controller AA:BB (public)\n Name: Fixture Bluetooth\n Powered: yes' if args[-1]=='show' else 'Device CC:DD Fixture headphones'
    fields=args[args.index('--fields')+1] if '--fields' in args else ''
    return {'STATE,CONNECTIVITY,WIFI':'connected:full:enabled',
        'DEVICE,TYPE,STATE,CONNECTION':'wlan0:wifi:connected:Office\\: WiFi',
        'IN-USE,SSID,SIGNAL,SECURITY,BSSID,DEVICE':'*:Office\\: WiFi:90:WPA2:AA\\:BB:wlan0\n:Guest:60::CC\\:DD:wlan0',
        'UUID,NAME,TYPE,DEVICE':'fixture-uuid:Office\\: WiFi:802-11-wireless:wlan0\nvpn-uuid:Fixture VPN:vpn:--'}.get(fields,'')
system['network_snapshot'].__globals__['command']=command
system['NetworkPane'].job.__globals__['command']=command
system['BluetoothPane'].read.__globals__['command']=command
# Default argument is bound at definition, so explicitly inject into snapshots.
original_snapshot=system['network_snapshot']
system['NetworkPane'].refresh.__globals__['network_snapshot']=lambda:original_snapshot(command)
window=Gtk.Window();box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.add(box)
network=system['NetworkPane'](window);bluetooth=system['BluetoothPane']();box.add(network);box.add(bluetooth)
window.show_all()

def inspect_providers():
    try:
        assert 'connected' in network.status.get_text()
        assert 'Office: WiFi' in network.devices.get_text()
        assert len(network.networks.get_children())==3
        assert len(network.saved.get_children())==3
        assert network.wifi.get_state()
        assert not any('radio' in args or 'disconnect' in args or 'power' in args for args in calls),'Opening settings changed the hardware'
        assert bluetooth.power.get_label()=='Power off' and 'Fixture headphones' in bluetooth.devices.get_text()
        # Toggle only the mocked backend; ensure explicit user change, not polling.
        network.wifi.set_active(False)
    except BaseException as error:errors.append(error)
    GLib.timeout_add(100,finish_providers);return False

def finish_providers():
    try:assert any(args[-4:]==['radio','wifi','off'][-4:] or args[-3:]==['radio','wifi','off'] for args in calls),calls
    except BaseException as error:errors.append(error)
    window.destroy();Gtk.main_quit();return False
GLib.timeout_add(300,inspect_providers);Gtk.main()
if errors:raise AssertionError('System providers failed') from errors[0]
print('PASS: escaped NM fields, network/device/saved VPN rows, explicit radio changes, Bluetooth and no changes on opening settings.',flush=True)

with tempfile.TemporaryDirectory(prefix='madway-preview-ui-') as tmp:
    directory=Path(tmp);(directory/'previews').mkdir()
    row=dict(id=1,title='Preview fixture',minimized=True,preview=1,visible_workspace=True)
    state=dict(windows=[row]);(directory/'desktop.json').write_text(json.dumps(state))
    import cairo
    surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,240,135);cr=cairo.Context(surface);cr.set_source_rgb(.7,.2,.1);cr.paint();surface.write_to_png(str(directory/'previews/1.png'))
    button=Gtk.Button();sent=[];preview=widgets['TaskPreview'](button,1,lambda:directory,lambda name,**values:sent.append((name,values)))
    preview.prefetch();assert sent==[('window-preview',dict(id=1))]
    tip=SimpleNamespace(set_custom=lambda widget:None)
    assert preview.query(button,0,0,False,tip)
    assert preview.image.get_storage_type()==Gtk.ImageType.SURFACE and 'Restore' in preview.title.get_text()
    state['locked']=True;(directory/'desktop.json').write_text(json.dumps(state))
    assert not preview.query(button,0,0,False,tip)
    button.destroy()
print('PASS: thumbnail tooltip, restore label, snapshot request and locked-session privacy.',flush=True)

panel=runpy.run_path(str(repo/'scripts/madway-panel'))
for theme in api['themes']().sections():
    cfg=api['settings']();cfg['appearance']['theme']=theme
    provider=Gtk.CssProvider();provider.load_from_data((api['theme_style'](panel['CSS'].decode(),cfg)+api['overlay_style']('utilities.css',cfg)).encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+4)
    menu=panel['DesktopMenu'](20,25,'Clock')
    calendar=next(child for child in menu.box.get_children() if isinstance(child,Gtk.Calendar))
    from datetime import datetime
    today=datetime.now();assert calendar.get_date()==(today.year,today.month-1,today.day)
    calendar.select_month((today.month)%12,today.year);assert calendar.get_date()[1]==today.month%12
    def close_calendar(theme=theme):
        if theme=='argent-dark':capture('calendar-midnight')
        menu.window.destroy();return False
    GLib.timeout_add(100,close_calendar);Gtk.main()
    Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),provider)
    for operation,accept in [('reboot',False),('poweroff',True),('logout',False)]:
        dialog_api=dict(runtime_directory=api['runtime_directory'],overlay_style=lambda name,cfg=cfg:api['overlay_style'](name,cfg))
        dialog=widgets['SessionConfirmation'](operation,dialog_api)
        assert not any(panel['Layer'].get_anchor(dialog.window,edge) for edge in (panel['Layer'].Edge.TOP,panel['Layer'].Edge.BOTTOM,panel['Layer'].Edge.LEFT,panel['Layer'].Edge.RIGHT))
        assert panel['Layer'].get_exclusive_zone(dialog.window)==-1
        def inspect(dialog=dialog,accept=accept,cfg=cfg,theme=theme,operation=operation):
            try:
                if theme in ('argent','argent-dark') and operation=='poweroff':capture('confirmation-'+theme)
                assert dialog.window.get_focus() is dialog.cancel,'Destructive action had initial focus'
                foreground=dialog.accept.get_child().get_style_context().get_color(Gtk.StateFlags.NORMAL)
                expected=api['contrast_text'](api['palette'](cfg)['active'])
                assert max(foreground.red,foreground.green,foreground.blue)>.95 if expected=='#ffffff' else max(foreground.red,foreground.green,foreground.blue)<.05
            except BaseException as error:errors.append(error)
            (dialog.accept if accept else dialog.cancel).clicked();return False
        GLib.timeout_add(100,inspect);assert dialog.run()==accept
if errors:raise AssertionError('Calendar / dialog theme regression') from errors[0]
print('PASS: seven palettes, calendar month navigation, centered layer dialogs, contrast, cancellation focus and accept/cancel without any machine actions.',flush=True)
