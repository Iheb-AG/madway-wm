#ifndef MADWAY_MONITORS_H
#define MADWAY_MONITORS_H
#include <stdbool.h>
struct madway_server;
bool madway_init_monitors(struct madway_server *server);
void madway_arrange_outputs(struct madway_server *server);
void madway_reload_outputs(struct madway_server *server);
void madway_finish_monitors(struct madway_server *server);
void madway_publish_outputs(struct madway_server *server);
#endif
