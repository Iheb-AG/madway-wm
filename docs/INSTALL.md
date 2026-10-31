# Installing a native madway session

madway is an experimental desktop preview. The installer adds a Wayland login
session alongside your existing desktop; it does not replace KDE, change the
login manager, select the default session, or reboot the machine. Installation
has been tested with a temporary staging root. A physical DRM/libinput session
has not been exercised in this development environment.

## CachyOS / Arch Linux

Run these commands from the checkout as your regular user:

```sh
./scripts/install-madway --dry-run
./scripts/install-madway --deps
```

The optional `--deps` flag installs build and desktop dependencies using
`pacman -S --needed`. It does not refresh package databases or force confirmation.
If dependencies are already installed, omit `--deps`:

```sh
./scripts/install-madway
```

The script builds in `build-install`, installs binaries/data under `/usr/local`,
and installs `/usr/share/wayland-sessions/madway.desktop`. It requests sudo only
for package installation and system-file copying. It checks that wlroots 0.20
has DRM, libinput, and session support and that GTK layer-shell bindings exist.
Other distributions can run the installer after manually installing the README
requirements; automatic dependency installation is currently Arch/CachyOS only.

Save your work and log out normally. In the login screen's session selector,
choose **madway (experimental)**. You can choose your previous desktop again on
a later login. The native launcher explicitly selects the DRM/libinput backend,
clears inherited nested-display variables, and uses the login user's D-Bus bus
when available. The desktop helper exports the Wayland activation environment
for native-session D-Bus services.

A native session needs an active local login with device access through logind
or a correctly configured libseat backend. The installer does not change device
permissions, add users to privileged groups, or enable seat/system services.

## If login shows a black screen

The login entry must contain `Exec=/usr/local/bin/madway-session --native`
without quotes around the executable. Plasma Login's session wrapper executes
the field without evaluating shell quotes; the earlier quoted entry exited
with status 127 before madway started. Reinstall from this checkout to update it:

```sh
./scripts/install-madway
```

Native launches now save compositor/helper output in
`${XDG_STATE_HOME:-$HOME/.local/state}/madway/session.log`, retaining one previous
nonempty attempt as `session.previous.log`. This log is private to your user.
If persistent logging fails (including a full filesystem), the launcher uses
`$XDG_RUNTIME_DIR/madway-logs/session.log` instead. If both locations fail, it
continues with the login manager's stdout/stderr. Logging failure must not abort
the desktop. Check the login manager journal if neither log exists
(`journalctl -b -u display-manager`).

An empty log together with an immediate exit status 1 and "No space left on
device" in the journal can indicate the earlier launcher's first log write
aborted startup. Free disk space and update just the launcher from the checkout:

```sh
df -h /
sudo install -m755 scripts/madway-session /usr/local/bin/madway-session
```

Review Trash or cached packages before deleting anything. A full disk can also
prevent application state, settings and login-manager files from being written;
the launcher fallback does not resolve those failures.

If the screen is stuck, try Ctrl+Alt+F3, log into the text console, and inspect:

```sh
tail -n 100 "${XDG_STATE_HOME:-$HOME/.local/state}/madway/session.log"
```

After returning to your existing desktop, `journalctl -b -1` shows the previous
boot if you rebooted. Avoid starting `--native` inside an already running desktop
to troubleshoot; use the nested launch command below for development.

## Controls in the native session

- **Alt+Enter:** Konsole terminal.
- **Print / Shift+Print / Ctrl+Print:** screenshot / select area / copy screenshot.
- **Application taskbar/dock entry:** minimize the focused window, otherwise focus/restore.
- **Alt+D / Alt+Shift+D:** applications / commands.
- **Alt+,** or madway → Settings: settings.
- **Right-click empty desktop space:** desktop utility menu.
- **Alt+T:** floating/tiled; **Alt+F:** fullscreen; **Alt+A:** keep above others.
- **Alt+right-drag:** resize floating windows or shared tile boundaries.
- **Ctrl+Shift+arrows:** reorder tiles.
- **Alt+Escape:** log out of madway.
- **Alt+L:** lock the session using swaylock and your account password.
- **Ctrl+Alt+F1–F12:** request another VT in a native hardware session.

The modifier can be changed to Super under Input settings. The top bar has
workspace/window/status dropdowns and a shared utility menu; its height/status/clock options
are under Panel. Screen edge supports top, bottom, left and right. It is hidden over fullscreen applications. Sounds and wallpaper
images are opt-in. Your existing `~/.config/madway/settings.ini` is preserved.

Screen locking uses swaylock; install it with `--deps`. This preview has no
Xwayland, network manager, or full desktop
portal/polkit-agent setup. It supports native Wayland applications. The system
power-off action shuts down the whole computer, following a confirmation in
settings.

## Test an installation without touching system files

```sh
./scripts/install-madway --destdir /tmp/madway-stage \
    --build-dir /tmp/madway-build
```

This puts the files under `/tmp/madway-stage/usr/local` and the session entry
under `/tmp/madway-stage/usr/share/wayland-sessions`; it uses no sudo. `--deps`
cannot be combined with staging. To change installation locations, use
`--prefix`, `--sessions-dir`, and `--build-dir`. Run `--help` for details.

For a nested preview inside your current desktop, use:

```sh
WLR_BACKENDS=wayland WLR_RENDERER=pixman ./scripts/madway-session
```

Add `WLR_WL_OUTPUTS=2` to try two nested outputs. Nested mode keeps its own D-Bus
session and does not reconfigure physical monitors.

## Fullscreen playback stalls until pointer activity

A failed display commit (for example DRM reporting `Device or resource busy`)
used to return from rendering without retrying unless a desktop animation was
active. A video client waiting for its next Wayland frame callback could then
stall until pointer movement damaged the scene and woke rendering again.

Madway now restores the failed frame's damage and retries independently on that
output. The first retry follows its refresh period; consecutive failures back
off up to 250 ms to avoid a busy loop. Successful commits reset the backoff.
Normal idle outputs do not gain a continuous redraw loop. Sleeping, disabled
and inactive outputs are not retried, and retries are removed with their output.
Client frame callbacks and lock presentation barriers still require the normal
successful rendering path.

The native session log at `~/.local/state/madway/session.log` records failures
and `Scene commits recovered` messages. This recovery does not repair permanent
GPU/driver faults; if playback still freezes after reinstalling and starting a
new session, retain the log around the freeze for diagnosis.

`python3 tests/frame_recovery.py` uses a private fullscreen client paced solely
by frame callbacks. It verifies recovery at 60/100 Hz with injected commit
failures, restored damage, retry backoff and simulated sleep/resume, without
mouse or keyboard input. It does not play media in the user's browser or test
the native DRM driver.

## Removing the login choice

Remove the session entry if you no longer want it listed:

```sh
sudo rm -- /usr/share/wayland-sessions/madway.desktop
```

CMake records installed file paths in `build-install/install_manifest.txt`.
Review that file before using it to remove installed binaries/data. Personal
settings and media are not part of the installation manifest.
