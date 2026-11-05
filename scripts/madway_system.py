"""Optional system settings providers; no shell strings or embedded credentials."""
import os
from pathlib import Path
import shutil
import subprocess
import threading
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gio,GLib


def nm_rows(text):
    """nmcli terse output escapes both colons and backslashes in names."""
    rows=[]
    for line in text.splitlines():
        row=[];field='';escaped=False
        for char in line:
            if escaped:field+=char;escaped=False
            elif char=='\\':escaped=True
            elif char==':':row.append(field);field=''
            else:field+=char
        row.append(field);rows.append(row)
    return rows


def command(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=18,env={**os.environ,'LC_ALL':'C'})
    if result.returncode:raise RuntimeError(result.stderr.strip() or 'Service unavailable')
    return result.stdout.strip()


def network_snapshot(run=command):
    prefix=['nmcli','--colors','no','--terse','--escape','yes']
    general=nm_rows(run(prefix+['--fields','STATE,CONNECTIVITY,WIFI','general','status']))
    devices=nm_rows(run(prefix+['--fields','DEVICE,TYPE,STATE,CONNECTION','device','status']))
    wifi=nm_rows(run(prefix+['--fields','IN-USE,SSID,SIGNAL,SECURITY,BSSID,DEVICE','device','wifi','list','--rescan','no']))
    connections=nm_rows(run(prefix+['--fields','UUID,NAME,TYPE,DEVICE','connection','show']))
    return dict(general=general[0] if general else [],devices=devices,wifi=wifi,connections=connections)


def launch_provider(candidates):
    for argv in candidates:
        if shutil.which(argv[0]):subprocess.Popen(argv,start_new_session=True);return
    raise RuntimeError('Install '+ ' or '.join(args[0] for args in candidates)+' to use this editor.')


class NetworkPane(Gtk.Box):
    __gtype_name__='MadwayNetworkPane'
    def __init__(self,parent):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.parent=parent;self.alive=True;self.busy=False;self.updating=False
        self.status=Gtk.Label(label='Reading NetworkManager…',xalign=0,wrap=True);self.pack_start(self.status,False,False,0)
        toolbar=Gtk.Box(spacing=5);self.pack_start(toolbar,False,False,0)
        self.wifi=Gtk.Switch();self.wifi.connect('state-set',self.radio)
        toolbar.pack_start(Gtk.Label(label='Wi-Fi'),False,False,0);toolbar.pack_start(self.wifi,False,False,0)
        self.refresh_button=Gtk.Button(label='Refresh / scan');self.refresh_button.connect('clicked',lambda w:self.refresh(True));toolbar.pack_end(self.refresh_button,False,False,0)
        self.devices=Gtk.Label(xalign=0,wrap=True,selectable=True);self.pack_start(self.devices,False,False,0)
        self.networks=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);self.pack_start(self.networks,False,False,0)
        self.saved=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);self.pack_start(self.saved,False,False,0)
        button=Gtk.Button(label='Edit connections, VPN, DNS & proxy…')
        button.connect('clicked',lambda w:self.external([['nm-connection-editor'],['systemsettings','kcm_networkmanagement']]))
        self.pack_start(button,False,False,0)
        self.note=Gtk.Label(label='Connect opens Konsole for NetworkManager authentication. Passwords stay out of command arguments. Changes here take effect immediately.',xalign=0,wrap=True,max_width_chars=48)
        self.pack_start(self.note,False,False,0)
        self.connect('destroy',self.destroyed)
        self.timer=GLib.timeout_add_seconds(15,self.refresh)
        self.refresh()

    def destroyed(self,*args):
        self.alive=False;GLib.source_remove(self.timer)

    def job(self,work,done):
        if self.busy:return
        self.busy=True;self.refresh_button.set_sensitive(False);self.wifi.set_sensitive(False)
        def worker():
            try:value=work();error=None
            except (OSError,RuntimeError,subprocess.TimeoutExpired) as exc:value=None;error=str(exc)
            def complete():
                if not self.alive:return False
                self.busy=False;self.refresh_button.set_sensitive(True);self.wifi.set_sensitive(True)
                if error:self.status.set_text(error)
                else:done(value)
                return False
            GLib.idle_add(complete)
        threading.Thread(target=worker,daemon=True).start()

    def external(self,candidates):
        try:launch_provider(candidates)
        except (OSError,RuntimeError) as error:self.status.set_text(str(error))

    def radio(self,widget,state):
        if self.updating:return False
        self.job(lambda:command(['nmcli','--wait','12','radio','wifi','on' if state else 'off']),lambda _:self.refresh())
        return True

    def refresh(self,scan=False):
        if not self.alive:return False
        if not self.busy:
            def read():
                if scan:command(['nmcli','--wait','12','device','wifi','rescan'])
                return network_snapshot()
            self.job(read,self.render)
        return True

    def action(self,args):
        self.job(lambda:command(['nmcli','--wait','12',*args]),lambda _:self.refresh())

    def render(self,snapshot):
        status=snapshot['general'];self.status.set_text(' · '.join(status[:2]) or 'NetworkManager unavailable')
        self.updating=True
        self.wifi.set_state(len(status)>2 and status[2]=='enabled');self.wifi.set_active(self.wifi.get_state())
        self.updating=False
        self.devices.set_text('\n'.join(f'{r[0]} · {r[1]} · {r[2]}'+(' · '+r[3] if r[3] not in ('','--') else '') for r in snapshot['devices'] if len(r)>=4) or 'No network devices')
        for box in (self.networks,self.saved):
            for child in box.get_children():child.destroy()
        self.networks.add(Gtk.Label(label='Nearby Wi-Fi networks',xalign=0))
        seen=set()
        for row in snapshot['wifi']:
            if len(row)!=6:continue
            active,ssid,signal,security,bssid,device=row
            if not ssid or (ssid,device) in seen:continue
            seen.add((ssid,device));line=Gtk.Box(spacing=5)
            title=Gtk.Label(label=f'{ssid} · {signal}% · {security or "open"}',xalign=0);title.set_ellipsize(3);title.set_max_width_chars(36)
            line.pack_start(title,True,True,0)
            button=Gtk.Button(label='Disconnect' if active=='*' else 'Connect')
            if active=='*':button.connect('clicked',lambda w,device=device:self.action(['device','disconnect',device]))
            else:button.connect('clicked',lambda w,bssid=bssid,device=device:self.external([['konsole','--separate','--platform','wayland','-e','nmcli','--ask','device','wifi','connect',bssid,'ifname',device]]))
            line.pack_end(button,False,False,0);self.networks.add(line)
        if not seen:self.networks.add(Gtk.Label(label='No nearby networks. Enable Wi-Fi or scan again.',xalign=0,wrap=True))
        self.saved.add(Gtk.Label(label='Saved connections · Ethernet / Wi-Fi / VPN',xalign=0))
        for row in snapshot['connections']:
            if len(row)!=4:continue
            uuid,name,kind,device=row;line=Gtk.Box(spacing=5)
            label=Gtk.Label(label=name+' · '+kind,xalign=0);label.set_ellipsize(3);label.set_max_width_chars(32);line.pack_start(label,True,True,0)
            active=device not in ('','--');button=Gtk.Button(label='Disconnect' if active else 'Connect')
            if active:button.connect('clicked',lambda w,uuid=uuid:self.action(['connection','down','uuid',uuid]))
            else:button.connect('clicked',lambda w,uuid=uuid:self.external([['konsole','--separate','--platform','wayland','-e','nmcli','--ask','connection','up','uuid',uuid]]))
            line.pack_end(button,False,False,0);self.saved.add(line)
        self.show_all()


