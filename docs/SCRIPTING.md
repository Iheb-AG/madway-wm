# Madway command files

`madway-script` runs a small, line-oriented command language. Run it from a
terminal inside madway so it inherits that session's Wayland socket:

```sh
madway-script --check examples/workstation.madway
madway-script examples/workstation.madway
```

From a source checkout, use `./scripts/madway-script`. Installed sessions include
it on PATH. A file at `~/.config/madway/startup.madway` runs once when the desktop
helper starts. Creating this file opts into running its commands at login; no
startup command file is installed automatically.

| Syntax | Behaviour |
| --- | --- |
| `exec kitty --title "Work terminal"` | Start a program with literal arguments |
| `workspace 2` | Select workspace 1–9 |
| `move 3` | Move the focused window to workspace 3 |
| `window toggle-floating` | Toggle the focused window between floating and tiled |
| `window maximize` / `window fullscreen` | Toggle the focused window's state |
| `window toggle-above` | Toggle keeping the focused window above other applications |
| `window close` | Request that the focused window close |
| `tile left` / `right` / `up` / `down` | Reorder the focused tile on its current output |
| `theme amber` | Save and apply a named theme |
| `background color #101010` | Select and save a solid background |
| `background image "wall paper.png" fit` | Select an image relative to the command file |
| `set input.focus_follows_mouse true` | Save a supported setting |
| `wait 200` | Wait 200 milliseconds (0–60000) |

Empty lines and lines starting with `#` are ignored. Quotes group arguments;
`#RRGGBB` colour values are preserved. Inline comments, variables, loops, pipes,
redirection, and shell expansion are not part of this language. `exec` uses an
argument list rather than a shell. All lines are parsed and validated before
execution; `--check` performs only that validation.

Supported `set` keys:

| Key | Values |
| --- | --- |
| `panel.position` | `top`, `bottom`, `left`, `right` |
| `appearance.theme` | `black`, `amber`, `terminal`, `slate`, `paper` |
| `appearance.title_height` | 12–24 |
| `appearance.tile_gap` | 0–12 |
| `windows.default_mode` | `floating`, `tiled` (new windows) |
| `windows.master_percent` | 25–75 |
| `input.focus_follows_mouse` | `true`, `false` |
| `input.modifier` | `alt`, `super` |
| `input.repeat_rate` | 1–100 |
| `input.repeat_delay` | 100–1500 milliseconds |
| `wallpaper.type` | `color`, `image` |
| `wallpaper.path` | Existing image path |
| `wallpaper.color` | `#RRGGBB` |
| `wallpaper.mode` | `fill`, `fit`, `center`, `stretch`, `tile` |

Settings commands update your personal settings file and apply live. Window
commands act on the window focused when the compositor receives the command.
Programs launch asynchronously; `exec` followed by a window command does not
wait for that program to create a window. Use Kitty's own arguments or explicit
focus before window operations. A timed `wait` can assist simple workflows but
is not a window-readiness guarantee. Runtime failures are reported in the
terminal/helper log, and preceding commands are not rolled back.

Tiling uses a master column and stack column per output. `left` promotes a stack
window to master; `right` swaps the master with the first stack window. `up` and
`down` reorder stack windows. At a column edge they do nothing. These commands
retain focus and do not move windows across monitors or workspaces.
