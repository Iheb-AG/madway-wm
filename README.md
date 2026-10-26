# madway-wm

An experimental C17 compositor using wlroots 0.20. The first preview is
**v0.1.0-alpha.1**; see [CHANGELOG.md](CHANGELOG.md) for its scope and limitations.
The current milestone displays native
Wayland application surfaces inside a nested session,
with keyboard/pointer input, master-and-stack tiling, floating windows, nine
workspaces, compact retro frames, notifications, launchers, wallpaper, session
sounds, and a basic settings window.

## Build

Requires CMake 3.20+, a C compiler, pkg-config, and development files for
`wlroots-0.20`, `wayland-server`, `xkbcommon`, `pangocairo` (Pango/Cairo text
rendering), and `gio-2.0`. Also requires `wayland-scanner`.

```sh
cmake -S . -B build
cmake --build build
```

## Start the desktop

From a terminal in your existing Wayland desktop, start madway:

```sh
WLR_BACKENDS=wayland WLR_RENDERER=pixman ./scripts/madway-session
```

The session wrapper starts a private D-Bus session and the desktop helper. This
lets applications inside madway use its notification manager while your host
desktop keeps its own. Launch applications from Kitty or the launcher inside
madway so they inherit both its Wayland socket and its D-Bus environment.
Running `./build/madway` directly starts only the compositor.

Desktop runtime dependencies: `python3` with PyGObject (`gi`), GTK 3 and Gio
introspection bindings, `dbus-run-session`, **Mako**, **Wofi**, **swaybg**, **Kitty**,
`notify-send`, and **WirePlumber** (`wpctl`). Sounds use `pw-play` (PipeWire) or
`paplay` (PulseAudio). Brightness uses optional `brightnessctl`, otherwise logind
through `busctl`. These programs are already installed here except brightnessctl.

```sh
./scripts/madway-shell doctor
```

Madway prints its own socket name, for example:

```text
Listening on WAYLAND_DISPLAY=wayland-1
```

Focus the outer madway window and press **Alt+Enter** to launch Kitty on the
active workspace. Kitty must be installed and available on `PATH`.

Alternatively, from a second terminal in your existing desktop, launch Kitty.
Replace `wayland-1` with the name printed by madway:

```sh
WAYLAND_DISPLAY=wayland-1 kitty -o linux_display_server=wayland
```

New normal windows tile automatically: the first is the master on the left,
with subsequent windows stacked on the right. There are 2 logical pixels between
tiles and no outer padding. A single tile occupies the output. Focus changes do
not reorder the tiles. New windows use the output under the pointer when possible.

To prioritize application space, tiled server-decorated windows have only a 1px
border; no title bar. The focused tile has an amber border. Floating windows have
an 18-logical-pixel title bar, 1px bevels, a monospace title, and square maximize/
close controls. Inactive floating titles are slate gray. Title images are cached
until their text, size, or state changes. Dialogs with a parent window float by
default.

Applications explicitly requesting client-side decorations keep drawing their
own frame. Applications that do not use decoration negotiation (including some
GTK applications) also keep their own chrome. Kitty's
`hide_window_decorations=yes` opts out of madway's frame. Remove that override to
try the compositor's decorations. Application toolbars and tabs remain under
application control.

The border around the outer nested window belongs to your host desktop;
madway's frames surround individual applications inside it.

New windows receive keyboard focus automatically. Click a window to focus and
raise it; click the background to clear keyboard focus. You can type commands,
use modifier keys, select text with the mouse, and scroll. Pointer movement
alone does not change keyboard focus. Closing the focused window restores focus
to the topmost remaining mapped window.

Press Alt+Escape while madway receives keyboard input to exit. Your host
desktop may reserve shortcuts; Ctrl+C in the terminal running madway is also
available. The nested window must have focus in your host desktop to receive
keyboard input.

## Workspace and window controls

All shortcuts below start with Alt. Their press and release events are
consumed by madway, so they do not become terminal input.

| Keys | Action |
| --- | --- |
| Enter | Launch Kitty on the active workspace |
| D | Search installed applications (Wofi drun) |
| Shift + D | Run an executable or script from PATH (Wofi run) |
| Comma | Open madway settings |
| 1 through 9 | Switch workspace |
| Shift + 1 through 9 | Move the focused window to that workspace without following it |
| Space | Toggle the focused window between tiled and floating |
| F | Toggle the focused application's fullscreen state |
| M | Maximize / restore |
| Tab / Shift+Tab | Cycle focus forward / backward in stable window order |
| Q | Request that the focused application close |
| Escape | Exit madway |

