# Argent desktop themes

**Argent Silver** and **Argent Midnight** are madway's coordinated light and dark
workstation profiles. Select them under Settings → Appearance, or apply a preset:

```sh
madway-shell preset argent
madway-shell preset argent-dark
```

The preset sets 22px title bars and panel, places the panel at the top, enables
its bottom application dock and hides the CPU/RAM text initially. Other input,
monitor, workspace, battery and application preferences are preserved. Individual
appearance settings remain editable afterward. Black, Amber, Green Terminal,
Slate Blue and Paper remain available.

Argent uses silver or charcoal gradients, a blue selection, centered titles,
small controls, and cached shadows. Cairo/Pango draws the window chrome; GTK CSS
styles madway utilities. It does not require another desktop, an X11 window
manager or GNUstep. Application-drawn toolbars and web content follow their own
settings. Inter is preferred, with a system sans-serif fallback.

The theme implementation is in `src/argent.c` and `share/madway/argent-*.css`.
Semantic colors in `themes.ini` also drive calendar, preview and session cards.
Selection text uses the foreground with stronger contrast against the selected
background, including custom palettes. The light panel is opaque so wallpaper
lines do not appear through it.

Existing installations using earlier theme identifiers migrate to Argent or
Argent Midnight on load. Old identifiers are retained only as compatibility
aliases in the configuration readers, not as selectable profiles.

No wallpaper is bundled in the public repository. If the user supplies a local
`share/madway/wallpapers/Abstract Blue.png`, presets can use it; otherwise they
use a solid slate background. That optional picture is private and Git-ignored.
Renaming a theme does not change ownership or redistribution rights of personal
media; distribute only images you have permission to share.

Validation uses private headless sessions:

```sh
cmake --build build
# The geometry test also needs the optional local picture.
dbus-run-session -- python3 tests/argent_smoke.py
dbus-run-session -- python3 tests/desktop_smoke.py
python3 tests/installer_smoke.py
```
