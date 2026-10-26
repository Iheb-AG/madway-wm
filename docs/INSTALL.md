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

## Controls in the native session

- **Alt+Enter:** Kitty terminal.
- **Alt+D / Alt+Shift+D:** applications / commands.
- **Alt+,** or the bar's Settings button: settings.
- **Right-click empty desktop space:** desktop utility menu.
- **Alt+T:** floating/tiled; **Alt+F:** fullscreen.
- **Alt+Escape:** log out of madway.
- **Ctrl+Alt+F1–F12:** request another VT in a native hardware session.

The modifier can be changed to Super under Input settings. The top bar has
workspace buttons and a shared utility menu; its height/status/clock options
are under Panel. It is hidden over fullscreen applications. Sounds and wallpaper
images are opt-in. Your existing `~/.config/madway/settings.ini` is preserved.

This preview has no lock screen, Xwayland, network manager, or full desktop
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

## Removing the login choice

Remove the session entry if you no longer want it listed:

```sh
sudo rm -- /usr/share/wayland-sessions/madway.desktop
```

CMake records installed file paths in `build-install/install_manifest.txt`.
Review that file before using it to remove installed binaries/data. Personal
settings and media are not part of the installation manifest.