class BluetoothPane(Gtk.Box):
    __gtype_name__='MadwayBluetoothPane'
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.alive=True;self.busy=False
        self.status=Gtk.Label(label='Reading Bluetooth adapters…',xalign=0,wrap=True);self.add(self.status)
        self.power=Gtk.Button(label='Power on');self.power.connect('clicked',lambda w:self.read('off' if self.power.get_label()=='Power off' else 'on'));self.add(self.power)
        self.devices=Gtk.Label(xalign=0,wrap=True,selectable=True);self.add(self.devices)
        button=Gtk.Button(label='Pair devices / Bluetooth manager…');button.connect('clicked',self.manager);self.add(button)
        refresh=Gtk.Button(label='Refresh');refresh.connect('clicked',lambda w:self.read());self.add(refresh)
        self.connect('destroy',lambda *a:setattr(self,'alive',False));self.read()
    def manager(self,*args):
        try:launch_provider([['blueman-manager'],['systemsettings','kcm_bluetooth']])
        except (OSError,RuntimeError) as error:self.status.set_text(str(error))
    def read(self,power=None):
        if self.busy:return
        self.busy=True;self.power.set_sensitive(False)
        def worker():
            try:
                if power:command(['bluetoothctl','--timeout','8','power',power])
                details=command(['bluetoothctl','--timeout','8','show']);devices=command(['bluetoothctl','--timeout','8','devices','Paired']);error=None
            except (OSError,RuntimeError,subprocess.TimeoutExpired) as exc:details='';devices='';error=str(exc)
            def done():
                if not self.alive:return False
                self.busy=False;self.power.set_sensitive(not error)
                self.status.set_text(error or '\n'.join(line.strip() for line in details.splitlines() if any(key in line for key in ('Controller ','Name:','Powered:','Discoverable:'))))
                self.power.set_label('Power off' if 'Powered: yes' in details else 'Power on');self.devices.set_text(devices or 'No paired devices');return False
            GLib.idle_add(done)
        threading.Thread(target=worker,daemon=True).start()


def defaults_pane(status):
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
    box.add(Gtk.Label(label='Choose the application used when opening links and files, then press Set.',xalign=0,wrap=True))
    for title,mime in [('Web browser','x-scheme-handler/https'),('Email','x-scheme-handler/mailto'),('File manager','inode/directory'),('Text files','text/plain'),('PDF documents','application/pdf'),('Video','video/mp4'),('Images','image/png')]:
        row=Gtk.Box(spacing=8);row.pack_start(Gtk.Label(label=title,xalign=0),False,False,0)
        chooser=Gtk.AppChooserButton(content_type=mime);chooser.set_show_default_item(True);chooser.set_show_dialog_item(True)
        def changed(widget,mime=mime,chooser=chooser):
            app=chooser.get_app_info()
            if app:
                try:
                    app.set_as_default_for_type(mime)
                    if mime=='x-scheme-handler/https':app.set_as_default_for_type('x-scheme-handler/http')
                    status.set_text('Default application updated')
                except GLib.Error as error:status.set_text(str(error))
        apply=Gtk.Button(label='Set');apply.connect('clicked',changed)
        row.pack_end(apply,False,False,0);row.pack_end(chooser,True,True,0);box.add(row)
    return box