Workspace selection is global across outputs in this version. Hidden-workspace
windows retain their application state but are removed from scene visibility and
keyboard focus. Switching back restores focus to the topmost visible window.
Floating/tiled state and normal floating geometry are retained. An output resize
or removal recomputes the layout and reassigns windows from a removed output.

Fullscreen uses the entire madway output: no madway title bar, border, or gaps.
Other windows on that output are hidden until fullscreen ends or focus cycles to
another window. Exiting fullscreen restores the preceding tiled/floating state.
The application can also request fullscreen itself, for example Firefox's F11.

The **outer nested window** is managed by your existing desktop. Use that
desktop's fullscreen/window-menu action to make madway itself fill the physical
monitor; Alt+F controls an application inside madway. A future standalone
session runs directly on physical outputs without this outer host window.

## Floating-window gestures

| Action | Control |
| --- | --- |
| Move | Drag madway's title bar, or Alt + left drag inside a window |
| Resize | Drag the 1px frame edges/corners, or Alt + right drag inside a window |
| Maximize / restore | Click the square title-bar button |
| Close | Click the title-bar X, or exit the application normally |
| Fullscreen | Alt+F, or the application's fullscreen action |

Applications can also request interactive move/resize through their own
decorations; requests are validated against the pointer grab serial. Move and
resize gestures apply to floating windows. Press Alt+Space to float a tile
first. Restore maximized/fullscreen windows before moving or resizing them.
Resizing respects application minimum/maximum size hints. When resizing the
left/top edges, the opposite edge remains anchored while the client acknowledges
and draws the requested size. The nested outer window can still be resized
using your host desktop. Host shortcuts may intercept Alt gestures.

XDG popups now get an initial configure, a scene surface, and output constraints.
The standard clipboard data-device protocol and selection requests are also
supported. Minimizing/restoring hidden windows, a workspace panel, configurable
bindings/layout ratios, primary selection, clipboard persistence, and Xwayland
remain future work. Very constrained layouts and clients that decline suggested
tile sizes need further compatibility work.

Keyboard layouts use the backend keymap when available,
otherwise the default XKB keymap; repeat is configured to 25 keys/second after
a 600 ms delay.

Close the outer madway window or press Ctrl+C in the terminal running madway to
stop the compositor. Client connections are closed during shutdown.

## Desktop services and settings

**Alt+Comma** opens the settings window. It controls wallpaper image/fit/color,
floating title height (14–24px), tile gaps (0–12px), notifications, session sounds,
volume, and brightness. Apply saves `~/.config/madway/settings.ini` (or
`$XDG_CONFIG_HOME/madway/settings.ini`) and updates the running session. The
provided `share/madway/settings.ini` documents the defaults. Tiled windows still
have no title bar; fullscreen applications have no madway borders or gaps.

Mako displays application notifications at the top right with square amber
borders. Volume up/down/mute and brightness up/down keys work without modifiers
and display short percentage/progress notifications. Changes use 5% steps;
volume is capped at 100% and brightness at 1–100%. The settings sliders offer
explicit values. Brightness requires a supported backlight and session access;
external monitor brightness/DDC is not implemented. In a nested session these
controls affect the host machine. Your host desktop may intercept multimedia
keys or Alt shortcuts before madway receives them.

Wofi provides two launcher modes: **Alt+D** searches installed `.desktop`
applications, and **Alt+Shift+D** searches executable commands/scripts. Put your
own executable scripts in `~/.local/bin`; this directory is added to the helper's
PATH. Escape closes the launcher and restores application focus. A launcher
uses an overlay only while open, so it reserves no permanent screen area.

Swaybg manages the wallpaper on the background layer. Choose an image in
settings or leave the path empty for a solid color. Supported image fitting
modes are fill, fit, center, stretch, and tile. Settings and launcher windows
use the same charcoal/amber monospace styling as the compositor.

No wallpaper images or sounds are bundled or selected by default. The personal
`longhorn assets/` directory is ignored by Git and excluded from installation.
Session sounds are disabled by default. To use your own clips, set
the Startup, Logout, and Shutdown sound files in settings (or
`sounds.startup`, `sounds.logout`, and `sounds.shutdown` in the INI file), then
enable Session sounds and click Apply. The Sound test button saves the current
settings and previews the startup clip. Playback requires a format
supported by the selected audio player.

