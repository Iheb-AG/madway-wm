# Customization and display layouts

Settings groups its pages under **Appearance**, **Workspace**, **Input**,
**Connectivity** and **System**. Search spans every group. Existing page IDs remain available to panel actions and the CLI.

| Appearance page | Controls |
| --- | --- |
| Themes & style | Profile/presets, font family, UI/title text sizes, installed icon theme, optional background/surface/text/muted/border/accent/active colors |
| Wallpaper | Solid color, image/fit, folder or selected-image slideshow, pause and duration |
| Session effects | Off, simple fade or nine shaders, synchronized sound, opening/exit durations and previews |
| Animations | Workspace/window/closing toggles and durations, wallpaper fade, launcher/media timing |
| Panel | Edge, thickness, padding, spacing, text size, label, task icons/names, clock format, widget visibility |
| Dock | Edge, icon size, icons/names, spacing, margin, corner radius, tray, autohide/animation, built-in shortcuts, running tasks and ordered pins |
| Desktop icons | Directory, visibility, image/label sizes, cell width, spacing, edge inset, labels and single-click activation |
| Launcher | Width, result count, icon visibility/size, inline completion and suggestion opacity |

The Themes & style page links directly to the other appearance pages. Empty font
and icon-theme names preserve profile/system defaults. Text size zero preserves
the component's theme size. Icon themes must already be installed. Palette
overrides are opt-in; empty color fields inherit the selected profile. **Use
profile colors** clears overrides. The shell and compositor-drawn title bars
use these preferences; applications retain their own toolkit themes and fonts.

The dock editor searches installed desktop entries. **Add** pins the selection;
↑/↓ reorder it and × removes it. Missing applications remain removable. Changes
take effect on Apply. Running dock icons and panel tasks retain their **Keep in
Dock** right-click action. Built-in Applications, Terminal, Files and Settings
shortcuts and the running-window list can each be hidden independently.

Clicking a panel button opens its menu; clicking it again closes it. Clicking a
different button replaces the menu. Outside clicks and Escape dismiss it.

## Displays

**Workspace → Displays** previews connected monitors in logical coordinates.
Scaling and rotation affect rectangle proportions. Drag a rectangle to move a
monitor; nearby edges snap together. Disabled outputs remain visible and marked
Disabled. Use **Arrange horizontally/vertically** for a quick starting layout.
Expand a monitor to edit enabled state, resolution/refresh, X/Y, scale or rotation.
Numeric changes update the preview too. Refresh discards unsaved display drafts.

Dragging edits the draft only. **Apply** writes monitor profiles and asks the
compositor to validate them. At least one output must remain enabled. Rejected
configurations report the compositor error; the current working output state is
retained. Monitor previews do not display application contents.

Preferences live in `~/.config/madway/settings.ini`. Existing configuration files
inherit defaults for new fields; no private images, audio or application data is
added to Git. After updating compositor code, reinstall and start a new session.

## Supported base system

This project targets **Linux**, with wlroots **0.20**, Wayland, libinput,
xkbcommon, Pango/Cairo and GLib/GIO. The shell uses GTK 3/PyGObject,
GtkLayerShell, Waybar, Wofi, Mako, swaybg and other tools listed in the README.
A native session needs wlroots DRM/libinput/session support and working GPU/seat
access. Nested development needs a host Wayland compositor.

CachyOS and KDE/Plasma are not required. Konsole is the current terminal choice
and brings KDE libraries; it does not need a running Plasma desktop. Audio uses
PipeWire/Pulse-compatible tools. Native sleep/lid handling and brightness fallback
use systemd-logind; locking uses swaylock with working PAM configuration.
GTK/Qt application styling, portals, polkit agents and distribution packaging
still need their own setup; this is not a complete replacement for every service
that a larger desktop starts.

`install-madway --deps` currently installs packages with pacman on Arch/CachyOS.
On another distribution install the matching dependencies manually, then build
and install. Older wlroots versions are not interchangeable with this checkout's
0.20 API. Immutable/declarative systems need suitable packaging/session setup.
Windows, macOS and BSD are not supported targets for the current code, and
arbitrary GPU/driver combinations are not certified.

Validation: `tests/desktop_smoke.py` checks the settings form and existing desktop
behavior. `tests/desktop_experience.py` checks actual panel toggle clicks and
runs `tests/customization_ui.py` for monitor dragging, draft/apply behavior,
palette validation, pin editing and persistence. Tests use private headless
outputs, temporary homes and mocked hardware controls.

Connectivity, default applications, calendar and centered session cards are
documented in [system settings](SYSTEM_SETTINGS.md). The renamed desktop profiles
are [Argent Silver and Argent Midnight](THEMES.md).

Settings uses a grouped, searchable source list with sectioned forms and
theme-aware switches and beveled buttons. **Appearance → Session effects** controls simple fades or the
nine built-in shaders for logout/restart/shutdown. **System → Sounds** holds
personal sound files. See [settings and exit effects](SETTINGS_AND_EXIT_EFFECTS.md).
