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

## Mouse and touchpad

The **Mouse & touchpad** page controls separate mouse/touchpad speed and natural
scrolling, left-handed buttons, middle-button emulation, acceleration profile,
touchpad click method, tapping, tap dragging, drag lock and disable-while-typing.
Tap-to-click and tap dragging default to enabled; drag lock defaults to disabled.

Madway applies these through libinput on native devices, both at startup and
when a device is plugged in. Each setting is checked against device capabilities;
unsupported options are skipped. Nested Wayland sessions receive pointer events
already processed by the host compositor, so tapping must be enabled there.

## Workspace transitions

The **Appearance** page offers **Animate workspace switching** and **Workspace
animation (ms)**. Slides use a cubic Bézier curve with gradual acceleration and
deceleration, default to 420 ms,
and accept 80–500 ms. Each monitor animates within its own bounds while the top
panel and dock remain stationary. Closing a panel menu or displaying a
notification no longer interrupts a slide. Workspace selection remains global across
monitors. Incoming content is a snapshot until the slide finishes.

Rapid switching settles the previous transition before starting the next one.
Clicks, window/layout changes, display reconfiguration, locking and sleep cancel
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

**Appearance → Animate maximize / minimize** controls window motion separately.
Maximize and restore zoom between the old and requested rectangles. Minimize
shrinks and fades toward the dock's screen edge; restoration reverses it. If
there is no dock, the target is the bottom center of the window's monitor.
The duration defaults to 360 ms and accepts 80–500 ms:

```ini
[windows]
animate = true
animation_ms = 360
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

Workspace, window and dock movement advances on each output's frame events;
there is no fixed 16 ms animation timer. A 100 Hz output can update movement at
its 10 ms refresh cadence, subject to rendering performance. Mixed-refresh
outputs advance independently, and idle outputs stop requesting animation frames.
Snapshots use the output's scale to retain native pixel density.

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
