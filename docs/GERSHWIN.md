# Gershwin / Eau desktop preset

Activate after installing this build:

```sh
madway-shell preset gershwin
```

Or use **Settings → Appearance → Use Gershwin panel, frames and wallpaper**.
The preset saves the theme, 22px title height and panel thickness, top panel
placement, and original desktop picture. It hides CPU/RAM text initially, as
Gershwin does with optional menu extras. Other settings, monitor profiles,
keybindings, battery alerts, and application data are preserved. The previous
Black and other profiles remain selectable.

## Source analysis

The local investigation checkout is
`/home/iheb/Desktop/gershwin cachyos port`. Its
`gershwin-system/Library/Preferences/GlobalDefaults/NSGlobalDomain.plist` selects
**Eau**, **Inter-Medium**, size **13**. The corresponding workspace defaults
select **Abstract Blue.png**, image style 1. In
`gershwin-workspace/Workspace/Desktop/GWDesktopView.m`, that style stretches the
image separately over each monitor, despite its name `BackImageFitStyle`.
Madway uses swaybg's `stretch` to match it.

The Eau implementation is in
`/home/iheb/Desktop/osx_like_DE/gershwin-build/Developer/Library/Sources/gershwin-eau-theme`,
revision `1551c7e6fe86858ebe09cee3ee0fa8d92b1cc9da`.

| Element | Source | Values reproduced |
| --- | --- | --- |
| Panel | `Eau+Menu.m` | 22px; top RGB .95, alpha .80; bottom RGB .85, alpha .70; white top highlight |
| Dropdowns | `Eau+Menu.m` | 22px rows; 5px side padding; near-white .992, alpha .95; 1px .4 gray border |
| Selected menu row | `Eau+Menu.m` | Blue gradient (.392,.533,.953) → (.165,.373,.929); white text |
| Active title | `Eau+Drawings.m` | Gray .83 → .63; 1px white highlight |
| Inactive title | `Eau+Drawings.m` | Gray .92 → .83; text .70 |
| Title geometry | `AppearanceMetrics.h`, `Eau+WindowDecoration.m` | 22px high, 7px top corners, centered Inter title with middle ellipsis |
| Default controls | `Eau+TitleBarButtons.m` | Close on left; minimize then maximize on right; square 22px regions; red/yellow/green hover |
| Shadow | Gershwin `URSCompositingManager.m` | Gaussian radius 12, 36px kernel, 40% opacity; origin (-18,-10), shape shifted 8px down |
| UI controls | `Eau+Drawings.m`, `AppearanceMetrics.h` | Silver bevels, pill buttons, white fields, blue focus and selection |

Madway redraws these measurements with Cairo/Pango and GTK CSS. It does not
load GNUstep or run Gershwin's X11 window manager. Shadows use eight cached
texture pieces, accept no pointer input, and disappear for maximized,
fullscreen, and tiled windows. Tiny windows scale the corner pieces to fit.

The panel retains madway's utility menus: desktop/application name and workspace
access at the left; audio, battery, and clock at the right. Session actions are in
the madway menu. All four panel edges remain supported. Minimized windows stay
in Alt+Tab and have compact restore entries in the panel on the current workspace.
Scroll over those entries when needed; the Window menu also lists them.

This reproduces the desktop's Eau styling; it does not import Gershwin's
application menu exporter, Workspace file manager, or dock. Client-drawn
toolbars, title bars, and web content remain controlled by their applications.
Inter must be installed for matching type; it is already available on this
machine. A missing font falls back to the system sans-serif.

## Original wallpaper

The local copy at `share/madway/wallpapers/Abstract Blue.png` is byte-for-byte
identical to `/System/Library/Desktop Pictures/Abstract Blue.png` and the
`gershwin-assets/Library/Desktop Pictures/Abstract Blue.png` asset
(assets revision `9266b6edd28ce7fb6d9e6dfcf9cca4cc4b1c3038`).

SHA-256: `7cd68b324a5759df01f267ac8fbd938ddcbf40a1c4e59335079fb24caf0c59d7`.

The assets checkout does not include an explicit license for this picture.
The original stays Git-ignored locally; this machine's installer includes it
when present. Other checkouts can copy their own licensed copy to that path.
Without it the preset uses Gershwin's configured solid background color
`#5f6770`. No images are downloaded, synthesized, or taken from demoscene assets.

## Validation

```sh
cmake --build build
dbus-run-session -- python3 tests/gershwin_smoke.py
dbus-run-session -- python3 tests/desktop_smoke.py
python3 tests/installer_smoke.py
```

The Gershwin test requires the optional original wallpaper. It uses a private
headless display and virtual input: verifies transparent title corners, gradient
pixels, shadow input exclusion, 22px panels on four edges, hover, minimize,
Alt+Tab restore, maximize/restore, and close. Actual Kitty, settings, and menu
previews are saved in `build/gershwin-*-preview.png` and
`build/gershwin-preview.png`. It never injects input into the host session.
