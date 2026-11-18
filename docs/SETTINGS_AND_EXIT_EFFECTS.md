# Settings browser and session exit effects

Settings uses one searchable source list under Appearance, Workspace, Input,
Connectivity and System. All page categories stay visible in the scrolling list;
there are no expanding group tabs. The reference-style sidebar uses aligned colored
category icons and a rounded selection. Back/forward navigation and search preserve
draft edits. Each page has an icon/title summary and compact row cards grouped by
section. Controls use small switches and single-outline fields. Long forms scroll
above a fixed footer, with a compact page summary. Light, dark
and the separate Prism glass preset share the same layout.

Session sound paths live under System → Sounds. Microphone and Camera pages are
under Input. The Settings window keeps its compositor opening animation.

## Panel dropdown animation

Panel menus (applications/user menu, workspaces, window actions, volume, calendar,
battery, session and timer controls) fade and expand gently from their panel edge.
Cascading menus reveal toward the available side; a cascade near the right edge
opens to the left while its parent remains anchored. Submenu replacement cancels
the previous reveal, so quick hovering never leaves a delayed menu behind.

The default is 240 ms with a responsive cubic Bézier `(0.2, 0.8, 0.2, 1)` settle.
GTK frame-clock callbacks follow the monitor's refresh cadence, including 100 Hz;
no animation timer runs after completion. The live widgets retain their final
allocation: text and sliders are not resized between frames. The reveal mask and
Wayland input region stay in sync, so hidden portions do not catch clicks.
Keyboard navigation finishes the reveal immediately and retains its usual focus.

Set **Appearance → Animations → Panel menu animation (ms)** (80–600 ms), or turn
**Desktop effects** off for immediate menus. This uses `motion.menu_ms` and the
existing `motion.effects` preference. Media-key volume/brightness feedback keeps
its own path and timing. Menus dismiss immediately on outside click or Escape;
only their appearance/page/cascade reveals animate.

Validation uses private 100 Hz outputs, intermediate opacity/reveal frames,
unchanged form geometry, input-mask checks, all panel edges, rapid submenu
replacement, corner anchoring and disabled-effect behavior.

## Select an exit effect

Open **Appearance → Session effects**. Choose:

| Mode | Behavior |
| --- | --- |
| Off | Perform the confirmed action without an exit effect. |
| Simple fade | Ease the desktop into a dark charcoal surface. |
| Custom shader | Run a built-in GLSL effect over a snapshot of each monitor. |

Thirteen shaders are included:

- **CRT standby:** compress the desktop into a soft horizontal line, then a point.
- **Iris close:** close a soft circular aperture toward the center.
- **Soft dissolve:** dissolve small areas of the desktop into the dark surface.
- **Event horizon:** gravitational image warping, chromatic lensing and an accretion rim.
- **Prismatic fold:** staggered perspective-folding glass panels with lit bevels.
- **Liquid lens:** refractive ripples and a soft caustic wavefront.
- **Ember dissolve:** a fractal burn front with drifting embers and glowing edges.
- **Mechanical shutter:** seven rotating aperture blades with metal seams.
- **Aurora veil:** layered noise curtains with refractive, colored light.
- **Zoom defocus · GPUImage:** multi-tap radial defocus toward the center.
- **Polar crystal · GPUImage:** concentric angular pixelization.
- **Pinch lens · GPUImage:** aspect-correct center-lens distortion.
- **Crosshatch raster · GPUImage:** luminance-weighted diagonal hatch rendering.

The four GPUImage filters are adapted from Brad Larson's BSD-licensed GPUImage2,
with pinned source links in [shader provenance](../share/madway/shaders/SOURCES.md)
and its shipped license. No GL Transitions effects are included.

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
reveals, not a bootloader or display-manager animation. The compositor covers all
outputs before their first desktop frame. Wallpaper/services prepare underneath;
once every opening pane has painted, it hands off the cover and starts audio at
the shared reveal epoch. Opening shaders capture the desktop beneath the cover
through bounded private snapshots, which the renderer removes after loading.
Failure, cancellation and a bounded timeout release the cover.

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

## Application audio during exit

After confirmation, the helper quiets application playback streams before starting
an effect. At the shared visual/audio epoch, it sends graceful close requests to
normal application windows. The session player is explicitly tagged and exempt;
the output device and microphone are not muted. New playback streams are isolated
until the action finishes. Nested sessions only quiet streams belonging to their
client processes, leaving the host desktop's playback alone.

Isolation routes eligible streams into a disposable `module-null-sink` output;
it never changes application mute or volume. The previous approach could leave a
closed browser's mute flag remembered by the audio server. Temporary outputs are
not selected as the default and have low session priority. If the audio backend
cannot create one, madway logs the failure and continues without isolation.

If applications remain open, including an unsaved-work dialog, exit is cancelled
after a short grace period. Escape, locking, rejected power actions and the audio
guard watchdog restore surviving streams to their original outputs and unload
the temporary output. An output that disappeared falls back to the current default.
Changed stream identities and user-selected new routes are respected. Session
teardown waits for cleanup; the next native startup also removes abandoned madway
outputs whose owner process has died. Already
closed applications are not relaunched. A preview never closes apps or isolates
playback. Animation and sound still run concurrently.
