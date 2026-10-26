#ifndef MADWAY_SESSION_H
#define MADWAY_SESSION_H

#include <stdbool.h>
#include <sys/types.h>
struct madway_server;

struct madway_config { int title_height, tile_gap; };
void madway_session_reload(struct madway_server *server);
bool madway_spawn(struct madway_server *server, char *const arguments[], pid_t *pid);
void madway_launch_kitty(struct madway_server *server);
void madway_session_start(struct madway_server *server);
void madway_session_stop(struct madway_server *server);
void madway_session_action(struct madway_server *server, const char *action);

#endif
