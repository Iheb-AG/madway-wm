#ifndef MADWAY_WINDOW_H
#define MADWAY_WINDOW_H

#include <stdbool.h>
#include <stdint.h>
#include <wlr/util/box.h>

enum madway_interactive_mode { MADWAY_NORMAL, MADWAY_MOVE, MADWAY_RESIZE, MADWAY_TILE_RESIZE };
struct madway_server;
struct madway_view;

void madway_begin_interactive(struct madway_view *view, enum madway_interactive_mode mode, uint32_t edges);
void madway_end_interactive(struct madway_server *server);
void madway_update_interactive(struct madway_server *server);
void madway_set_keep_above(struct madway_view *view, bool above);
void madway_set_minimized(struct madway_view *view, bool minimized);
void madway_set_maximized(struct madway_view *view, bool maximized);
void madway_set_fullscreen(struct madway_view *view, bool fullscreen);
void madway_arrange_views(struct madway_server *server);
void madway_apply_window_state(struct madway_view *view);
void madway_view_output_box(struct madway_view *view, struct wlr_box *box);

#endif
