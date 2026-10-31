"""Pure battery/notification-state tests with fake sysfs; no hardware is changed."""
import runpy
import tempfile
from pathlib import Path

api=runpy.run_path(str(Path(__file__).resolve().parent.parent/'scripts/madway-shell'))
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    def supply(name,**values):
        path=root/name;path.mkdir(exist_ok=True)
        for key,value in values.items():(path/key).write_text(str(value))
        return path
    assert not api['battery_state'](root)['present']
    supply('AC',type='Mains',online=0)
    bat=supply('BAT0',type='Battery',present=1,capacity=20,status='Discharging',energy_now=2000000,energy_full=10000000,power_now=2000000)
    supply('mouse',type='Battery',scope='Device',capacity=1,status='Discharging')
    state=api['battery_state'](root)
    assert state['percent']==20 and state['seconds']==3600 and state['on_ac'] is False
    assert len(state['batteries'])==1 and api['battery_severity'](state)==1
    alerts=api['BatteryAlerts']()
    assert alerts.update(state)=='low' and alerts.update(state) is None
    for percent in (21,20,19):assert alerts.update({**state,'percent':percent}) is None
    assert alerts.update({**state,'percent':10})=='critical'
    assert alerts.update({**state,'percent':9}) is None
    assert alerts.update({**state,'percent':11}) is None
    assert alerts.update({**state,'status':'Charging','on_ac':True}) is None and alerts.level==0
    assert alerts.update({**state,'percent':9})=='critical'
    alerts.update({**state,'percent':26});assert alerts.level==0
    assert alerts.update(state)=='low'
    alerts.update(state,enabled=False);assert alerts.level==0
    assert alerts.update(state)=='low'
    assert api['battery_severity']({**state,'on_ac':True,'status':'Charging'})==0
    assert api['battery_severity']({**state,'on_ac':True,'status':'Not charging'})==0
    assert api['battery_severity']({**state,'on_ac':True,'status':'Discharging'})==1
    supply('BAT1',type='Battery',present=1,capacity=80,status='Discharging',energy_now=24000000,energy_full=30000000,power_now=3000000)
    state=api['battery_state'](root)
    assert state['percent']==65, state # Energy-weighted, not the unweighted 50%.
    (root/'BAT1/present').write_text('0');assert len(api['battery_state'](root)['batteries'])==1
    # Missing capacity can be derived from charge, with explicit voltage conversion.
    for name in ('capacity','energy_now','energy_full','power_now'):(bat/name).unlink()
    supply('BAT0',charge_now=1000000,charge_full=2000000,voltage_now=12000000,current_now=1000000)
    state=api['battery_state'](root)
    assert state['percent']==50 and state['seconds']==3600
    (bat/'status').write_text('Charging');(root/'AC/online').write_text('1')
    state=api['battery_state'](root)
    assert state['status']=='Charging' and state['on_ac'] and state['seconds']==3600
    for name in ('charge_now','charge_full','voltage_now','current_now'):(bat/name).unlink()
    (bat/'capacity').write_text('not available')
    state=api['battery_state'](root)
    assert state['present'] and state['percent'] is None and state['seconds'] is None
    assert api['battery_severity'](state)==0
    (bat/'capacity').write_text('0');(bat/'status').write_text('Discharging');(root/'AC/online').write_text('0')
    assert api['battery_state'](root)['percent']==0 and api['battery_severity'](api['battery_state'](root))==2
    (bat/'present').write_text('0');assert not api['battery_state'](root)['present']
print('PASS: battery detection, peripheral exclusion, energy/charge units, percentages, estimates, charging, unknown values and non-spamming low/critical warnings.')
