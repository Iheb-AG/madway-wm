"""Serialize hardware changes outside the GTK loop and confirm optimistic feedback."""
import queue
import threading


class MediaController:
    def __init__(self,desktop,api):
        self.desktop=desktop;self.api=api;self.values={};self.serial={'volume':0,'brightness':0};self.closed=False
        self.pending=queue.Queue();self.worker=threading.Thread(target=self.work,daemon=True);self.worker.start()

    def feedback(self,kind,value,muted=False,previous=None,pending=False):
        title='Volume muted' if kind=='volume' and muted else f'Volume {value}%' if kind=='volume' else f'Brightness {value}%'
        self.desktop.notify(kind,title,value=value,previous=previous,pending=pending)

    def request(self,name,message):
        kind='volume' if 'volume' in name else 'brightness';self.serial[kind]+=1;serial=self.serial[kind]
        cached=self.values.get(kind);previous=None
        step=min(20,max(1,self.desktop.config.getint('controls','volume_step' if kind=='volume' else 'brightness_step')))
        if cached:
            value,muted=cached;previous=value
            if name=='volume-mute':muted=not muted
            elif name.startswith('set-'):value=int(message['value'])
            else:value+=step*(1 if name.endswith('-up') else -1)
            value=min(100,max(0 if kind=='volume' else 1,value));self.values[kind]=(value,muted)
            self.feedback(kind,value,muted,previous)
        else:self.feedback(kind,0,pending=True)
        self.pending.put((kind,serial,name,dict(message),step))

    def complete(self,kind,serial,result=None,error=None):
        if self.closed or serial!=self.serial[kind]:return False
        if error:
            self.values.pop(kind,None)
            self.desktop.notify('error','Media control unavailable',str(error));return False
        if result is not None:
            previous=self.values.get(kind,(result[0],False))[0];self.values[kind]=result
            if serial:self.feedback(kind,*result,previous=previous)
        return False

    def read(self,kind):
        if kind=='volume':return self.api['volume']()
        value=self.api['brightness']()
        if value is None:return None
        return value,False

    def work(self):
        for kind in ('volume','brightness'):
            if self.closed:return
            try:self.desktop.GLib.idle_add(self.complete,kind,0,self.read(kind))
            except Exception:pass
        while not self.closed:
            item=self.pending.get()
            if item is None or self.closed:return
            kind,serial,name,message,step=item
            try:
                if kind=='volume':
                    if name=='volume-mute':self.api['run'](['wpctl','set-mute','@DEFAULT_AUDIO_SINK@','toggle'])
                    elif name=='set-volume':self.api['run'](['wpctl','set-volume','--limit','1.0','@DEFAULT_AUDIO_SINK@',str(min(100,max(0,int(message['value']))))+'%'])
                    else:self.api['run'](['wpctl','set-volume','--limit','1.0','@DEFAULT_AUDIO_SINK@',str(step)+'%'+('+' if name.endswith('-up') else '-')])
                else:
                    current=self.api['brightness']()
                    if current is None:raise RuntimeError('No backlight device available')
                    value=int(message['value']) if name=='set-brightness' else current+step*(1 if name.endswith('-up') else -1)
                    self.api['set_brightness'](value)
                result=self.read(kind)
                self.desktop.GLib.idle_add(self.complete,kind,serial,result)
            except Exception as error:self.desktop.GLib.idle_add(self.complete,kind,serial,None,error)

    def close(self):
        self.closed=True;self.pending.put(None)
