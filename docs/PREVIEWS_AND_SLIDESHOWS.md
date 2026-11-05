# Window previews, compact task entries and wallpaper slideshows

## Alt+Tab previews

Hold Alt and press Tab to open a floating grid of window images on the focused output.
Only windows on that output's current workspace appear, including minimized ones.
Tab cycles forward, Shift+Tab cycles backward, releasing Alt accepts the
selection, and Escape cancels it. With Super selected as the shortcut modifier,
use Super instead of Alt. Clicking a card also selects its window.

The switcher uses a rounded surface, larger preview cards, application icons,
two-level app/title captions and an accent outline for the selection. A compact
footer shows the selected window title, position and active modifier. Cycling
updates the selection in place, retaining the cards and scroll position.

Each card contains a scaled image of that window and its title. Previews
refresh when the switcher opens. Covered windows are rendered independently;
minimized applications use their last committed content. A minimized label
remains visible on its card until the window is restored. The grid scrolls to
the selected row when it contains more windows than fit on the output.

The compositor renders the window's own scene subtree into a 480×300 buffer,
preserving the aspect ratio and including client subsurfaces and decorations.
It reads back only the small preview image. Window shadows and neighboring
applications are excluded. GTK displays the resulting images at up to 228×144
logical pixels, with scale-aware image loading for HiDPI outputs. Smaller outputs
reduce the preview size and column count; large window lists scroll vertically.
If a buffer cannot be captured/read back, the card remains usable with an
application fallback icon. Rendering is validated with the Pixman backend;
physical GPU readback still needs validation on the target system.

PNG files are owner-readable only, under
`$XDG_RUNTIME_DIR/madway-$WAYLAND_DISPLAY/previews/`. A window's preview is
deleted on unmap/destruction. All previews are removed on lock, compositor
shutdown, and initialization of a replacement session. Capture is refused
while locked or sleeping. Previews are absent from installed data and Git.

## Application and command search

**Alt+D** opens the Spotlight-style application search; **Alt+Shift+D** opens
command search. Application search is a native GTK layer-shell popup; command
search continues to use Wofi. Application
results include 28px icons, soft accent selections and rounded rows below a
larger, unboxed search field. Light, Midnight and other themes share the layout
while retaining their palettes. Overlay styling is separate from dropdown-menu
styling, so the launcher no longer inherits Argent's small pill-shaped entry.

The default width is about 560 logical pixels, with up to seven results.
The helper chooses the active output and reduces width/result count for smaller
or scaled/rotated outputs. Filtering shrinks the surface to the remaining rows.
Escape dismisses it and Enter launches the selection, as before.
Prefix matches show a faint grey suffix after the text cursor. This is a visual
suggestion, separate from the editable query: **Tab** or **Right** accepts it.
It disappears during IME composition, selection or editing inside the query.
Substring matching still works without an invented completion. **Settings →
Launcher → Inline autocomplete / Suggestion opacity (%)** controls it.
Opening fades and lifts the surface into place; closing fades a compositor-owned
image out without delaying application launch. **Animations → Desktop effects** and **Launcher animation (ms)** control this effect.

## Panel task entries

Under **Settings → Panel → Taskbar entries**, choose:

- **Icons only** (default): compact application icons with the full title in
  the tooltip.
- **Application names only**: names resolved from desktop entries/app IDs,
  without an accompanying icon. Separate windows from one application retain
  separate entries; their tooltips identify the window.

Both modes start after the workspace number and use the available panel space.
Clicking the focused entry minimizes it; clicking an inactive or minimized
entry focuses/restores it. Vertical panels rotate name labels, while icon
entries remain upright.

Right-click a panel task or running dock icon to open its application menu.
**Keep in Dock** saves the installed application's desktop entry; **Remove from
Dock** unpins it. Pinned icons remain after the last window closes, launch the
application when stopped, and activate an existing window when running. Choose
**Open another window** for another instance. Apps without an identifiable
installed desktop entry cannot be pinned. Pins are stored in `[dock] pinned` as
a JSON list of desktop-entry IDs. The dock continues to use Waybar.

