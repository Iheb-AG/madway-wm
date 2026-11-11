"""Restore a checkpoint left by the retired Studio appearance experiment."""
import json
from pathlib import Path
import re

FIELDS=('theme','shell_finish','custom_colors')


def change(config,choice,checkpoint,save):
    if choice!='rollback':raise ValueError('Studio was retired; only rollback is available')
    checkpoint=Path(checkpoint)
    try:data=json.loads(checkpoint.read_text())
    except FileNotFoundError:raise ValueError('No appearance preview to restore') from None
    values=data.get('appearance') if isinstance(data,dict) and data.get('version')==1 else None
    if not isinstance(values,dict) or set(values)!=set(FIELDS) or any(not isinstance(value,str) or len(value)>128 for value in values.values()):raise ValueError('Invalid appearance rollback checkpoint')
    if not re.fullmatch(r'[a-z0-9-]+',values['theme']) or values['shell_finish'] not in ('classic','studio-preview') or values['custom_colors'] not in ('true','false'):raise ValueError('Invalid saved appearance')
    values['shell_finish']='classic'
    config['appearance'].update(values);save(config);checkpoint.unlink()
