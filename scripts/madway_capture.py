"""Microphone routing and explicit, memory-only capture tests for Settings."""
import array
import fcntl
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GdkPixbuf','2.0')
from gi.repository import Gtk,GLib,GdkPixbuf


def command(argv):
    result=subprocess.run(argv,capture_output=True,text=True,timeout=6,env={**os.environ,'LC_ALL':'C'})
    if result.returncode:raise RuntimeError(result.stderr.strip() or 'Audio service unavailable')
    return result.stdout


def microphone_snapshot(run=command):
    info=json.loads(run(['pactl','--format=json','info']))
    sources=json.loads(run(['pactl','--format=json','list','sources']))
    streams=json.loads(run(['pactl','--format=json','list','source-outputs']))
    cards=json.loads(run(['pactl','--format=json','list','cards']))
    sources=[row for row in sources if row.get('monitor_of_sink') in (None,4294967295,'4294967295') and not row.get('name','').endswith('.monitor')]
    return dict(default=info.get('default_source_name'),sources=sources,streams=streams,cards=cards)


def capture_control(operation,identity,value=None,run=command):
    identity=str(int(identity))
    if int(identity)<0:raise ValueError('Invalid device')
    if operation=='default':argv=['set-default-source',identity]
    elif operation=='mute':argv=['set-source-mute',identity,'1' if value else '0']
    elif operation=='volume':argv=['set-source-volume',identity,str(max(0,min(100,int(value))))+'%']
    elif operation=='route':
        target=int(value)
        if target<0:raise ValueError('Invalid input device')
        argv=['move-source-output',identity,str(target)]
    elif operation in ('port','profile'):
        if not isinstance(value,str) or not value or len(value)>256 or any(ord(c)<32 for c in value):raise ValueError('Invalid device option')
        argv=['set-source-port' if operation=='port' else 'set-card-profile',identity,value]
    else:raise ValueError('Invalid capture operation')
    run(['pactl',*argv])


def playback_snapshot(run=command):
    info=json.loads(run(['pactl','--format=json','info']))
    return dict(default=info.get('default_sink_name'),
        sinks=[row for row in json.loads(run(['pactl','--format=json','list','sinks']))
               if not row.get('name','').startswith('madway_exit_')],
        streams=json.loads(run(['pactl','--format=json','list','sink-inputs'])))


def playback_control(operation,identity,value=None,run=command):
    identity=str(int(identity))
    if int(identity)<0:raise ValueError('Invalid output')
    if operation=='default':
        run(['pactl','set-default-sink',identity])
        # A default change alone can leave an existing browser on its old HDMI
        # route. This explicit "Use output" action also moves current playback.
        for row in json.loads(run(['pactl','--format=json','list','sink-inputs'])):
            try:run(['pactl','move-sink-input',str(int(row['index'])),identity])
            except RuntimeError:pass # Applications may close between snapshots.
        return
    if operation=='route':
        target=int(value)
        if target<0:raise ValueError('Invalid output route')
        argv=['move-sink-input',identity,str(target)]
    elif operation=='mute':argv=['set-sink-input-mute',identity,'1' if value else '0']
    elif operation=='port' and isinstance(value,str) and value and len(value)<256 and not any(ord(c)<32 for c in value):
        argv=['set-sink-port',identity,value]
    else:raise ValueError('Invalid playback operation')
    run(['pactl',*argv])


def camera_snapshot(root=Path('/sys/class/video4linux'),dev=Path('/dev')):
    rows=[]
    if not root.exists():return rows
    for entry in sorted(root.glob('video*')):
        path=dev/entry.name
        row=dict(path=str(path),name=entry.name,usable=False,error='')
        try:
            row['name']=(entry/'name').read_text().strip()
            fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
            try:
                data=bytearray(104);fcntl.ioctl(fd,0x80685600,data,True) # VIDIOC_QUERYCAP
                capabilities,device_caps=struct.unpack_from('II',data,84)
                caps=device_caps if capabilities&0x80000000 else capabilities
                if not caps&0x1001:continue # Video capture (single/multiplanar), not metadata nodes.
                row['usable']=True
            finally:os.close(fd)
        except OSError as error:row['error']=str(error)
        rows.append(row)
    return rows


