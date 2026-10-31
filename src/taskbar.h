#ifndef MADWAY_TASKBAR_H
#define MADWAY_TASKBAR_H

#include <stdbool.h>
struct madway_server;
struct madway_view;
bool madway_taskbar_init(struct madway_server *server);
void madway_taskbar_sync(struct madway_server *server);
void madway_taskbar_remove(struct madway_view *view);

#endif
