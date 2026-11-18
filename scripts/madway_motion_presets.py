"""Window motion presets and draft editor binding, independent of app identity."""
OPENING={
 'soft':('Soft zoom',dict(open_style='zoom',open_curve='gentle',open_ms='320',open_scale='94',open_distance='10',open_fade='true')),
 'fade':('Fade',dict(open_style='fade',open_curve='responsive',open_ms='220',open_scale='100',open_distance='0',open_fade='true')),
 'rise':('Rise',dict(open_style='rise',open_curve='gentle',open_ms='340',open_scale='100',open_distance='28',open_fade='true')),
 'slide':('Slide',dict(open_style='slide',open_curve='responsive',open_ms='320',open_scale='100',open_distance='32',open_fade='true')),
 'spring':('Spring pop',dict(open_style='zoom',open_curve='spring',open_ms='440',open_scale='86',open_distance='0',open_fade='true')),
}
MAXIMIZE={
 'smooth':('Smooth zoom',dict(maximize_style='zoom',maximize_curve='gentle',maximize_ms='360')),
 'responsive':('Responsive zoom',dict(maximize_style='zoom',maximize_curve='responsive',maximize_ms='240')),
 'spring':('Gentle spring',dict(maximize_style='zoom',maximize_curve='spring',maximize_ms='440')),
 'dissolve':('Dissolve',dict(maximize_style='dissolve',maximize_curve='responsive',maximize_ms='260')),
 'instant':('Instant',dict(maximize_style='none',maximize_curve='gentle',maximize_ms='360')),
}
CURVES=[('gentle','Gentle'),('responsive','Responsive'),('spring','Gentle spring'),('linear','Linear')]


def normalize(config,stored):
    values=config['windows']
    if not stored.has_option('windows','open_animate'):values['open_animate']=values['animate']
    for key,catalog,fallback in [('open_preset',OPENING,'soft'),('maximize_preset',MAXIMIZE,'smooth')]:
        name=values.get(key,fallback)
        if name not in (*catalog,'custom'):name=fallback
        values[key]=name
        for field,value in catalog.get(name,catalog[fallback])[1].items():
            if not stored.has_option('windows',field):values[field]=value
        if key=='maximize_preset' and not stored.has_option('windows','maximize_preset') and not stored.has_option('windows','maximize_ms'):
            values['maximize_ms']=values['animation_ms']
        if name!='custom' and any(values.get(field)!=value for field,value in catalog[name][1].items()):values[key]='custom'


def bind(preset,catalog,controls,enabled,update):
    """Selecting a profile sets draft controls; editing a control selects Custom."""
    applying=False
    def choose(*args):
        nonlocal applying
        name=preset.get_active_id()
        if name not in catalog:return
        applying=True
        try:
            for key,value in catalog[name][1].items():
                widget=controls[key]
                if hasattr(widget,'set_active_id'):widget.set_active_id(value)
                elif hasattr(widget,'set_value'):widget.set_value(int(value))
                else:widget.set_active(value=='true')
        finally:applying=False
        update()
    def edit(*args):
        if not applying:preset.set_active_id('custom');update()
    preset.connect('changed',choose)
    for widget in controls.values():
        signal='changed' if hasattr(widget,'set_active_id') else 'value-changed' if hasattr(widget,'set_value') else 'notify::active'
        widget.connect(signal,edit)
    enabled.connect('notify::active',lambda *args:update())
    update()