class CapturePane(Gtk.Box):
    __gtype_name__='MadwayCapturePane'
    def __init__(self,directory):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.directory=directory;self.alive=True;self.generation=0;self.process=None;self.pipeline=None;self.testing=False;self.busy=False
        self.status=Gtk.Label(xalign=0,wrap=True,max_width_chars=48);self.pack_start(self.status,False,False,0)
        self.connect('destroy',self.destroyed)
        self.privacy_timer=GLib.timeout_add(250,self.privacy)

    def destroyed(self,*args):
        self.alive=False;self.stop()
        if self.privacy_timer:GLib.source_remove(self.privacy_timer);self.privacy_timer=0

    def privacy(self):
        if not self.alive:return False
        if self.testing:
            try:state=json.loads((self.directory()/'desktop.json').read_text())
            except (OSError,ValueError):state={}
            if state.get('locked') or state.get('sleeping'):self.stop()
        return True

    def stop(self):
        self.generation+=1;self.testing=False
        process=self.process;self.process=None
        if process and process.poll() is None:
            process.terminate()
            def reap():
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            threading.Thread(target=reap,daemon=True).start()
        if self.pipeline:
            self.pipeline.set_state(self.Gst.State.NULL);self.pipeline=None
        if hasattr(self,'test'):self.test.set_label('Test microphone' if hasattr(self,'meter') else 'Start preview')
        if hasattr(self,'meter'):self.meter.set_value(0)
        if hasattr(self,'image'):self.image.clear()

    def async_call(self,work,done):
        if self.busy:return
        self.busy=True
        def worker():
            try:result=work();error=None
            except Exception as failure:result=None;error=str(failure)
            def finish():
                self.busy=False
                if self.alive:done(result,error)
                return False
            GLib.idle_add(finish)
        threading.Thread(target=worker,daemon=True).start()


