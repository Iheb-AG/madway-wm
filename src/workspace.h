#ifndef MADWAY_WORKSPACE_H
#define MADWAY_WORKSPACE_H

#include <stdbool.h>
#include <stdint.h>

#define MADWAY_WORKSPACE_COUNT 9
#define MADWAY_TILE_GAP 1

struct madway_server;
struct madway_view;

bool madway_view_visible(struct madway_view *view);
void madway_workspace_arrange(struct madway_server *server);
void madway_workspace_focus(struct madway_server *server);
void madway_workspace_switch(struct madway_server *server, unsigned workspace);
void madway_workspace_move_view(struct madway_view *view, unsigned workspace);
void madway_toggle_floating(struct madway_view *view);
bool madway_tile_resize_begin(struct madway_view *view, uint32_t edges);
void madway_tile_resize_update(struct madway_server *server, int dx, int dy);
void madway_move_tile(struct madway_server *server, const char *direction);
void madway_switcher_step(struct madway_server *server, bool backwards);
void madway_switcher_finish(struct madway_server *server, bool cancel);
void madway_cycle_focus(struct madway_server *server, bool backwards);

#endif
