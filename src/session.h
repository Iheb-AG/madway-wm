#ifndef MADWAY_SESSION_H
#define MADWAY_SESSION_H

#include <stdbool.h>
#include <sys/types.h>
struct madway_server;

struct madway_config {
    int title_height, tile_gap, master_percent;
    int repeat_rate, repeat_delay;
    bool default_floating, use_super, focus_follows_mouse;
    float surface[4], active[4], text[4], muted[4], border[4], accent[4];
};
bool madway_session_init(struct madway_server *server);
void madway_session_finish(struct madway_server *server);
void madway_session_publish_state(struct madway_server *server);
void madway_session_menu(struct madway_server *server, double x, double y);
void madway_session_reload(struct madway_server *server);
bool madway_spawn(struct madway_server *server, char *const arguments[], pid_t *pid);
void madway_launch_kitty(struct madway_server *server);
void madway_session_start(struct madway_server *server);
void madway_session_stop(struct madway_server *server);
void madway_session_action(struct madway_server *server, const char *action);

#endif
