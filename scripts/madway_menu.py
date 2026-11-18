"""Frame-clock menu reveals with stable layout and matching visible input regions."""
import math
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk


def ease(progress):
    """Responsive onset and a quiet settle: cubic-bezier(.2,.8,.2,1)."""
    if progress<=0:return 0.
    if progress>=1:return 1.
    low,high=0.,1.
    for _ in range(20):
        t=(low+high)/2;u=1-t
        if 3*u*u*t*.2+3*u*t*t*.2+t*t*t<progress:low=t
        else:high=t
    t=(low+high)/2;u=1-t
    return 3*u*u*t*.8+3*u*t*t+t*t*t


def reveal_rect(width,height,edge,progress):
    amount=.92+.08*ease(progress)
    horizontal=edge in ('left','right')
    w=max(1,math.ceil(width*amount)) if horizontal else width
    h=height if horizontal else max(1,math.ceil(height*amount))
    return (max(0,width-w) if edge=='right' else 0,
            max(0,height-h) if edge=='bottom' else 0,min(width,w),min(height,h))


class MenuMotion(Gtk.Overlay):
    __gtype_name__='MadwayMenuMotion'
    def __init__(self,edge='top',duration=240,enabled=True,changed=None):
        super().__init__();self.edge=edge;self.duration=min(600,max(80,duration));self.enabled=enabled
        self.changed=changed;self.progress=0. if enabled else 1.;self.tick_id=0;self.started=None;self.frames=0
        self.get_style_context().add_class('menu-motion')
        self.set_opacity(.12 if enabled else 1.)
        self.connect('map',self.start);self.connect('unmap',self.stop);self.connect('destroy',self.stop)
        self.connect_after('size-allocate',lambda *args:self.notify_region())

    def clip_rect(self):return reveal_rect(self.get_allocated_width(),self.get_allocated_height(),self.edge,self.progress)

    def notify_region(self):
        if self.changed:self.changed()

    def do_draw(self,cr):
        cr.save();cr.rectangle(*self.clip_rect());cr.clip()
        result=Gtk.Overlay.do_draw(self,cr);cr.restore();return result

    def start(self,*args):
        self.stop();self.progress=0. if self.enabled else 1.;self.started=None;self.frames=0
        self.set_opacity(.12 if self.enabled else 1.);self.queue_draw();self.notify_region()
        if self.enabled:self.tick_id=self.add_tick_callback(self.frame)

    def frame(self,widget,clock):
        now=clock.get_frame_time()
        if self.started is None:self.started=now
        self.progress=min(1.,max(0.,(now-self.started)/(self.duration*1000)))
        self.frames+=1;self.set_opacity(.12+.88*ease(self.progress));self.queue_draw();self.notify_region()
        if self.progress>=1:self.tick_id=0;return False
        return True

    def finish(self):
        self.stop();self.queue_draw();self.notify_region()

    def stop(self,*args):
        if self.tick_id:self.remove_tick_callback(self.tick_id);self.tick_id=0
        self.started=None;self.progress=1.;self.set_opacity(1.)
