#ifndef MADWAY_LOCK_H
#define MADWAY_LOCK_H
#include <stdbool.h>
#include <sys/types.h>
struct madway_server;
struct madway_output;
struct wlr_surface;
struct wlr_output_state;
bool madway_lock_init(struct madway_server *server);
void madway_lock_finish(struct madway_server *server);
bool madway_lock_add_output(struct madway_output *output);
void madway_lock_remove_output(struct madway_output *output);
void madway_lock_arrange(struct madway_server *server);
void madway_lock_focus(struct madway_server *server,struct wlr_surface *surface);
struct wlr_surface *madway_lock_at(struct madway_server *server,double x,double y,double *sx,double *sy);
void madway_lock_blank(struct madway_server *server);
void madway_lock_request(struct madway_server *server,unsigned serial);
unsigned madway_lock_request_serial(struct madway_server *server);
void madway_lock_authorize(struct madway_server *server,pid_t pid);
bool madway_lock_ready(struct madway_server *server);
pid_t madway_lock_client_pid(struct madway_server *server);
bool madway_lock_secure_output(struct madway_output *output,struct wlr_output_state *state);
#endif
