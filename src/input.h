#ifndef MADWAY_INPUT_H
#define MADWAY_INPUT_H

#include <stdbool.h>
struct madway_server;
struct wlr_surface;
void madway_reload_input(struct madway_server *server);
void madway_map_pointer_outputs(struct madway_server *server);

bool madway_init_input(struct madway_server *server);
void madway_finish_input(struct madway_server *server);
void madway_rebase_cursor(struct madway_server *server);
void madway_cancel_pointer_grab(struct madway_server *server);
void madway_discard_held_keys(struct madway_server *server);
void madway_keyboard_enter(struct madway_server *server,struct wlr_surface *surface);

#endif
