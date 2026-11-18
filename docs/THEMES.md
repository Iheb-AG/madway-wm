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

## XP and Vista profiles

[XP screenshot](screenshots/theme-xp.png) · [Vista screenshot](screenshots/theme-vista.png)


**Windows XP · Luna** (`windows-xp`) adds a blue shaded panel, green user/menu
button, warm beige controls and native blue title bars with right-aligned
minimize/maximize/close controls. **Windows Vista · Aero** (`windows-vista`) adds
slate glass-like bands, pale blue surfaces and the same compact native controls.
These are original Cairo/CSS interpretations; no Microsoft wallpaper, font,
icon pack, sound or other binary artwork is bundled. Font names use installed
system fonts with normal sans-serif fallback. Glass bands are opaque, without blur.

Select the theme in **Settings → Appearance** and Apply to retain your geometry.
**Use this profile layout** applies coordinated title/panel sizes and a bottom
panel. Command-line equivalents:

```sh
madway-shell preset windows-xp
madway-shell preset windows-vista
```

## Approved Argent refinement

The thin perimeter outline is removed from both Argent light/dark panels and
docks. Original application icons, sizes, positioning and utility icons remain.
The Studio finish experiment was not approved and is retired. A stored Studio
flag is ignored on load. If you used its trial and want the previous color profile
back too, `madway-shell appearance-preview rollback` can restore its old checkpoint;
new previews cannot be activated.

## Prism glass preset

[Glass screenshot](screenshots/theme-glass.png)

Choose **Prism · Glass** (`prism-glass`) in Settings → Appearance → Theme profile
and Apply. It is a separate opt-in preset; switching back to Argent, Black or
another profile restores that preset's materials. Personal wallpaper, audio,
input preferences and dock contents are retained. The optional coordinated layout
uses a compact top panel and bottom dock.

Prism uses real alpha compositing on the panel, dock, menus, launcher, switcher,
media indicators, session cards, previews, Settings and compositor title bars.
Settings has an RGBA client surface; background shapes remain visible underneath.
Text/icons stay opaque, control surfaces are solid, and grouped form cards use
a stronger dark tint for legibility over bright wallpaper. There is no whole-window
opacity reduction, compositor background blur, or global change to third-party
application content. Transparency uses the existing wlroots scene composition,
so it does not require an extra blur pass or continuous idle rendering.

`share/madway/prism-glass.css`, `themes.ini` and the glass branch of `src/argent.c`
define the preset. The generated background in the screenshot is a private test
fixture, not an installed wallpaper. Tests verify CSS parsing, RGBA pixels over
different backdrops, opaque heading text and real headless captures.
