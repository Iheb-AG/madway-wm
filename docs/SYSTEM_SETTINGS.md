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
standalone installation may also need a Polkit authentication agent supplied by
the distribution. Madway does not bundle a complete policy/portal environment.
The date/time editor likewise uses an installed Plasma or GNOME settings module;
changing the system clock still requires the system's usual authorization.

## Default applications

Choose an application and press **Set** in that row. This writes the corresponding
GIO/MIME preference immediately; opening the page makes no association changes.
The browser row sets both HTTP and HTTPS. This page does not change madway's
Konsole terminal shortcut. Shell layout preferences elsewhere still use Apply.

## Panel previews and calendar

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
