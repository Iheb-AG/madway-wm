# Input and workspace settings

Open Settings with **Alt+Comma**, change the controls, then click **Apply**.
These preferences are stored in `~/.config/madway/settings.ini` and reload in
the current session. Install the updated compositor and start a new session
once to make these features available in an older installation.

## Keyboard

The **Keyboard** page controls repeat speed/delay and XKB layout, variant and
options. Examples:

| Preference | Example | Effect |
| --- | --- | --- |
| Layout | `fr` | French keyboard |
| Layout | `us,fr` | US and French layout groups |
| Options | `grp:alt_shift_toggle` | Alt+Shift switches configured groups |
| Variant | `dvorak` | Dvorak variant with the `us` layout |

Leave all three XKB fields empty to restore the original backend keymap.
Invalid configurations retain the last working map and show an error in
Settings. The **Input** page retains shortcut modifier and hover-focus controls.
Changing layouts can change the symbols used for compositor shortcuts.

**Alt+B** shows or hides the panel on all monitors (**Super+B** when Super is
the configured modifier). The preference is saved as `[panel] enabled`.
Hiding closes open panel menus and releases the panel's reserved space, allowing
tiled and maximized windows to expand; showing it restores that reservation.
Tiling with Alt+T/Alt+Space leaves panel visibility unchanged. Alt+F requests
fullscreen, which hides the panel for that output until fullscreen ends.

## Mouse and touchpad

The **Mouse & touchpad** page controls separate mouse/touchpad speed and natural
scrolling, left-handed buttons, middle-button emulation, acceleration profile,
touchpad click method, tapping, tap dragging, drag lock and disable-while-typing.
Tap-to-click and tap dragging default to enabled; drag lock defaults to disabled.

Madway applies these through libinput on native devices, both at startup and
when a device is plugged in. Each setting is checked against device capabilities;
unsupported options are skipped. Nested Wayland sessions receive pointer events
already processed by the host compositor, so tapping must be enabled there.

## Touchpad gestures

Three-finger horizontal workspace swipes are enabled by default:

| Gesture | Action |
| --- | --- |
| Three fingers left | Next workspace |
| Three fingers right | Previous workspace |
| Two-finger scroll | Normal application scrolling |
| Pinch / rotate | Forward to the application, where supported |
| Hold | Forward to the application, where supported |

Workspaces switch once when fingers are lifted, using the existing workspace
slide animation. The desktop does not track the fingers during the swipe.
The first/last workspace is a boundary; gestures do not wrap between 1 and 9.
Each monitor has nine independent workspaces. Keyboard shortcuts and gestures
target the monitor under the pointer (or the active monitor when using a panel).
Changing one monitor leaves the other monitors' workspaces and windows in place.
Moving a window to another monitor puts it on that monitor's current workspace.

In **Settings → Mouse & touchpad**, use **Three-finger workspace swipe** to
enable/disable it, **Reverse workspace swipe** to exchange directions, and
**Swipe distance** to adjust the minimum movement (120 by default; 30–600).
Distance uses the backend's touchpad motion units, not screen pixels. A smaller
value needs less motion. Natural scrolling is independent of swipe direction.
These options apply live when saved. With workspace swipes disabled, three-finger
swipes are available to applications through the pointer-gestures protocol.
Other finger counts are forwarded; no four-finger desktop action is assigned.

Short, mostly vertical, cancelled or changed-finger-count gestures do not
switch. Exactly three fingers are required, and horizontal displacement must
exceed vertical displacement by a factor of 1.5. Vertical three-finger swipes
have no desktop action while workspace swipes are enabled. A long swipe still
switches only one workspace. Reversing back to the starting point cancels it.

Escape, clicks, settings reload, device removal, an external workspace change,
locking and sleep cancel an active workspace gesture. No workspace gesture
starts during a button/file drag, window move/resize, application switcher or
shell menu/launcher grab. A second touchpad cannot modify another device's
ongoing gesture. Pinch/swipe/hold delivery stays with the original application;
moving pointer focus cancels it without sending updates to another app.