Each panel and dock task list follows its own monitor's current workspace.

The Audio dropdown uses two rows per device/application: name, default-device
action and mute toggle above a slider with a separate percentage column. Its
opaque themed surface keeps values readable; long names ellipsize with full
tooltips. Long lists have a visible scrollbar and open on complete device rows,
while **Audio options…** stays outside the scrolling area. Validate this layout
with `dbus-run-session -- python3 tests/audio_menu.py` (mock audio, private display).

## Wallpaper slideshow

In **Settings → Wallpaper**:

1. Turn on **Enable slideshow** (this selects the Slideshow background mode).
2. Choose **Slideshow source**: **Folder** or **Selected images**.
3. Browse to a folder, or use **Add images…** to select multiple files. Remove
   individual selected files with ×, or use **Clear** to replace the selection.
4. Set **Change image every (seconds)**, from 1 to 86400 seconds.
5. Choose the fit mode, then Apply. **Next slideshow image** saves settings and
   advances the slideshow.

Turn **Enable slideshow** off and Apply to pause rotation while keeping the
current image, selected folder/files and interval. Turn it back on to resume.
Next-image preview is disabled while paused. You can edit the selection while
paused; an empty selection uses the solid background color until configured.

Folder mode uses readable images directly inside that directory in filename
order. Selected-image mode preserves the saved list order and removes
duplicates. The folder/list is checked again on rotation, so added images are
included and deleted or unreadable files are skipped. An empty collection
temporarily uses the configured solid background color and recovers when
images become available again. The status field reports the current image,
image count, or an error.

All monitors advance together. The previous swaybg process remains alive until
the replacement has finished fading in on every active output. A failed or
timed-out replacement keeps the previous background. Rapid image changes queue
the latest selection until the current fade finishes. Switching to a solid color or a single image stops
slideshow scheduling. Lock and sleep pause rotation.

Single-image and solid-color changes use the same crossfade. Configure it with
**Animations → Desktop effects** and **Wallpaper fade (ms)**
(650 ms by default). Media indicators use a frame-clock-driven value animation
(180 ms by default); repeated volume/brightness keys retarget from the visible
value. The indicator is kept warm while hidden and appears at full opacity on
its first frame, without an entrance fade. Volume/brightness commands are
serialized on a worker thread: the requested level appears immediately from the
last known value, then hardware confirmation corrects it if needed. An unknown
initial level briefly shows an ellipsis. Monitor changes reuse the same process.
**Media indicator animation (ms)** adjusts the feedback duration.

The personal settings file stores the folder or selected paths. Image files
are read from their existing locations; they are not copied into madway's
installation or repository.

Example personal configuration:

```ini
[panel]
tasks = icons

[wallpaper]
type = slideshow
slideshow_enabled = true
source = folder
folder = /home/you/Pictures/Wallpapers
images = []
interval = 300
mode = fill
color = #000000
```

For a selected list, use `source = files` and a JSON array such as
`images = ["/home/you/Pictures/one.png", "/home/you/Pictures/two.jpg"]`.

## Validation

```sh
cmake --build build
dbus-run-session -- python3 tests/wallpaper.py
dbus-run-session -- python3 tests/preview_slideshow.py
dbus-run-session -- python3 tests/desktop_smoke.py
dbus-run-session -- python3 tests/lock_smoke.py
python3 tests/installer_smoke.py
```

The tests use temporary settings, synthetic images, private D-Bus sessions and
headless displays. They verify distinct real window pixels for obscured and
minimized clients, selection/cancel behavior, actual GTK panel modes, settings
handlers for both slideshow sources, live rotation, all-output handoff,
missing-file recovery, timer cleanup and lock-time preview deletion.
