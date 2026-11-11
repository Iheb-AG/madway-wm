#ifndef MADWAY_STARTUP_H
#define MADWAY_STARTUP_H
#include <stdbool.h>
struct madway_server;
bool madway_startup_init(struct madway_server *server);
void madway_startup_arrange(struct madway_server *server);
void madway_startup_check(struct madway_server *server);
void madway_startup_request(struct madway_server *server);
void madway_startup_release(struct madway_server *server);
void madway_startup_finish(struct madway_server *server);
#endif
