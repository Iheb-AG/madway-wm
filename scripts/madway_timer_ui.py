"""Compact in-panel timer controls; the desktop helper owns the running clocks."""
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
from pathlib import Path
import runpy
timer=runpy.run_path(str(Path(__file__).with_name('madway_timer.py')))
read_state,clock=timer['read_state'],timer['clock']


class TimerPane(Gtk.Box):
    def __init__(self,path,send):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=7)
        self.path=path;self.send=send;self.syncing=False;self.pending=None;self.preference=None;self.error=''
        self.get_style_context().add_class('timer-popup')
        self.choice=Gtk.ComboBoxText();self.choice.append('timer','Timer');self.choice.append('stopwatch','Stopwatch')
        self.choice.connect('changed',self.choose);self.pack_start(self.choice,False,False,0)
        self.readout=Gtk.Label();self.readout.get_style_context().add_class('timer-value');self.pack_start(self.readout,False,False,0)
        self.status=Gtk.Label();self.status.get_style_context().add_class('timer-status');self.pack_start(self.status,False,False,0)
        self.duration_box=Gtk.Box(spacing=4);self.pack_start(self.duration_box,False,False,0)
        self.fields=[]
        for caption,maximum in [('h',99),('m',59),('s',59)]:
            field=Gtk.SpinButton.new_with_range(0,maximum,1);field.set_numeric(True);field.set_width_chars(2)
            field.set_tooltip_text({'h':'Hours','m':'Minutes','s':'Seconds'}[caption])
            field.connect('value-changed',lambda w:setattr(self,'error',''))
            self.duration_box.pack_start(field,True,True,0);self.fields.append(field)
            self.duration_box.pack_start(Gtk.Label(label=caption),False,False,0)
        self.duration_box.show_all();self.duration_box.set_no_show_all(True)
        buttons=Gtk.Box(spacing=5);self.pack_start(buttons,False,False,0)
        self.primary=Gtk.Button(label='Start');self.primary.connect('clicked',self.toggle)
        self.reset=Gtk.Button(label='Reset');self.reset.connect('clicked',lambda w:self.command('reset'))
        buttons.pack_start(self.primary,True,True,0);buttons.pack_start(self.reset,True,True,0)
        self.refresh();self.watcher=GLib.timeout_add(100,self.refresh);self.connect('destroy',self.close)

    def seconds(self):
        for widget in self.fields:widget.update()
        return sum(w.get_value_as_int()*factor for w,factor in zip(self.fields,(3600,60,1)))

    def choose(self,widget):
        if self.syncing:return
        self.pending=(widget.get_active_id(),clock());self.send('timer-control',operation='select',mode=self.pending[0]);self.refresh()

    def command(self,operation):
        self.error=''
        mode=self.choice.get_active_id();values=dict(operation=operation,mode=mode)
        if mode=='timer' and operation in ('start','reset') and self.duration_box.get_sensitive():
            seconds=self.seconds()
            if not seconds:self.error='Choose a duration greater than zero.';self.status.set_text(self.error);return
            values['seconds']=seconds
        self.send('timer-control',**values)

    def toggle(self,widget):
        model=read_state(self.path)
        model.mode=self.choice.get_active_id()
        self.command('pause' if model.view()['phase']=='running' else 'start')

    def refresh(self):
        model=read_state(self.path)
        if self.pending:
            if self.pending[0]==model.mode or clock()-self.pending[1]>1:self.pending=None
            else:model.mode=self.pending[0]
        view=model.view();self.syncing=True;self.choice.set_active_id(model.mode);self.syncing=False
        self.readout.set_text(view['label'])
        self.status.set_text(self.error or {'idle':'Ready','running':'Running','paused':'Paused','finished':'Time is up'}[view['phase']])
        self.primary.set_label({'idle':'Start','running':'Pause','paused':'Resume','finished':'Start again'}[view['phase']])
        self.duration_box.set_visible(model.mode=='timer')
        self.duration_box.set_sensitive(view['phase'] in ('idle','finished'))
        if self.preference!=model.duration:
            self.preference=model.duration
            for widget,value in zip(self.fields,(model.duration//3600,model.duration//60%60,model.duration%60)):widget.set_value(value)
        return True

    def close(self,*args):
        if self.watcher:GLib.source_remove(self.watcher);self.watcher=0
