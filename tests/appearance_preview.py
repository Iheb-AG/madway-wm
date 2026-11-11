"""Only approved border removal remains; legacy preview checkpoints can restore."""
import json
from pathlib import Path
import runpy
import tempfile
repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway-shell'));module=runpy.run_path(str(repo/'scripts/madway_appearance.py'))
with tempfile.TemporaryDirectory() as tmp:
    checkpoint=Path(tmp)/'rollback.json';config=api['settings']()
    config['appearance']['theme']='argent-dark';config['mouse']['speed']='0.8';config['panel']['position']='left'
    checkpoint.write_text(json.dumps(dict(version=1,appearance=dict(theme='slate',shell_finish='classic',custom_colors='true'))))
    module['change'](config,'rollback',checkpoint,lambda cfg:None)
    assert config.get('appearance','theme')=='slate' and config.getboolean('appearance','custom_colors')
    assert config.get('appearance','shell_finish')=='classic' and not checkpoint.exists()
    assert config.get('mouse','speed')=='0.8' and config.get('panel','position')=='left'
    for choice in ('light','dark','promote','rollback'):
        try:module['change'](config,choice,checkpoint,lambda cfg:None)
        except ValueError:pass
        else:raise AssertionError(choice)
print('PASS: retired Studio previews cannot be activated; legacy rollback restores only its owned appearance settings.')
