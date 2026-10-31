# Session locking

Madway uses [swaylock](https://github.com/swaywm/swaylock), a Wayland locker,
with the `ext-session-lock-v1` protocol. Swaylock and the distribution's PAM
configuration perform password authentication. Madway does not read, store or
log passwords and does not implement a password checker.

Install or update with the dependency option:

```sh
./scripts/install-madway --deps
```

Start a fresh madway session to load the rebuilt compositor. Lock with **Alt+L**
(**Super+L** if selected in Input settings), **Session → Lock screen**,
**Settings → Session → Lock screen**, or:

```sh
madway-shell action lock
```

Enter your account password and press Enter. Caps Lock and keyboard-layout
feedback come from swaylock. Volume and brightness keys remain available while
locked. Normal window/workspace/launcher/logout shortcuts and desktop pointer
actions are blocked. Ctrl+Alt+F1–F12 remains available for native VT switching.

The helper launches swaylock with a generated theme configuration and an explicit
ready pipe, without daemonizing. User/system swaylock configuration is not loaded,
so a daemonize option cannot invalidate the supervised PID. The configuration
uses opaque backgrounds and compact indicators. The installer installs the distro
swaylock package and its normal PAM policy; it does not rewrite PAM files.

## Presentation and input boundaries

All normal application, panel, notification, wallpaper and overlay scenes are
under a single desktop container. Locking disables that container and displays
opaque per-output backgrounds with only lock surfaces above them. New ordinary
clients and layer surfaces remain under the hidden container.

Madway acknowledges the lock only after the first protected frame has actually
been **presented** on each enabled output. Commit sequence checks reject delayed
presentation events from earlier desktop frames. This follows the requirements
in the installed Wayland session-lock protocol XML. A lock request nonce prevents
the helper from trusting stale runtime state. Managed readiness also checks
swaylock's [ready-fd notification](https://github.com/swaywm/swaylock/blob/master/swaylock.1.scd).

Hotplugged or re-enabled monitors receive protected buffers. Output resize,
scale, rotation, disable/enable, and removal reconfigure lock surfaces. All
enabled outputs must be safe before lock readiness is reported. Re-enabling
an output builds a new protected scene buffer instead of reusing a framebuffer
retained from the desktop.

Keyboard and pointer focus are confined to the lock surfaces. Previous pointer
and keyboard grabs are ended. Ordinary popup requests cannot create a grab over
the locker. Held keys are omitted when entering password input and consumed
through unlock so they do not spill into the application underneath. The private
control socket has no unlock command, and `loginctl unlock-session` is not treated
as authentication. Only the accepted lock client can send the protocol unlock.

## Locker ownership and recovery

The helper registers the child PID over the private per-display control socket.
The compositor verifies Wayland peer credentials and pins the process using a
Linux pidfd, preventing a recycled PID from inheriting authorization. Requests
that race with registration wait briefly; unrelated or duplicate locker requests
are rejected. Start swaylock through madway's controls: running an unregistered
locker directly is deliberately not accepted.

Killing, crashing, disconnecting or timing out the locker **never unlocks** the
desktop. Opaque backgrounds remain with a small recovery message. The helper
attempts a bounded number of restarts with backoff. The lock shortcut retries
recovery, including a hung startup. Authentication is still required after the
replacement locker appears.

If the authentication UI cannot start, switch to a text console, log in normally
as your account and inspect `~/.local/state/madway/session.log`. Install or repair
the distro's swaylock/PAM package, then retry the lock action using the display
name recorded in that log, for example:

```sh
WAYLAND_DISPLAY=wayland-0 madway-shell action lock
```

The compositor's locked state survives a helper failure; a running swaylock can
still authenticate independently. Repairing or restarting a failed helper may
require the authenticated console. No crash-recovery path automatically reveals
the desktop. Root and other trusted programs with access to the user's private
control socket are outside the Wayland-client isolation boundary.

## Sleep and limitations

Settings → Power → **Lock before sleep** is enabled by default. A madway sleep
request waits for lock readiness; failure cancels suspend and keeps protection.
For external sleep, a [logind delay inhibitor](https://systemd.io/INHIBITOR_LOCKS/)
holds suspend while protected frames are presented, then is released and
reacquired after resume. If swaylock cannot start, an external sleep uses the
opaque compositor lock and retries the authentication UI after wake. Disabling
the setting explicitly allows unlocked sleep; it never unlocks an existing lock.

Logind's inhibitor timeout, forced administrator/kernel sleep, GPU/firmware
failures and a killed compositor are outside this guarantee. The implementation
has automated checks, not a formal security audit. Physical DRM suspend/wake and
password authentication should be verified after installation. Nested locking
protects only the madway session inside its host window, not the host desktop.

## Tests

```sh
cmake --build build
python3 tests/power.py
python3 tests/locking.py
dbus-run-session -- python3 tests/lock_smoke.py
dbus-run-session -- python3 tests/desktop_smoke.py
```

The lock suite uses private headless displays, a test-only protocol client and
virtual input. It withholds presentation on one monitor and verifies no early
acknowledgement; checks exclusive input, shortcut/IPC isolation, duplicate
rejection, hotplug, fractional scaling, rotation, re-enable, crash protection,
rejected takeover, supervised recovery and protocol unlock. If swaylock is
installed (or `MADWAY_TEST_SWAYLOCK` names a test binary), it also checks real
swaylock compatibility without attempting password authentication.

Supervisor unit tests also verify stale-state rejection, dual readiness checks,
timeouts, missing binaries and emergency blank protection using fake processes.
Power tests use a fake logind service and deferred locker callbacks to check
lock-before-suspend ordering, failure cancellation, delay descriptor lifetime,
resume rearming and session Lock signals. They never suspend the host.
