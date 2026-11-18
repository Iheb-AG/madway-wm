# System settings and desktop utilities

KDE Plasma was used as the checklist for this pass. Its [System Settings
handbook](https://docs.kde.org/trunk_kf6/en/systemsettings/systemsettings/general.html)
groups appearance, workspace behavior, personalization, network, hardware and
system administration. Madway exposes a smaller set, with its own compositor
settings and existing system services where appropriate.

| Area | Available in madway | Remaining work |
| --- | --- | --- |
| Appearance | Profiles, palette/font/icons, wallpaper/slideshow, animations, panel, dock and desktop | Application toolkit integration, cursor chooser |
| Workspace | Tiling/floating, master sizing, tile swaps, per-output workspaces, task switcher, monitor layout | Arbitrary keybindings, window rules |
| Input | XKB layout, repeat, mouse, tap/drag, scrolling and three-finger workspace gestures | Accessibility input tools, tablet calibration |
| Connectivity | Wi-Fi radio/scan/connect/disconnect, device status, saved Ethernet/Wi-Fi/VPN connections; Bluetooth power, paired devices and pairing manager | Native enterprise authentication and pairing UI; alternative network backends |
| Applications | Default browser, mail, file manager, text/PDF/video/image associations | Autostart editor, application permissions |
| Time & system | Clock, local timezone, system time editor, OS/kernel/session information | Native timezone/NTP editor, user/account management |
| Notifications, audio, power | Notification configuration, device/application mixer, battery/lid behavior, sleep and locking | Idle timeout profiles, accessibility, printing and removable-device management |

The checklist is a roadmap, not a claim of Plasma feature parity.

## Playback troubleshooting

Open **System → Audio & brightness**. Select an output and port, then **Use output**
to set the default and reroute current playback. **Test speakers** plays an installed
system sample through the selected output without changing mute or volume; it stops
when the page closes, the session locks or the system sleeps. The sample requires
`alsa-utils` or the freedesktop audio-test sample, and `pw-play` must be installed.

Start a video/song and Refresh to see its application mute and output route.
Device volume and application mute are separate: if the speaker test works but
a browser is silent, inspect its **Unmute** button and selected output. App controls
apply immediately and do not wait for Apply. No active stream appears while an
application is not playing audio. A device marked SUSPENDED while idle is normal.

Confirmed logout/shutdown now uses temporary playback routes rather than changing
persisted app mute flags; see [exit audio](SETTINGS_AND_EXIT_EFFECTS.md#application-audio-during-exit).
This does not automatically unmute applications the user intentionally muted.

## Connectivity

Open Settings → Connectivity → Network or Bluetooth. The grouped Settings menu
also links to these pages. Network controls use NetworkManager's documented
[nmcli interface](https://networkmanager.dev/docs/api/latest/nmcli.html). Reads,
scans and state changes run outside the GTK event loop; pending operations are
serialized per pane. Opening the page reads status and cached scan results;
Refresh / scan requests a fresh scan. The page refreshes status every 15 seconds.

Connect opens Konsole running `nmcli --ask`. NetworkManager asks for credentials
there, including enterprise/VPN credentials when required. Passwords are never
included in process arguments or madway's settings file. Disconnect and radio
changes apply immediately. Saved connection names with colons/backslashes are
parsed using nmcli's escaped output.

Advanced connection editing uses **nm-connection-editor**, with Plasma's network
module as a fallback. Bluetooth power and paired-device information use
**bluetoothctl**; pairing uses **blueman-manager**, with Plasma's Bluetooth module
as a fallback. These services are optional: missing tools, absent adapters,
blocked radios, policy failures and unavailable daemons display their errors.
Madway does not enable services or change another network stack automatically.

Arch/CachyOS optional packages:

```sh
sudo pacman -S --needed networkmanager nm-connection-editor blueman bluez-utils
```

Use the system's NetworkManager/BlueZ services and authorization policy. A
standalone installation needs a Polkit authentication agent supplied by
the distribution; madway starts a supported installed agent at native login.
Madway does not replace the system's authorization policy or portal environment.
The date/time editor likewise uses an installed Plasma or GNOME settings module;
changing the system clock still requires the system's usual authorization.

## File access and partition mounting

Native madway logins start one installed graphical Polkit authentication agent,
preferring KDE's agent, then LXQt, MATE or GNOME. KDE's existing D-Bus owner is
reused; other agents reject duplicate registration through Polkit itself. The
agent is a managed session child and stops when the helper exits. Missing or
failed agents are logged without preventing desktop startup. Nested madway
leaves authentication to the host desktop. Agent windows use native Wayland,
even if the login environment contains an X11-only toolkit override.

These are separate file-manager operations:

- **Mounting a partition:** file managers ask the system's UDisks2 service to mount
  or unlock a device. Polkit requests a password when the system policy requires
  one. Services are normally activated over D-Bus; madway does not run `sudo mount`
  or automatically mount every device.
- **Protected folders in Dolphin:** install `kio-admin`, then use Dolphin's
  administrator mode, or enter `admin:///etc` in the location bar. KDE documents
  this [administrator backend](https://github.com/KDE/kio-admin).
- **GTK file managers:** GVfs supplies remote/device support and an `admin:///`
  backend where supported by the application. Madway no longer forces
  `GIO_USE_VFS=local` on shell-launched applications. An explicit user override
  is respected; remove it from your startup configuration if it disables GVfs.

On Arch/CachyOS, `install-madway --deps` includes `polkit`, `polkit-kde-agent`,
`udisks2` and `gvfs`. Dolphin's optional backend can be installed separately:

```sh
sudo pacman -S --needed kio-admin
```

Run the file manager as your normal user; use its administrator backend rather
than `sudo dolphin`. An authentication agent provides password prompts, not
blanket access: filesystem permissions, read-only mounts, unsupported filesystems
and system policy still apply. See the
[Polkit architecture](https://www.freedesktop.org/software/polkit/docs/latest/polkit.8.html).

After updating, reinstall madway and start a new login session. The already-running
helper and file managers retain their previous environment. `madway-shell doctor`
reports the discovered agent executable, UDisks CLI and any GIO backend override;
this is an installation check, not proof that authentication succeeds. Check the
native session log for agent startup/exit messages. Real password prompts and
mounting must be verified in a native local login; the automated tests use fake
agent processes and never authenticate or mount host devices.

## Default applications

Choose an application and press **Set** in that row. This writes the corresponding
GIO/MIME preference immediately; opening the page makes no association changes.
The browser row sets both HTTP and HTTPS. This page does not change madway's
Konsole terminal shortcut. Shell layout preferences elsewhere still use Apply.

## Panel previews and calendar

The panel also has a digits-only **timer / stopwatch** button, initially `05:00`.
Click it to open a small anchored popup, choose Timer or Stopwatch, and use
Start, Pause/Resume or Reset. A countdown's hours/minutes/seconds can be edited
before starting or after resetting. The mode and last countdown duration are
remembered; running/paused clocks belong to the current desktop session.

Closing the popup and reloading the panel do not stop either clock. The countdown
and stopwatch can run independently; the selected mode supplies the panel readout
on every monitor. Countdown completion sends one normal desktop notification,
following notification preferences. Times include laptop sleep and do not change
when the system clock is adjusted. There are no lap lists or extra application
windows. Disable the readout under **Panel → Timer / stopwatch**; hiding it does
not cancel a running countdown. The popup follows all four panel positions.

Hover an application task in the panel for its window image and title, including
minimized windows. The compositor captures only that window on demand, without
opening Alt+Tab or changing focus. Images are private runtime files; locking and
sleep clear them. Turn previews off in Panel → Window preview tooltips.
Thumbnails are snapshots when entering the task, rather than continuously
capturing every application. Clients without capturable content show an icon.

Click the clock to open a month calendar with week numbers, previous/next month
controls and Today. The same popup links to date/time and clock-format settings.
It is a calendar view, not an appointment or account-sync service.

## Tile placement

Ctrl+Shift+arrows retains its existing directional tile movement. Additions:

- **Alt+Shift+Enter** (or Super+Shift+Enter with that modifier) puts the focused
  tiled application into the master slot.
- The Window menu lists **Swap tile with …** for other tiled windows.
- Right-click another tiled application's panel entry and choose **Swap tile
  with focused window**.

A swap preserves keyboard focus and slot proportions. Floating, minimized,
maximized, fullscreen, hidden-workspace and other-monitor windows are excluded.
With one tile, making it master does nothing.

## Session confirmation and exit effects

Restart, shutdown and panel/settings logout use a centered utility card on the
active monitor. Cancel receives focus, and Escape closes the card. Text and
controls use semantic theme colors with contrast-aware selected text.

**Appearance → Session effects** now provides Off, Simple fade and Custom shader
modes, with CRT standby, iris and soft dissolve shaders, configurable duration,
and a preview that returns to the desktop without a session action. See
[settings layout and exit effects](SETTINGS_AND_EXIT_EFFECTS.md) for configuration,
rendering, cancellation and fallback behavior.

Validation: the desktop suite uses mocked system providers and power actions;
the preview suite checks actual headless client captures and tile swaps. Native
Wi-Fi authentication, Bluetooth pairing and authorization still need validation
on the target laptop.
