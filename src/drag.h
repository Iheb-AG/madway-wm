#ifndef MADWAY_DRAG_H
#define MADWAY_DRAG_H
#include <stdbool.h>
struct madway_server;
bool madway_drag_init(struct madway_server *server);
void madway_drag_finish(struct madway_server *server);
void madway_drag_update(struct madway_server *server);
void madway_drag_cancel(struct madway_server *server);
#endif
