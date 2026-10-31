"""StatusNotifier test app, used only on desktop_features.py's private bus."""
import os
from pathlib import Path
import gi
from gi.repository import Gio,GLib

marker=Path(os.environ['MADWAY_TEST_TRAY_FILE'])
xml='''<node><interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="WindowId" type="u" access="read"/><property name="IconName" type="s" access="read"/>
<property name="IconPixmap" type="a(iiay)" access="read"/>
<property name="OverlayIconName" type="s" access="read"/><property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
<property name="AttentionIconName" type="s" access="read"/><property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
<property name="AttentionMovieName" type="s" access="read"/><property name="Menu" type="o" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/><property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<signal name="NewIcon"/><signal name="NewStatus"><arg type="s"/></signal>
</interface></node>'''
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
properties={key:GLib.Variant('s',value) for key,value in dict(Category='ApplicationStatus',Id='MadwayTrayFixture',
    Title='Tray fixture · 3 unread',Status='NeedsAttention',IconName='mail-unread',OverlayIconName='',AttentionIconName='mail-unread',AttentionMovieName='').items()}
properties.update(WindowId=GLib.Variant('u',0),ItemIsMenu=GLib.Variant('b',False),Menu=GLib.Variant('o','/NO_DBUSMENU'),
                  ToolTip=GLib.Variant('(sa(iiay)ss)',('mail-unread',[],'Tray fixture','3 unread')))
for key in ('IconPixmap','OverlayIconPixmap','AttentionIconPixmap'):properties[key]=GLib.Variant('a(iiay)',[])
def call(connection,sender,path,interface,method,parameters,invocation):
    marker.write_text(method);invocation.return_value(None)
def get(connection,sender,path,interface,name):
    marker.with_suffix('.properties').write_text(name)
    return properties.get(name)
bus.register_object('/StatusNotifierItem',Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0],call,get,None)
Gio.bus_own_name_on_connection(bus,'org.madway.TrayFixture',Gio.BusNameOwnerFlags.NONE,None,None)
bus.call_sync('org.kde.StatusNotifierWatcher','/StatusNotifierWatcher','org.kde.StatusNotifierWatcher','RegisterStatusNotifierItem',
              GLib.Variant('(s)',(bus.get_unique_name(),)),None,Gio.DBusCallFlags.NONE,3000,None)
marker.write_text('registered')
GLib.MainLoop().run()
