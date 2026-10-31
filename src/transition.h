#ifndef MADWAY_TRANSITION_H
#define MADWAY_TRANSITION_H
#include <stdbool.h>
struct madway_server;
struct madway_output;
void madway_transition_frame(struct madway_output *output,double now);
bool madway_transition_active(struct madway_output *output);
void madway_transition_prepare(struct madway_server *server,unsigned target);
void madway_transition_start(struct madway_server *server);
void madway_transition_finish(struct madway_server *server);
void madway_transition_cancel_running(struct madway_server *server);
#endif