class PlaybackPane(CapturePane):
    __gtype_name__='MadwayPlaybackPane'
    def __init__(self,directory):
        super().__init__(directory);self.sinks=[];self.updating=False
        self.choice=Gtk.ComboBoxText();self.choice.connect('changed',lambda w:self.select())
        self.pack_start(self.choice,False,False,0)
        self.port=Gtk.ComboBoxText();self.port.connect('changed',lambda w:None if self.updating else self.control('port',w.get_active_id()))
        self.pack_start(self.port,False,False,0)
        toolbar=Gtk.Box(spacing=5);self.pack_start(toolbar,False,False,0)
        self.use=Gtk.Button(label='Use output');self.use.connect('clicked',lambda w:self.control('default'));toolbar.pack_start(self.use,False,False,0)
        self.test=Gtk.Button(label='Test speakers');self.test.connect('clicked',self.test_speakers);toolbar.pack_start(self.test,False,False,0)
        refresh=Gtk.Button(label='Refresh');refresh.connect('clicked',lambda w:self.refresh());toolbar.pack_end(refresh,False,False,0)
        self.apps=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);self.pack_start(self.apps,False,False,0)
        self.refresh()

    def stop(self):
        super().stop()
        if hasattr(self,'test'):self.test.set_label('Test speakers')

    def selected(self):return next((row for row in self.sinks if str(row['index'])==self.choice.get_active_id()),None)

    def refresh(self):self.async_call(playback_snapshot,self.loaded)

    def loaded(self,state,error):
        if error:self.status.set_text('Cannot reach the audio server: '+error);return
        previous=self.choice.get_active_id();self.sinks=state['sinks'];self.updating=True;self.choice.remove_all()
        for row in self.sinks:self.choice.append(str(row['index']),row.get('description',row['name']))
        default=next((str(row['index']) for row in self.sinks if row['name']==state['default']),None)
        self.choice.set_active_id(previous if any(str(row['index'])==previous for row in self.sinks) else default or (str(self.sinks[0]['index']) if self.sinks else ''))
        self.updating=False;self.select()
        for child in self.apps.get_children():child.destroy()
        self.apps.add(Gtk.Label(label='Playing applications',xalign=0))
        if not state['streams']:self.apps.add(Gtk.Label(label='Play a video or song, then refresh to check its mute and output.',xalign=0,wrap=True,max_width_chars=46))
        for stream in state['streams']:
            line=Gtk.Box(spacing=5);props=stream.get('properties',{})
            label=Gtk.Label(label=props.get('application.name','Application'),xalign=0)
            label.set_ellipsize(3);label.set_max_width_chars(16);label.set_width_chars(1)
            line.pack_start(label,True,True,0)
            mute=Gtk.Button(label='Unmute' if stream.get('mute') else 'Mute')
            mute.connect('clicked',lambda w,row=stream:self.control('mute',not row.get('mute'),row['index']))
            line.pack_start(mute,False,False,0)
            route=Gtk.ComboBoxText()
            for sink in self.sinks:route.append(str(sink['index']),sink.get('description',sink['name']))
            route.set_active_id(str(stream.get('sink','')));route.set_hexpand(True)
            route.connect('changed',lambda w,identity=stream['index']:self.control('route',w.get_active_id(),identity))
            line.pack_start(route,True,True,0);self.apps.add(line)
        for combo in [self.choice,self.port,*[w for line in self.apps.get_children() if isinstance(line,Gtk.Box) for w in line.get_children() if isinstance(w,Gtk.ComboBoxText)]]:
            for renderer in combo.get_cells():
                if isinstance(renderer,Gtk.CellRendererText):renderer.set_property('ellipsize',3);renderer.set_property('max-width-chars',24)
        self.apps.show_all()

    def select(self):
        if self.updating:return
        self.stop();sink=self.selected();self.updating=True;self.port.remove_all()
        self.use.set_sensitive(bool(sink));self.test.set_sensitive(bool(sink))
        if sink:
            for port in sink.get('ports',[]):
                unavailable=port.get('availability') in ('no','not available')
                self.port.append(port['name'],port.get('description',port['name'])+(' (unplugged)' if unavailable else ''))
            self.port.set_active_id(sink.get('active_port'))
            levels=[float(v['value_percent'].rstrip('%')) for v in sink.get('volume',{}).values()]
            text='Selected output: '+sink.get('description',sink['name'])
            if sink.get('mute'):text+=' · muted at device level'
            elif levels and max(levels)==0:text+=' · volume is zero'
            self.status.set_text(text)
        else:self.status.set_text('No playback output available. Check the audio services and sound-card profile.')
        self.port.set_sensitive(bool(sink and sink.get('ports')));self.updating=False

    def control(self,operation,value=None,identity=None):
        if self.busy:return
        sink=self.selected()
        if identity is None:
            if not sink:return
            identity=sink['index']
        self.stop()
        def done(result,error):
            if error:self.status.set_text(error)
            else:self.refresh()
        self.async_call(lambda:playback_control(operation,identity,value),done)

    def test_speakers(self,*args):
        if self.testing:self.stop();return
        sink=self.selected()
        if not sink:return
        sample=next((path for path in (Path('/usr/share/sounds/alsa/Front_Center.wav'),
            Path('/usr/share/sounds/freedesktop/stereo/audio-test-signal.oga')) if path.is_file()),None)
        if not sample:self.status.set_text('No system speaker-test sample installed. Install alsa-utils, then try again.');return
        self.stop();generation=self.generation;self.testing=True;self.test.set_label('Stop test')
        try:
            self.process=subprocess.Popen(['pw-play','--target',sink['name'],'--volume','0.5',str(sample)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        except OSError as error:self.stop();self.status.set_text(str(error));return
        process=self.process
        def worker():
            try:
                _,err=process.communicate(timeout=8)
                error=err.decode(errors='replace').strip() if process.returncode else ''
            except subprocess.TimeoutExpired:process.kill();process.communicate();error='Speaker test timed out.'
            def finish():
                if self.alive and generation==self.generation:
                    self.stop();self.status.set_text(error or 'Test finished. If you heard it, check the application mute and output route below.')
                return False
            GLib.idle_add(finish)
        threading.Thread(target=worker,daemon=True).start()


class MicrophonePane(CapturePane):
    __gtype_name__='MadwayMicrophonePane'
    def __init__(self,directory):
        super().__init__(directory);self.sources=[];self.updating=False
        toolbar=Gtk.Box(spacing=5);self.pack_start(toolbar,False,False,0)
        refresh=Gtk.Button(label='Refresh devices');refresh.connect('clicked',lambda w:self.refresh());toolbar.add(refresh)
        self.choice=Gtk.ComboBoxText();self.choice.connect('changed',lambda w:self.select());self.pack_start(self.choice,False,False,0)
        self.details=Gtk.Label(xalign=0,wrap=True,max_width_chars=48);self.pack_start(self.details,False,False,0)
        line=Gtk.Box(spacing=5);self.pack_start(line,False,False,0)
        self.default=Gtk.Button(label='Use for meetings');self.default.connect('clicked',lambda w:self.control('default'));line.pack_start(self.default,True,True,0)
        self.mute=Gtk.CheckButton(label='Mute input');self.mute.connect('toggled',lambda w:None if self.updating else self.control('mute',w.get_active()));line.add(self.mute)
        self.volume=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1);self.volume.set_value_pos(Gtk.PositionType.RIGHT)
        self.volume.connect('button-release-event',lambda w,e:self.control('volume',round(w.get_value())))
        self.volume.connect('key-release-event',lambda w,e:self.control('volume',round(w.get_value())))
        self.pack_start(Gtk.Label(label='Input level (%)',xalign=0),False,False,0);self.pack_start(self.volume,False,False,0)
        self.port=Gtk.ComboBoxText();self.port.connect('changed',lambda w:None if self.updating else self.control('port',w.get_active_id()))
        self.pack_start(Gtk.Label(label='Microphone port',xalign=0),False,False,0);self.pack_start(self.port,False,False,0)
        self.test=Gtk.Button(label='Test microphone');self.test.connect('clicked',self.toggle_test)
        self.pack_start(self.test,False,False,0);self.meter=Gtk.LevelBar();self.pack_start(self.meter,False,False,0)
        self.stream_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);self.pack_start(self.stream_box,False,False,0)
        self.profile_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);self.pack_start(self.profile_box,False,False,0)
        note=Gtk.Label(label='Changes take effect immediately. Allow microphone access in your browser and choose this input in the meeting. Refresh while the meeting is recording to reroute an existing stream. The test meter keeps no recording.',xalign=0,wrap=True,max_width_chars=48)
        self.pack_start(note,False,False,0);self.refresh()

    def selected(self):return next((row for row in self.sources if str(row['index'])==self.choice.get_active_id()),None)

    def refresh(self):
        self.async_call(microphone_snapshot,self.loaded)
        return False

    def loaded(self,state,error):
        if error:self.status.set_text('Cannot reach the audio server: '+error+'\nCheck that PipeWire, pipewire-pulse and WirePlumber are running.');return
        previous=self.choice.get_active_id();self.sources=state['sources'];self.updating=True;self.choice.remove_all()
        for row in self.sources:self.choice.append(str(row['index']),row.get('description') or row['name'])
        default=next((str(row['index']) for row in self.sources if row['name']==state['default']),None)
        self.choice.set_active_id(previous if any(str(row['index'])==previous for row in self.sources) else default or (str(self.sources[0]['index']) if self.sources else ''))
        self.updating=False;self.select();self.status.set_text('Default input: '+next((row.get('description',row['name']) for row in self.sources if row['name']==state['default']),'None') if self.sources else 'No microphone input is exposed. Check the sound-card profile below; an output-only profile disables recording.')
        for box in (self.stream_box,self.profile_box):
            for child in box.get_children():child.destroy()
        self.stream_box.add(Gtk.Label(label='Applications currently recording',xalign=0))
        if not state['streams']:self.stream_box.add(Gtk.Label(label='No active recording streams',xalign=0))
        for stream in state['streams']:
            line=Gtk.Box(spacing=5);label=Gtk.Label(label=stream.get('properties',{}).get('application.name','Recording application'),xalign=0)
            label.set_ellipsize(3);label.set_max_width_chars(18);line.pack_start(label,True,True,0)
            choice=Gtk.ComboBoxText()
            for source in self.sources:choice.append(str(source['index']),source.get('description') or source['name'])
            choice.set_active_id(str(stream.get('source','')))
            choice.connect('changed',lambda w,identity=stream['index']:self.control('route',w.get_active_id(),identity))
            line.pack_start(choice,True,True,0);self.stream_box.add(line)
        self.profile_box.add(Gtk.Label(label='Sound-card profile · choose a duplex/input profile to enable a missing mic',xalign=0,wrap=True,max_width_chars=48))
        for card in state['cards']:
            profiles=card.get('profiles',{})
            if not isinstance(profiles,dict):continue
            label=Gtk.Label(label=card.get('properties',{}).get('device.description',card.get('name','Sound card')),xalign=0,wrap=True,max_width_chars=48)
            self.profile_box.add(label);line=Gtk.Box(spacing=5);choice=Gtk.ComboBoxText()
            for name,profile in profiles.items():
                if profile.get('available') not in ('no','not available'):choice.append(name,profile.get('description',name))
            choice.set_active_id(card.get('active_profile'));line.pack_start(choice,True,True,0)
            button=Gtk.Button(label='Set profile');button.connect('clicked',lambda w,c=choice,i=card['index']:self.control('profile',c.get_active_id(),i));line.add(button);self.profile_box.add(line)
        for widget in self.get_children():widget.show_all()
        for combo in [self.choice,self.port,*[w for box in (self.stream_box,self.profile_box) for line in box.get_children() if isinstance(line,Gtk.Box) for w in line.get_children() if isinstance(w,Gtk.ComboBoxText)]]:
            for renderer in combo.get_cells():
                if isinstance(renderer,Gtk.CellRendererText):renderer.set_property('ellipsize',3);renderer.set_property('max-width-chars',22)

    def select(self):
        if self.updating:return
        self.stop();source=self.selected();self.updating=True
        for widget in (self.default,self.mute,self.volume,self.test):widget.set_sensitive(bool(source))
        self.port.remove_all()
        if source:
            levels=[float(level['value_percent'].rstrip('%')) for level in source.get('volume',{}).values()]
            self.volume.set_value(sum(levels)/len(levels) if levels else 0);self.mute.set_active(bool(source.get('mute')))
            self.details.set_text(source.get('name','')+' · '+source.get('state','Unknown'))
            for port in source.get('ports',[]):
                available=port.get('availability',port.get('available','unknown'))
                self.port.append(port['name'],port.get('description',port['name'])+(' (unplugged)' if available in ('no','not available') else ''))
            self.port.set_active_id(source.get('active_port'))
        else:self.details.set_text('No input selected')
        self.port.set_sensitive(bool(source and source.get('ports')));self.updating=False

    def control(self,operation,value=None,identity=None):
        if self.busy:return False
        source=self.selected()
        if identity is None:
            if not source:return False
            identity=source['index']
        self.stop()
        def done(result,error):
            if error:self.status.set_text(error)
            else:self.refresh()
        self.async_call(lambda:capture_control(operation,identity,value),done)
        return False

    def toggle_test(self,*args):
        if self.testing:self.stop();return
        source=self.selected()
        if not source:return
        if not shutil.which('parec'):self.status.set_text('Install libpulse / pulseaudio-utils for the microphone meter (parec).');return
        self.stop();generation=self.generation;self.testing=True;self.test.set_label('Stop microphone test');self.status.set_text('Listening to '+source.get('description',source['name'])+' · no audio is saved')
        try:self.process=subprocess.Popen(['parec','--raw','--format=s16le','--rate=16000','--channels=1','--latency-msec=50','--device='+source['name']],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        except OSError as error:self.stop();self.status.set_text(str(error));return
        process=self.process
        def update(level,error=None):
            if not self.alive or generation!=self.generation:return False
            if error:self.stop();self.status.set_text(error)
            else:self.meter.set_value(level)
            return False
        def worker():
            while generation==self.generation:
                data=process.stdout.read(1024)
                if not data:break
                samples=array.array('h');samples.frombytes(data[:len(data)//2*2])
                rms=math.sqrt(sum(float(sample)*sample for sample in samples)/max(1,len(samples)))/32768
                level=max(0,min(1,(20*math.log10(max(1e-6,rms))+60)/60))
                GLib.idle_add(update,level)
            if generation==self.generation:GLib.idle_add(update,0,'Microphone capture stopped. Check the device, hardware mute key and input permissions.')
            process.stdout.close();process.stderr.close()
        threading.Thread(target=worker,daemon=True).start()


class CameraPane(CapturePane):
    __gtype_name__='MadwayCameraPane'
    def __init__(self,directory):
        super().__init__(directory);self.cameras=[]
        refresh=Gtk.Button(label='Refresh cameras');refresh.connect('clicked',lambda w:self.refresh());self.pack_start(refresh,False,False,0)
        self.choice=Gtk.ComboBoxText();self.choice.connect('changed',lambda w:self.stop());self.pack_start(self.choice,False,False,0)
        self.test=Gtk.Button(label='Start preview');self.test.connect('clicked',self.toggle_test);self.pack_start(self.test,False,False,0)
        self.image=Gtk.Image();self.image.set_size_request(240,180);self.pack_start(self.image,False,False,0)
        self.pack_start(Gtk.Label(label='Preview uses the selected camera locally and saves nothing. Stop it before joining a meeting. In Brave, allow camera and microphone access for the meeting site and choose the devices in its settings. Check any physical camera shutter or privacy key.',xalign=0,wrap=True,max_width_chars=48),False,False,0)
        self.refresh()

    def refresh(self):self.stop();self.async_call(camera_snapshot,self.loaded)

    def loaded(self,rows,error):
        self.choice.remove_all();self.cameras=rows or []
        for row in self.cameras:self.choice.append(row['path'],row['name']+' · '+row['path'])
        self.choice.set_active(0);self.test.set_sensitive(any(row['usable'] for row in self.cameras))
        self.status.set_text(error or ('\n'.join(row['error'] for row in self.cameras if row['error']) or (str(len(rows))+' camera device(s) found' if rows else 'No camera detected. Check the privacy switch and reconnect USB cameras.')))
        for renderer in self.choice.get_cells():
            if isinstance(renderer,Gtk.CellRendererText):renderer.set_property('ellipsize',3);renderer.set_property('max-width-chars',35)

    def toggle_test(self,*args):
        if self.testing:self.stop();return
        path=self.choice.get_active_id()
        if not path:return
        try:
            gi.require_version('Gst','1.0');gi.require_version('GstVideo','1.0')
            from gi.repository import Gst,GstVideo
            self.Gst=Gst;Gst.init(None)
            self.pipeline=self.make_pipeline(path)
            generation=self.generation
            def sample(sink):
                sample=sink.emit('pull-sample')
                if not sample:return Gst.FlowReturn.ERROR
                buffer=sample.get_buffer();ok,mapping=buffer.map(Gst.MapFlags.READ)
                if not ok:return Gst.FlowReturn.ERROR
                try:
                    info=GstVideo.VideoInfo.new_from_caps(sample.get_caps())
                    data=GLib.Bytes.new(bytes(mapping.data));stride=info.stride[0]
                    GLib.idle_add(self.show_frame,generation,data,info.width,info.height,stride)
                finally:buffer.unmap(mapping)
                return Gst.FlowReturn.OK
            self.pipeline.get_by_name('preview').connect('new-sample',sample)
            self.pipeline.set_state(Gst.State.PLAYING);self.testing=True;self.test.set_label('Stop preview');self.status.set_text('Camera preview · no video is saved')
            GLib.timeout_add(100,self.poll_camera,generation)
        except (ImportError,ValueError,GLib.Error) as error:
            self.stop();self.status.set_text('Camera preview requires GStreamer, gst-plugins-base/good and their Python introspection bindings. '+str(error))

    def show_frame(self,generation,data,width,height,stride):
        if self.alive and self.testing and generation==self.generation:self.image.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_bytes(data,GdkPixbuf.Colorspace.RGB,False,8,width,height,stride))
        return False

    def poll_camera(self,generation):
        if not self.alive or not self.testing or generation!=self.generation:return False
        message=self.pipeline.get_bus().pop_filtered(self.Gst.MessageType.ERROR|self.Gst.MessageType.EOS)
        if message:
            error=message.parse_error()[0].message if message.type==self.Gst.MessageType.ERROR else 'Camera stream ended'
            self.stop();self.status.set_text(error);return False
        return True

    def make_pipeline(self,path):
        pipeline=self.Gst.parse_launch('v4l2src name=camera ! videoconvert ! videoscale ! video/x-raw,format=RGB,width=320,height=240 ! appsink name=preview emit-signals=true max-buffers=1 drop=true sync=false')
        pipeline.get_by_name('camera').set_property('device',path)
        return pipeline
