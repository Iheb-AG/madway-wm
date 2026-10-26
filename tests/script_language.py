"""Validate the madway language and theme profiles without running user commands."""
from pathlib import Path
import runpy
import tempfile

repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway-script'))
parse=api['parse']
with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp);(base/'wall paper.png').touch()
    commands=parse('''# My desktop
workspace 2
exec kitty --title "Work terminal"
wait 100
move 3
window toggle-floating
tile left
theme amber
background color #123456
background image "wall paper.png" fit
set input.focus_follows_mouse true
''',base)
    assert len(commands)==10
    assert commands[1]==('exec',['kitty','--title','Work terminal'])
    assert commands[0][1]['value']==1 and commands[3][1]['value']==2
    assert commands[-2][1]['updates']['wallpaper.path']==str(base/'wall paper.png')
    assert parse('window toggle-above',base)[0][1]['action']=='window-above'
    assert parse('set panel.position left',base)[0][1]['updates']=={'panel.position':'left'}
    # Shell syntax stays literal argv. No interpolation or shell eval.
    assert parse('exec printf "$(touch /tmp/never-executed)"',base)[0][1][1]=='$(touch /tmp/never-executed)'
    for source in ('workspace 0','move 10','theme missing','set missing.key value',
                   'set input.focus_follows_mouse maybe','background color nope','wait -1',
                   'background image absent.png','window destroy','exec "unterminated'):
        try:parse(source,base)
        except ValueError as error:assert 'Line 1:' in str(error)
        else:raise AssertionError('Invalid script accepted: '+source)
    # Parsing the entire file catches later errors before any command executes.
    try:parse('exec kitty\nworkspace 20',base)
    except ValueError as error:assert 'Line 2:' in str(error)
    else:raise AssertionError('Partial script accepted')
profiles=api['api']['themes']()
assert set(profiles.sections())=={'black','amber','terminal','slate','paper'}
for name in profiles:
    if name=='DEFAULT':continue
    cfg=api['api']['settings']();cfg['appearance']['theme']=name
    style=api['api']['theme_style']('background: #000000; color: #c8c8c8;',cfg)
    assert profiles[name]['background'] in style and profiles[name]['text'] in style
print('PASS: script grammar, quotes/colors/relative paths, full-file validation, and five theme profiles.')
