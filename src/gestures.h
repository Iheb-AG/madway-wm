#ifndef MADWAY_GESTURES_H
#define MADWAY_GESTURES_H
#include <stdbool.h>
struct madway_server;
struct wlr_pointer;
bool madway_gestures_init(struct madway_server *server);
void madway_gestures_finish(struct madway_server *server);
void madway_gestures_cancel(struct madway_server *server);
void madway_gestures_remove_pointer(struct madway_server *server,struct wlr_pointer *pointer);
#endif
