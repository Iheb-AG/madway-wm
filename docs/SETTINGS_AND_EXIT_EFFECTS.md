# Settings browser and session exit effects

Settings uses a single searchable source list, grouped under Appearance,
Workspace, Input, Connectivity and System. Expand a group to see its pages;
other groups remain reachable in the same sidebar. Navigation preserves drafts.
A page title, short description and section headings organize the right pane.

Controls follow the selected desktop palette: gently beveled buttons, rounded
switches with white thumbs, blue or theme-colored selections, inset entries,
and consistent numeric fields. Switches and numeric fields align along the
right edge; long forms scroll without covering the footer. Search spans page
names, labels, choices and hints. Session sound paths have their own System →
Sounds page. The Settings window also opens with a short compositor fade/zoom,
controlled by the window-animation preference.

## Select an exit effect

Open **Appearance → Session effects**. Choose:

| Mode | Behavior |
| --- | --- |
| Off | Perform the confirmed action without an exit effect. |
| Simple fade | Ease the desktop into a dark charcoal surface. |
| Custom shader | Run a built-in GLSL effect over a snapshot of each monitor. |

Nine custom shaders are included:

- **CRT standby:** compress the desktop into a soft horizontal line, then a point.
- **Iris close:** close a soft circular aperture toward the center.
- **Soft dissolve:** dissolve small areas of the desktop into the dark surface.
- **Event horizon:** gravitational image warping, chromatic lensing and an accretion rim.
- **Prismatic fold:** staggered perspective-folding glass panels with lit bevels.
- **Liquid lens:** refractive ripples and a soft caustic wavefront.
- **Ember dissolve:** a fractal burn front with drifting embers and glowing edges.
- **Mechanical shutter:** seven rotating aperture blades with metal seams.
- **Aurora veil:** layered noise curtains with refractive, colored light.

The duration is configurable from 160–1600 ms (default 600 ms). Motion follows
GTK frame-clock callbacks at each output's refresh rate with the shared cubic
Bézier `(0.32, 0, 0.18, 1)`. Monitors share one start time. A small action label
appears near the end. Disabling desktop effects in Animations also skips exit
effects for actual session actions.

**Preview animation** uses the current draft controls without saving other
settings or performing logout, restart or shutdown. It returns to the desktop
with a short reveal; Escape closes the preview. Apply saves the selected effect. **Animate session opening** enables a matching
reveal at login, with its own duration and **Preview opening** button. Startup
or logon audio starts at the opening effect's animation epoch. These are session
reveals, not a bootloader or display-manager animation.

```ini
[session_effects]
mode = shader
shader = iris
duration_ms = 700
opening = true
opening_ms = 700
```

Effects run for madway-initiated logout, restart and shutdown, including
Alt+Escape/Super+Escape when desktop services are running. Existing confirmation
cards still appear before panel/settings power actions. Forced process termination,
closing the outer nested window, and shutdown already initiated elsewhere do not
wait for a new effect.

## Rendering and failure handling

The renderer is a separate GtkLayerShell client with one overlay per monitor.
Simple fades use Cairo. Shaders use Gtk.GLArea and the GLES2 interface, with a
GLSL 150 variant for desktop GL contexts. Built-in vertex/fragment sources live
in `share/madway/shaders`; no Python OpenGL package or new compositor renderer is
required. A missing GL library, failed context/program, or unavailable capture
falls back to the software fade.

Only shader mode captures desktop images. `grim` captures enabled outputs before
any overlay maps, into process memory; no screenshot files are written. Captures
are downscaled to at most 1600 pixels on the longest side and the decoded image
budget is 64 MiB. A monitor without a usable snapshot still receives a fade.
Textures and snapshots are released when their overlay is destroyed.

Sound and animation begin from the same start message, after the renderer is
ready. The controller waits for both concurrently, so closing takes approximately
the longer of the animation or sound, rather than their combined duration. A
sound is played once, is canceled with the exit, and remains bounded to eight
seconds if the playback process stalls. Disabled effects still permit sound.

The renderer cannot run a power command. After a short final-frame hold, it sends
a one-use token to the desktop controller, which performs the previously
requested action when concurrent sound playback has also completed. Duplicate pending requests and stale completion messages are
ignored. Canceling with Escape, locking, sleep or a topology change cancels the
pending effect/action. A crashed or stalled renderer is bounded by a watchdog,
which proceeds with the already-requested action. If that action fails, overlays
are removed and the error is reported. An orphaned overlay also has a bounded
lifetime. Existing system permissions still govern power operations.

The settings preview does not require a controller token and never requests a
system operation. To try a renderer directly from a madway terminal:

```sh
python3 /usr/local/bin/madway_exit.py --preview --mode shader --shader crt
```

## Validation

- `tests/settings_redesign_ui.py`: grouped navigation/search, retained drafts,
  preview without saving, persisted exit options and compact bounds on all pages.
- `tests/session_exit.py`: controller tokens, duplicate requests, reduced motion,
  process-reaper cancellation race, watchdog, privacy and rejected-action cleanup.
- `tests/session_shader_ui.py`: actual GL compilation, first/middle/final image
  checks, full-screen previews, and disabled-GL software fallback.
- `tests/session_exit_integration.py`: real effects on two private 100/60 Hz
  outputs, mocked rejected power requests, restored desktops, and private logout.

All integration tests use temporary homes and private Wayland outputs. Their
power commands are local stubs; they never shut down the host. Native graphics
behavior still needs validation on the target laptop.
