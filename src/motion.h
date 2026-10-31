#ifndef MADWAY_MOTION_H
#define MADWAY_MOTION_H
#include <stdbool.h>
struct madway_server;
struct madway_view;
struct madway_output;
void madway_motion_frame(struct madway_output *output,double now);
bool madway_motion_active(struct madway_output *output);
void madway_motion_commit(struct madway_view *view);
void madway_motion_prepare(struct madway_view *view);
void madway_motion_start(struct madway_view *view,bool minimizing,bool restoring);
void madway_motion_finish(struct madway_server *server);
void madway_motion_cancel_running(struct madway_server *server);
void madway_motion_focus(struct madway_server *server,struct madway_view *view);
#endif
