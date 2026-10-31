# Laptop sleep and lid handling

Closing the lid defaults to **Always suspend**, including with an external
monitor connected. Choose another behavior under **Settings → Power → Closing
the lid**:

| Choice | Result |
| --- | --- |
| Always suspend | Request system sleep once when the lid closes. |
| Automatic | Suspend without an enabled external display. With an external display, keep running and temporarily disable the built-in screen. |
| Do nothing | Keep running and retain display configuration. |
| Use system lid policy | Leave lid behavior to the machine's logind configuration. |

**Session → Sleep…** opens Power settings. **Sleep computer** requests sleep
immediately. Applications stay open in memory. The existing hardware sleep key
continues to be handled by logind. A nested madway session cannot request host
sleep or take ownership of the host's lid switch.

**Lock-before-sleep is enabled by default.** Swaylock checks your account password
on wake. Settings → Power can disable this explicitly; doing so resumes without
authentication. See [session locking and failure recovery](LOCKING.md).

The panel name defaults to `@user`, expanded to the current account name.
Settings → Panel → Panel name also accepts `groxiv` or another custom label.
Side panels use the first character with the full name in the tooltip.

## How it works

The operating system handles the actual suspend operation. Madway's helper calls
the [logind Suspend method and observes PrepareForSleep](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.login1.html).
It checks that the compositor belongs to the active native login session before
requesting sleep. Requests use normal logind authorization and respect existing
sleep inhibitors; madway does not force suspend or change global system files.
With locking enabled, a desktop-initiated request waits for swaylock readiness
and confirmed safe presentation before requesting suspend. External sleep uses a
logind `sleep:delay` inhibitor, released after the compositor confirms protected
frames. The delay is reacquired after resume. A failed locker cancels a
desktop-initiated sleep; an external sleep falls back to opaque locked frames
while authentication UI recovery continues. Logind's bounded timeout and forced
administrator/kernel sleep remain outside madway's control.

To use a madway lid policy, the helper holds logind's
[`handle-lid-switch` inhibitor](https://www.freedesktop.org/software/systemd/man/latest/logind.conf.html)
only while its native session is active and a lid switch is present. This gives
the desktop ownership of lid actions and avoids two components suspending on the
same event. It releases the descriptor when inactive, in system-policy mode, or
on exit. If acquisition fails, logind retains control; retry and logging are
bounded. No `logind.conf` drop-in is installed or services restarted.

The compositor reads libinput's lid capability and switch events. In Automatic
mode it distinguishes built-in `eDP-`, `LVDS-`, and `DSI-` outputs from external
outputs. Lid blanking marks only previously enabled built-in outputs and restores
them on opening. An explicitly disabled saved display profile stays disabled.
If the last external display is unplugged, the internal output is recovered.

Before sleep, madway ends interactive drags, cancels pointer grabs and clears
keyboard focus. It stops frame submission while sleeping or while its native
session is inactive. On resume or VT reactivation, it arranges outputs, damages
the full scene, schedules fresh frames, refreshes the cursor, and restores focus.
Temporary removal of every native output keeps the compositor and clients alive;
closing the last nested output still ends that nested session.

## Validation and limits

```sh
cmake --build build
python3 tests/power.py
dbus-run-session -- python3 tests/power_smoke.py
dbus-run-session -- python3 tests/desktop_smoke.py
```

The unit suite uses a fake logind connection, including fake inhibitor file
descriptors. It checks all four lid policies, nested/inactive-session guards,
duplicate request suppression, descriptor cleanup and failure fallback, and
sleep/resume signal handling. No real `Suspend` call is made.

The compositor suite uses a fake native session, a virtual lid and keyboard,
two headless displays, and a real Kitty client. It tests close/open, docked
blanking, external unplug recovery, sleep/VT transitions, keyboard focus, actual
screenshots after repaint, loss/reconnection of all outputs, retained clients,
and unchanged monitor preferences. It uses no physical VT or DRM device.

Physical laptop suspend/resume still needs a test after installing this build.
These checks cannot establish firmware, GPU-driver, or kernel wake reliability.
If wake still fails, retain `~/.local/state/madway/session.log` and the boot's
logind/kernel journal around the suspend. New compositor messages include
`Preparing compositor for system sleep`, `Laptop lid opened/closed`, and
`Session resumed: output layout, full repaint and input focus restored`.
