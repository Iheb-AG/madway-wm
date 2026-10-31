"""Native-session sleep/lid integration. No shell commands or global policy edits."""
import json
import os
import sys
import time

LOGIN='org.freedesktop.login1'
MANAGER='/org/freedesktop/login1'


def lid_decision(policy, closed, external):
    if not closed or policy in ('ignore','system'):return None
    return 'suspend' if policy=='suspend' or (policy=='auto' and not external) else None


class PowerManager:
    def __init__(self, desktop):
        self.desktop=desktop
        self.Gio,self.GLib=desktop.Gio,desktop.GLib
        self.bus=desktop.system_bus
        self.session_path=None
        self.lid_fd=-1
        self.lid_owned=False
        self.last_lid=None
        self.native=False
        self.sleep_requested=False
        self.sleeping=False
        self.request_timer=0
        self.inhibit_retry_at=0
        self.inhibit_error=None
        self.delay_fd=-1;self.delay_retry_at=0;self.delay_error=None
        self.lock_signal=0;self.lock_signal_path=None;self.lock_hint=None;self.closed=False
        if self.bus is not None:
            self.bus.signal_subscribe(LOGIN,LOGIN+'.Manager','PrepareForSleep',MANAGER,None,
                self.Gio.DBusSignalFlags.NONE,self.prepare_sleep)

    def state(self):
        try:return json.loads((self.desktop.directory/'desktop.json').read_text())
        except (OSError,ValueError):return {}

    def active(self):
        if self.bus is None or not self.native:return False
        try:
            if self.session_path is None:
                reply=self.bus.call_sync(LOGIN,MANAGER,LOGIN+'.Manager','GetSessionByPID',
                    self.GLib.Variant('(u)',(self.desktop.parent,)),None,self.Gio.DBusCallFlags.NONE,1000,None)
                self.session_path=reply.unpack()[0]
            reply=self.bus.call_sync(LOGIN,self.session_path,'org.freedesktop.DBus.Properties','Get',
                self.GLib.Variant('(ss)',(LOGIN+'.Session','Active')),None,self.Gio.DBusCallFlags.NONE,1000,None)
            return bool(reply.unpack()[0])
        except self.GLib.Error:
            self.session_path=None
            return False

    def release_lid(self):
        if self.lid_fd>=0:os.close(self.lid_fd);self.lid_fd=-1
        if self.lid_owned:
            self.lid_owned=False;self.last_lid=None
            try:self.desktop.compositor('lid-managed 0')
            except OSError:pass

    def acquire_lid(self):
        if self.lid_fd>=0:return True
        if time.monotonic()<self.inhibit_retry_at:return False
        try:
            reply,fds=self.bus.call_with_unix_fd_list_sync(LOGIN,MANAGER,LOGIN+'.Manager','Inhibit',
                self.GLib.Variant('(ssss)',('handle-lid-switch','madway','Desktop laptop lid policy','block')),
                None,self.Gio.DBusCallFlags.NONE,1000,None,None)
            self.lid_fd=fds.get(reply.unpack()[0])
            self.desktop.compositor('lid-managed 1')
            self.lid_owned=True
            self.inhibit_error=None;self.inhibit_retry_at=0
            return True
        except (self.GLib.Error,OSError) as error:
            self.release_lid()
            self.inhibit_retry_at=time.monotonic()+30
            if self.inhibit_error!=str(error):
                print('madway: lid policy unavailable; systemd-logind retains control: '+str(error),file=sys.stderr)
                self.inhibit_error=str(error)
            return False

    def sync(self):
        state=self.state()
        self.native=bool(state.get('native')) and os.environ.get('MADWAY_NATIVE')=='1'
        active=self.active() if self.native else False
        if active and not self.sleeping and self.desktop.config.getboolean('locking','before_sleep'):self.acquire_delay()
        else:self.release_delay()
        if self.native and self.session_path:
            if self.session_path!=self.lock_signal_path:
                if self.lock_signal:self.bus.signal_unsubscribe(self.lock_signal)
                self.lock_signal_path=self.session_path
                self.lock_signal=self.bus.signal_subscribe(LOGIN,LOGIN+'.Session','Lock',self.session_path,None,
                    self.Gio.DBusSignalFlags.NONE,self.session_lock)
            hint=bool(state.get('locked') and state.get('lock_ready'))
            if hint!=self.lock_hint:
                self.lock_hint=hint
                def hint_done(bus,result):
                    try:bus.call_finish(result)
                    except self.GLib.Error:pass
                self.bus.call(LOGIN,self.session_path,LOGIN+'.Session','SetLockedHint',self.GLib.Variant('(b)',(hint,)),
                    None,self.Gio.DBusCallFlags.NONE,1000,None,hint_done)
        policy=self.desktop.config.get('power','lid_action')
        if policy not in ('auto','suspend','ignore','system'):policy='system'
        if not self.native or not state.get('lid_present') or policy=='system' or not active:
            self.release_lid();return True
        if not self.acquire_lid():return True
        try:
            outputs=json.loads((self.desktop.directory/'outputs.json').read_text()).get('outputs',[])
        except (OSError,ValueError):return True
        external=any(row.get('enabled') and not row.get('name','').startswith(('eDP-','LVDS-','DSI-')) for row in outputs)
        signature=(bool(state.get('lid_closed')),external,policy)
        if signature!=self.last_lid:
            self.last_lid=signature
            if lid_decision(policy,signature[0],external)=='suspend':
                self.request_sleep()
        return True

    def release_delay(self):
        if self.delay_fd>=0:os.close(self.delay_fd);self.delay_fd=-1

    def acquire_delay(self):
        if self.delay_fd>=0:return True
        if time.monotonic()<self.delay_retry_at:return False
        try:
            reply,fds=self.bus.call_with_unix_fd_list_sync(LOGIN,MANAGER,LOGIN+'.Manager','Inhibit',
                self.GLib.Variant('(ssss)',('sleep','madway','Present the session lock before sleeping','delay')),
                None,self.Gio.DBusCallFlags.NONE,1000,None,None)
            self.delay_fd=fds.get(reply.unpack()[0]);self.delay_error=None;return True
        except (self.GLib.Error,OSError) as error:
            self.delay_retry_at=time.monotonic()+30
            if self.delay_error!=str(error):
                print('madway: sleep delay inhibitor unavailable: '+str(error),file=sys.stderr);self.delay_error=str(error)
            return False

    def session_lock(self,*args):
        if self.native and not self.closed:self.desktop.locker.ensure(emergency=True)

    def request_sleep(self):
        self.native=bool(self.state().get('native')) and os.environ.get('MADWAY_NATIVE')=='1'
        if not self.native or not self.active():
            raise RuntimeError('Sleep is available only in the active native madway session')
        if self.sleep_requested or self.sleeping:return
        self.sleep_requested=True
        def expired():
            self.request_timer=0;self.sleep_requested=False;return False
        self.request_timer=self.GLib.timeout_add_seconds(15,expired)
        if self.desktop.config.getboolean('locking','before_sleep'):
            try:self.desktop.locker.ensure(self.locked_for_sleep)
            except Exception:
                self.sleep_requested=False
                if self.request_timer:self.GLib.source_remove(self.request_timer);self.request_timer=0
                raise
        else:self.suspend()

    def locked_for_sleep(self,success):
        if self.closed or not self.sleep_requested:return
        if not success:
            self.sleep_requested=False
            if self.request_timer:self.GLib.source_remove(self.request_timer);self.request_timer=0
            self.desktop.notify('sleep','Sleep cancelled','The screen locker did not become ready.')
            return
        if not self.active():self.sleep_requested=False;return
        self.suspend()

    def suspend(self):
        def done(bus,result):
            try:bus.call_finish(result)
            except self.GLib.Error as error:
                self.sleep_requested=False
                if self.request_timer:self.GLib.source_remove(self.request_timer);self.request_timer=0
                print('madway: system sleep request failed: '+str(error),file=sys.stderr)
                self.desktop.notify('sleep','Sleep request failed',body=str(error))
        self.bus.call(LOGIN,MANAGER,LOGIN+'.Manager','Suspend',self.GLib.Variant('(b)',(True,)),
            None,self.Gio.DBusCallFlags.NONE,15000,None,done)

    def prepare_sleep(self,connection,sender,path,interface,member,parameters):
        starting=parameters.unpack()[0]
        if not self.native or (not self.sleeping and not self.sleep_requested and not self.active()):return
        if starting:
            self.sleeping=True;self.sleep_requested=False
            for name in ('desktop-menu','launcher','switcher'):self.desktop.terminate(name)
            if self.desktop.config.getboolean('locking','before_sleep'):
                self.desktop.locker.ensure(self.prepared_for_sleep,emergency=True)
            else:self.prepared_for_sleep(True)
        else:
            self.sleeping=False;self.sleep_requested=False
            self.desktop.compositor('resume')
            self.desktop.poll_power()
            self.sync()
        if self.request_timer:self.GLib.source_remove(self.request_timer);self.request_timer=0

    def prepared_for_sleep(self,success):
        if self.closed or not self.sleeping:return
        if success:
            self.desktop.compositor('prepare-sleep')
            self.release_delay()
        else:print('madway: lock presentation not confirmed; retaining sleep delay until logind timeout',file=sys.stderr)

    def close(self):
        self.closed=True;self.release_delay()
        if self.lock_signal:self.bus.signal_unsubscribe(self.lock_signal);self.lock_signal=0
        self.release_lid()
        if self.request_timer:self.GLib.source_remove(self.request_timer);self.request_timer=0
