# Dock, taskbar, tray, screenshots and Midnight

Install the updated desktop with `./scripts/install-madway --deps` and start a
new madway session. The installer adds Waybar, grim, slurp, wl-clipboard and
xdg-user-dirs through the distribution packages. It does not replace your
personal Waybar configuration: madway generates its own configuration and CSS
under `$XDG_RUNTIME_DIR/madway-$WAYLAND_DISPLAY/` and supervises that process.

## Existing dock implementation

The bottom dock is **Waybar**, configured with its existing
[`wlr/taskbar`](https://github.com/Alexays/Waybar/blob/master/man/waybar-wlr-taskbar.5.scd)
and [`tray`](https://github.com/Alexays/Waybar/blob/master/man/waybar-tray.5.scd)
modules. Its styling uses a centered, content-sized surface, small application
icons and a rounded shelf, inspired by the supplied macOS reference. The top
madway utility/menu bar remains available. The desktop picture stays under your
control; no reference wallpaper or Apple artwork is bundled.

The dock includes Apps, Konsole, Files (the default file manager), Settings and
running windows. Click a focused application to minimize it; click an inactive
or minimized application to focus or restore it. Middle-click closes that
window. Each window has its own entry, including multiple windows from one app.
Dock entries include windows from all workspaces: activation switches to the
window's workspace. The top bar lists windows on the current workspace, using
icons only or application names only, with the same click-to-minimize/restore behavior. Scroll over
that list when it exceeds its allocated space. The list starts directly after
the workspace number and expands across the remaining panel space.

See [window previews and wallpaper slideshows](PREVIEWS_AND_SLIDESHOWS.md) for
Alt+Tab images, the panel display option, and timed folder/selected-image backgrounds.

Settings → Panel controls the dock's enabled state, edge, icon size, icon-only
versus labeled entries, and tray. Every output gets a dock. Maximizing an
application slides that output's dock out and releases its reserved space.
Move the pointer to the dock's screen edge to reveal it; it stays while hovered
and hides 350ms after leaving. Restoring, minimizing or closing the maximized
window brings the dock back. Other outputs and workspaces retain their own state.

The compositor animates the existing Waybar surface using
`cubic-bezier(.32, 0, .18, 1)`, default duration 240ms, paced by output frames.
Reversing a transition
continues from the current position. Slides are clipped to their own monitor.
Settings → Panel can disable maximized-window hiding, disable animation or
adjust duration (80–500ms). Fullscreen and locking hide the dock immediately.
Locking covers all layer surfaces and withdraws foreign
window handles; dock requests cannot activate, resize or close normal windows
while locked. Handles are recreated after authentication.

Madway implements `wlr-foreign-toplevel-management-v1` for compatible docks and
taskbars, including title/app identity, focus, minimize, maximize, fullscreen,
parent/output updates and close. Window identity comes from the client's
`app_id`; icons are resolved from installed desktop entries/icon themes, with a
generic top-bar icon when no desktop entry matches.

## Telegram and other tray apps

An application needs a StatusNotifier host to display its tray item. The earlier
madway panel did not implement one; Waybar now supplies it on the session D-Bus
bus. Enable **System tray / Telegram icon** in Panel settings and enable
Telegram's own tray option. Restart Telegram after installing if needed, and
launch it inside the madway session. A Telegram process running on another
desktop or D-Bus session may still belong to that session.

The app supplies its icon, tooltip, attention state and any unread count drawn
into its tray icon. Madway does not synthesize unread messages or promise a
numeric badge on every dock icon. The same tray supports other compatible apps.

## Screenshots

| Control | Result |
| --- | --- |
| Print | Save the entire desktop and copy its PNG to the clipboard |
| Shift+Print | Select a rectangle, then save and copy it; Escape cancels |
| Ctrl+Print | Save the desktop and copy the PNG to the clipboard |
| Username menu → Screenshot | The same three actions |
| Settings → Session | Capture desktop or select an area |

Files go to the XDG Pictures directory's `Screenshots` subdirectory (normally
`~/Pictures/Screenshots`). Without xdg-user-dir, the fallback is
`~/Pictures/Screenshots`. Filenames include a timestamp and unique suffix; files
are created with owner-only permissions. A notification shows the saved path
when application notifications are enabled.

The tools are grim for capture, slurp for area selection and wl-copy for PNG
clipboard ownership. Madway exposes screencopy and data-control protocols.
Keyboard screenshot shortcuts keep an already-open panel menu visible in the
capture. Choosing a screenshot action inside the Screenshot menu closes that
invoking menu deliberately, so its own controls do not obstruct the picture.
KDE Spectacle's KWin-specific capture integration is not added by this work.
`madway-screenshot`, `madway-screenshot --region`, and
`madway-screenshot --clipboard` can also be run from a madway terminal.
All captures copy automatically; use `madway-screenshot --no-clipboard` to save
only. If clipboard ownership fails, the saved image is retained and the helper
logs the copy failure.
Captures are refused while locked, rechecked after selecting/capturing, and
failed or canceled captures leave no partial file. Only one interactive capture
runs at a time.

Dock labels and other layer-shell popups are constrained to their monitor's
visible bounds, so bottom and side docks keep tooltips on screen.

## Gershwin Midnight

Choose **Gershwin · Midnight** under Appearance, or apply the coordinated preset:

```sh
madway-shell preset gershwin-dark
```

The preset uses the existing 22px Eau layout, top bar and bottom dock with dark
charcoal gradients, light text and blue selections. It keeps the local Gershwin
wallpaper policy; the theme variant alone does not change your wallpaper.
Close, minimize and maximize glyphs remain white, including hover states.
Desktop menus, settings, frames, notification colors, launcher and dock follow
the palette. Application-owned toolbars/content follow the application's theme.

Audio rows separate the device/application name, default/mute controls and
slider. Long names ellipsize and retain their full tooltip, and the list scrolls
instead of letting controls collide or run beyond the popup.

## Validation

```sh
cmake --build build
dbus-run-session -- python3 tests/desktop_features.py
dbus-run-session -- python3 tests/dock_smoke.py
dbus-run-session -- python3 tests/desktop_smoke.py
dbus-run-session -- python3 tests/lock_smoke.py
python3 tests/installer_smoke.py
```

Tests use temporary user settings, private D-Bus sessions and headless outputs.
They exercise actual Waybar, Konsole, Kitty, foreign-toplevel requests, a
synthetic StatusNotifier application, PNG files/clipboard, region/cancel
behavior, all dock edges, light/dark themes, long audio names, locking and
installation staging. The tray test does not open a personal Telegram account.
