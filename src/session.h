#ifndef MADWAY_SESSION_H
#define MADWAY_SESSION_H

#include <stdbool.h>
#include <sys/types.h>
struct madway_server;

struct madway_config {
    int title_height, tile_gap, master_percent;
    int repeat_rate, repeat_delay;
    int dock_animation_ms;
    bool dock_autohide, dock_animate;
    bool default_floating, use_super, focus_follows_mouse, eau, eau_dark;
    bool lid_auto;
    bool tap, tap_drag, drag_lock, dwt, touchpad_natural, mouse_natural, left_handed, middle_emulation;
    double touchpad_speed, mouse_speed;
    char accel_profile[16], click_method[16];
    char keyboard_layout[128], keyboard_variant[128], keyboard_options[256];
    bool workspace_animate;
    int workspace_animation_ms;
    bool window_animate;
    int window_animation_ms;
    float surface[4], active[4], text[4], muted[4], border[4], accent[4];
};
bool madway_session_init(struct madway_server *server);
void madway_session_finish(struct madway_server *server);
void madway_session_publish_state(struct madway_server *server);
void madway_session_menu(struct madway_server *server, double x, double y);
void madway_session_reload(struct madway_server *server);
bool madway_spawn(struct madway_server *server, char *const arguments[], pid_t *pid);
void madway_launch_terminal(struct madway_server *server);
void madway_session_start(struct madway_server *server);
void madway_session_stop(struct madway_server *server);
void madway_session_action(struct madway_server *server, const char *action);

#endif
