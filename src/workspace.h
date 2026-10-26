#ifndef MADWAY_WORKSPACE_H
#define MADWAY_WORKSPACE_H

#include <stdbool.h>

#define MADWAY_WORKSPACE_COUNT 9
#define MADWAY_TILE_GAP 2

struct madway_server;
struct madway_view;

bool madway_view_visible(struct madway_view *view);
void madway_workspace_arrange(struct madway_server *server);
void madway_workspace_focus(struct madway_server *server);
void madway_workspace_switch(struct madway_server *server, unsigned workspace);
void madway_workspace_move_view(struct madway_view *view, unsigned workspace);
void madway_toggle_floating(struct madway_view *view);
void madway_cycle_focus(struct madway_server *server, bool backwards);

#endif