When configured, shutdown through the settings window plays its clip before
requesting `systemctl poweroff`; this
button shuts down the **whole computer**, including when madway is nested.
Shutdown initiated elsewhere is detected through logind's PrepareForShutdown
signal, with best-effort playback while audio is still available. The settings
window offers a sound preview and sound level for configured clips.

The small desktop helper owns these programs and stops them on logout. The
compositor handles layer-shell positioning, focus, and rendering; external
services supply notifications, wallpaper pixels, and launcher content. This
keeps hardware commands and desktop UI work outside the compositor event loop.
The settings manager currently covers these desktop controls; display modes,
keyboard layouts, network management, and arbitrary key binding editing remain
future settings pages.

For a local installation, configure the intended prefix before building:

```sh
cmake -S . -B build -DCMAKE_INSTALL_PREFIX="$HOME/.local"
cmake --build build
cmake --install build
```

Then run `~/.local/bin/madway-session`. A display-manager login entry and full
standalone-session integration are still separate work.

## Validation

The desktop smoke test starts a headless compositor on its own Wayland socket
and private D-Bus session, with a temporary HOME and mock audio/backlight tools.
It exercises real Mako notifications, swaybg, both Wofi modes with injected
keyboard input, the GTK settings window, multimedia shortcuts, live configuration
reload, and startup/logout/shutdown sound events. It does not change host volume,
brightness, play audio, or request a shutdown.

```sh
cmake --build build
dbus-run-session -- python3 tests/desktop_smoke.py
```

## Firefox diagnostics

Applications launched inside a madway terminal inherit its `WAYLAND_DISPLAY`.
For a reproducible Firefox test that does not reuse an existing browser/profile,
run this from a host terminal, substituting madway's printed socket name:

```sh
madway_firefox_profile="$(mktemp -d /tmp/madway-firefox.XXXXXX)"
MOZ_ENABLE_WAYLAND=1 WAYLAND_DISPLAY=wayland-1 firefox --no-remote \
    --profile "$madway_firefox_profile" about:blank 2>/tmp/madway-firefox.log
```

This creates a separate temporary profile. The crash reporter indicates that
Firefox crashed; it does not by itself establish the cause. Keep Firefox's log
and madway's terminal output when reproducing a crash. Testing covered a fresh
Firefox window and a context-menu popup; broader browser compatibility still
needs testing.

## Read the implementation

- `src/main.c`: startup, socket creation, outputs, scene rendering, and shutdown.
- `src/main.h`: server and output state.
- Every C implementation has a matching header (`view.h`, `input.h`, `window.h`,
  `decoration.h`, `workspace.h`, `layer.h`, and `session.h`). The header declares its public interface;
  private callbacks remain inside its `.c` file. Headers use forward declarations
  for peer objects to avoid circular includes. `view.h` owns application state.
- `src/view.c`: XDG toplevel creation, initial configure, map/unmap, and cleanup.
- `src/window.c`: move/resize geometry, size constraints, maximize/fullscreen,
  and restoring the previous geometry.
- `src/decoration.c`: compact frame geometry, cached Pango/Cairo title buffers,
  and hit testing for title-bar controls and borders.
- `src/input.c`: seat capabilities, keyboard/pointer devices, cursor events,
  hit testing, shortcuts, desktop action dispatch, event forwarding, and input cleanup.
- `src/workspace.c`: scene visibility, stable master/stack geometry, workspace
  switching, moving windows between workspaces, and tiled/floating transitions.
- `src/layer.c`: wallpaper/background, panel, notification and launcher layers,
  reserved output areas, and keyboard focus for interactive overlays.
- `src/session.c`: child process launch, helper lifecycle, settings reload, and
  nonblocking desktop action messages.
- `scripts/madway-shell`: desktop service supervision, hardware controls, sounds,
  and the GTK settings window. Matching configs and sounds live in `share/madway`.

The application lifecycle is:

```text
connect to socket -> request XDG toplevel -> initial empty commit
    -> madway sends configure -> client acknowledges and attaches pixels
    -> map -> scene renders application contents
    -> unmap/destroy -> listeners and window state are released
```

Input follows a separate path:

```text
backend device -> keyboard/cursor event -> madway handler
    -> seat -> focused application surface
```

The output layout supplies shared display coordinates. Pointer hit testing
converts those coordinates to coordinates inside an application surface. Mouse
button drags stay with the surface where the first button was pressed until
all buttons are released.