No separate gesture daemon or input-group access is needed. On native sessions,
the touchpad must support gestures through libinput. In nested sessions the host
may consume workspace gestures first; use the native login session to test the
laptop's touchpad. Pinch behavior is implemented by the receiving application.
See the [libinput gesture documentation](https://wayland.freedesktop.org/libinput/doc/latest/gestures.html)
for hardware recognition and finger-count limitations.

## Workspace transitions

The **Animations** page offers **Animate workspace switching** and **Workspace
animation (ms)**. Slides use a cubic Bézier curve with gradual acceleration and
deceleration, default to 420 ms,
and accept 80–500 ms. Each monitor animates within its own bounds while the top
panel and dock remain stationary. Closing a panel menu or displaying a
notification no longer interrupts a slide. Application commits and dock work-area
changes also preserve the slide. Two monitors can animate different workspace
changes at the same time. Incoming content is a snapshot until the slide finishes.

Rapid switching settles the previous transition before starting the next one.
Clicks, display reconfiguration, locking and sleep cancel
the animation immediately. Snapshot buffers stay in memory and are released on
completion/cancellation. If snapshot allocation/rendering fails, switching
continues immediately.

Example configuration:

```ini
[keyboard]
layout = us,fr
variant =
options = grp:alt_shift_toggle

[touchpad]
tap = true
tap_drag = true
drag_lock = false
disable_while_typing = true
natural_scroll = false
speed = 0.0
click_method = default
workspace_swipe = true
swipe_invert = false
swipe_threshold = 120

[mouse]
speed = 0.0
natural_scroll = false
left_handed = false
middle_emulation = false
accel_profile = default

[workspaces]
animate = true
animation_ms = 420
```

## Window animations

**Animations → Animate maximize / minimize** controls window motion separately.
Maximize and restore zoom between the old and requested rectangles. Minimize
shrinks and fades toward the dock's screen edge; restoration reverses it. If
there is no dock, the target is the bottom center of the window's monitor.
The duration defaults to 360 ms and accepts 80–500 ms:

```ini
[windows]
animate = true
animation_ms = 360
close_animate = true
close_ms = 240
```

These transitions use in-memory snapshots while the application receives its
new size/state immediately. They settle on clicks, focus changes to another
window, workspace/layout changes, window closure, lock and sleep. Disabling the
option makes state changes immediate. Fullscreen state changes stay immediate.
Reversing an in-progress transition continues from its visible size. Minimize
preserves the window's aspect ratio and fades near the end of its journey.
Maximize/restore blends in a newly rendered snapshot at the requested size when
the client supplies it. If an application has not rendered its requested size by the end of the zoom,
the compositor displays its latest committed buffer until it updates.

**Animations → Animate closing windows / Close animation (ms)** adds a subtle
centered shrink and fade, defaulting to 240 ms. The application closes normally
and loses focus immediately; only its last pixels remain for the animation,
and input passes through them. Closing is independent of maximize/minimize.
Hidden/minimized windows and allocation failures close immediately. Captures
occur at unmap rather than on every application frame. Up to four outgoing
images share a 64 MiB budget; older images are retired when necessary. Workspace
switches, output changes, lock, sleep and shutdown release the images.

Panel visibility is checked on every layer relayout, so notification, wallpaper,
clock and media updates cannot reveal the panel over an active fullscreen window.
The regression test uses fullscreen GTK clients and real Mako/media updates;
native Brave/GPU behavior still needs validation on the target laptop.

Workspace, window and dock movement advances on each output's frame events;
there is no fixed 16 ms animation timer. A 100 Hz output can update movement at
its 10 ms refresh cadence, subject to rendering performance. Mixed-refresh
outputs advance independently, and idle outputs stop requesting animation frames.
Snapshots use the output's scale to retain native pixel density.

Wallpaper and launcher effects use the same output-driven timing. The media
indicator's value bar follows the GTK frame clock and retargets from its current
value during repeated key presses. Animations offers separate wallpaper,
launcher and media durations through `[motion] wallpaper_fade_ms`, `launcher_ms`
and `media_ms`, plus an `effects` enable switch. Window/workspace animations
retain their separate enable switches.

The shared curve is `cubic-bezier(.32,0,.18,1)`. Older shipped durations
(180 ms windows/dock and 220 ms workspaces) upgrade to 360/240/420 ms when the
configuration lacks `[motion] version=2`; custom durations and enable flags are
retained. Applying Settings saves version 2, after which all chosen durations
are used as entered.

Settings uses a compact, scrollable form with single-frame square controls and
small category rows marked by an accent stripe. Utility menus reset inherited GTK `.menu` margins so
their visible border meets the panel edge.

`tests/input_workspaces.py` checks live XKB reload/fallback, two-output slide
pixels, rapid switching, interruption and lock/simulated sleep behavior in a
private headless compositor. `tests/device_settings.c` checks capability handling
and defaults with a fake libinput device; physical touchpad behavior still needs
validation on native hardware. These tests do not suspend or authenticate the
host session.

`dbus-run-session -- python3 tests/desktop_experience.py` exercises independent
monitor workspaces and simultaneous slides with real GTK windows, wallpaper
handoffs, launcher entrance/exit images, media retargeting, desktop grid geometry,
Waybar right-click/pinning and lock cleanup. Hardware controls are mocked.
`python3 tests/session_sounds.py` checks boot/logon selection and concurrent claims.

`python3 tests/gestures.py` injects native gesture signals into a private
two-output compositor and uses real Wayland gesture clients. It checks release
thresholds/direction/boundaries, animation activation, reversal and cancellation,
live settings, simultaneous-device isolation, hotplug, lock/simulated sleep, and
pinch/hold/swipe routing. It does not read `/dev/input` or validate physical
touchpad recognition; that still needs testing in the native laptop session.

To measure private headless animation commits at 100 Hz:

```sh
MADWAY_TEST_REFRESH=100000 dbus-run-session -- python3 tests/input_workspaces.py
```

This checks cadence and transition behavior; native GPU/display
performance still needs testing on the target machine.

The installed Kitty/GLFW client intermittently crashed during synthetic output
disable/re-enable with fractional scale/rotation, including with workspace
animations disabled. The transition stress test uses software-rendered GTK
windows for reproducibility; native hardware behavior of that separate Kitty
case is unverified.
