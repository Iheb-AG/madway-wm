"""Session timer/stopwatch state, shared by every panel and its compact popup."""
import json
import math
from pathlib import Path
import time

MAX_DURATION=99*3600+59*60+59


def clock():
    # Countdown and elapsed time include laptop sleep and ignore wall-clock edits.
    return time.clock_gettime(time.CLOCK_BOOTTIME) if hasattr(time,'CLOCK_BOOTTIME') else time.monotonic()


def duration(value):
    if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=MAX_DURATION:
        raise ValueError('Timer duration must be between 1 second and 99:59:59')
    return value


def format_time(seconds):
    seconds=max(0,int(seconds));hours,rest=divmod(seconds,3600);minutes,seconds=divmod(rest,60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'


class TimerState:
    def __init__(self,mode='timer',seconds=300,now=clock):
        self.now=now;self.mode=mode if mode in ('timer','stopwatch') else 'timer'
        self.duration=duration(seconds);self.remaining=float(seconds);self.deadline=None;self.finished=False
        self.elapsed=0.;self.anchor=None

    @classmethod
    def restore(cls,data,now=clock):
        if not isinstance(data,dict) or data.get('version')!=1:raise ValueError('Invalid timer state')
        model=cls(data['mode'],data['duration'],now)
        if data['mode'] not in ('timer','stopwatch'):raise ValueError('Invalid timer mode')
        for key in ('remaining','elapsed','deadline','anchor'):
            value=data[key]
            if key in ('deadline','anchor') and value is None:continue
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError('Invalid timer clock')
            if key in ('deadline','anchor') and value>now()+MAX_DURATION:raise ValueError('Invalid timer clock')
        if data['remaining']>model.duration or not isinstance(data['finished'],bool):raise ValueError('Invalid timer state')
        model.remaining=float(data['remaining']);model.elapsed=float(data['elapsed'])
        model.deadline=data['deadline'];model.anchor=data['anchor'];model.finished=data['finished']
        return model

    def snapshot(self):
        return dict(version=1,mode=self.mode,duration=self.duration,remaining=self.remaining,
                    deadline=self.deadline,finished=self.finished,elapsed=self.elapsed,anchor=self.anchor)

    def view(self):
        if self.mode=='timer':
            seconds=max(0,self.deadline-self.now()) if self.deadline is not None else self.remaining
            phase='running' if self.deadline is not None else 'finished' if self.finished else 'paused' if self.remaining<self.duration else 'idle'
            seconds=math.ceil(seconds)
        else:
            seconds=self.elapsed+(max(0,self.now()-self.anchor) if self.anchor is not None else 0)
            phase='running' if self.anchor is not None else 'paused' if self.elapsed else 'idle'
        return dict(mode=self.mode,phase=phase,seconds=seconds,label=format_time(seconds),duration=self.duration)

    def poll(self):
        if self.deadline is None or self.now()<self.deadline:return False
        self.deadline=None;self.remaining=0.;self.finished=True
        return True

    def control(self,operation,mode=None,seconds=None):
        if mode is not None and mode not in ('timer','stopwatch'):raise ValueError('Invalid timer mode')
        if operation not in ('select','start','pause','reset'):raise ValueError('Invalid timer operation')
        if seconds is not None:duration(seconds)
        completed=self.poll()
        if mode:self.mode=mode
        if operation=='select':return completed
        if self.mode=='timer':
            if operation=='start' and self.deadline is None:
                if self.finished or self.remaining==self.duration:
                    if seconds is not None:self.duration=seconds
                    self.remaining=float(self.duration)
                self.finished=False;self.deadline=self.now()+self.remaining
            elif operation=='pause' and self.deadline is not None:
                self.remaining=max(0,self.deadline-self.now());self.deadline=None
            elif operation=='reset':
                if seconds is not None:self.duration=seconds
                self.remaining=float(self.duration);self.deadline=None;self.finished=False
        else:
            if operation=='start' and self.anchor is None:self.anchor=self.now()
            elif operation=='pause' and self.anchor is not None:
                self.elapsed+=max(0,self.now()-self.anchor);self.anchor=None
            elif operation=='reset':self.elapsed=0.;self.anchor=None
        return completed


def read_state(path,mode='timer',seconds=300,now=clock):
    try:return TimerState.restore(json.loads(Path(path).read_text()),now)
    except (OSError,ValueError,KeyError,TypeError):return TimerState(mode,seconds,now)


class TimerController:
    def __init__(self,desktop):
        self.desktop=desktop;self.path=desktop.directory/'timer.json';self.watch=0
        try:seconds=duration(desktop.config.getint('timer','duration'))
        except ValueError:seconds=300
        self.model=read_state(self.path,desktop.config.get('timer','mode'),seconds)
        self.publish();self.schedule()

    def publish(self):
        temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.model.snapshot()))
        temporary.chmod(0o600);temporary.replace(self.path)

    def schedule(self):
        if self.watch:self.desktop.GLib.source_remove(self.watch);self.watch=0
        if self.model.deadline is not None:self.watch=self.desktop.GLib.timeout_add(100,self.tick)

    def tick(self):
        if not self.model.poll():return True
        self.watch=0;self.publish()
        self.desktop.notify('timer','Timer finished',format_time(self.model.duration)+' elapsed',timeout=5000)
        return False

    def control(self,message):
        previous_duration=self.model.duration
        completed=self.model.control(message.get('operation'),message.get('mode'),message.get('seconds'))
        self.publish();self.schedule()
        if completed:self.desktop.notify('timer','Timer finished',format_time(previous_duration)+' elapsed',timeout=5000)
        return dict(mode=self.model.mode,duration=str(self.model.duration))

    def close(self):
        if self.watch:self.desktop.GLib.source_remove(self.watch);self.watch=0
        self.path.unlink(missing_ok=True)
