# Window previews, compact task entries and wallpaper slideshows

## Alt+Tab previews

Hold Alt and press Tab to open a grid of window images on the focused output.
Tab cycles forward, Shift+Tab cycles backward, releasing Alt accepts the
selection, and Escape cancels it. With Super selected as the shortcut modifier,
use Super instead of Alt. Clicking a card also selects its window.

Each card contains a scaled image of that window and its title. Previews
refresh when the switcher opens. Covered windows are rendered independently;
minimized applications use their last committed content. A minimized label
remains visible on its card until the window is restored. The grid scrolls to
the selected row when it contains more windows than fit on the output.

The compositor renders the window's own scene subtree into a 240×160 buffer,
preserving the aspect ratio and including client subsurfaces and decorations.
It reads back only the small preview image. Window shadows and neighboring
applications are excluded. GTK displays the resulting images at 192×128.
If a buffer cannot be captured/read back, the card remains usable with an
application fallback icon. Rendering is validated with the Pixman backend;
physical GPU readback still needs validation on the target system.

PNG files are owner-readable only, under
`$XDG_RUNTIME_DIR/madway-$WAYLAND_DISPLAY/previews/`. A window's preview is
deleted on unmap/destruction. All previews are removed on lock, compositor
shutdown, and initialization of a replacement session. Capture is refused
while locked or sleeping. Previews are absent from installed data and Git.

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

## Wallpaper slideshow

In **Settings → Appearance**:

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
the replacement has mapped a background on every active output. A failed or
timed-out replacement keeps the previous background. Settings changes cancel
outdated handoffs/timers, and switching to a solid color or a single image stops
slideshow scheduling. Lock and sleep pause rotation.

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
