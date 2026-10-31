#ifndef MADWAY_DOCK_H
#define MADWAY_DOCK_H

#include <stdbool.h>
struct madway_server;
struct madway_layer;
struct wlr_output;
struct madway_output;
void madway_dock_frame(struct madway_output *output);
bool madway_dock_active(struct madway_output *output);
bool madway_dock_autohidden(struct madway_server *server, struct wlr_output *output);
void madway_dock_update(struct madway_layer *layer);
void madway_dock_pointer(struct madway_server *server);
void madway_dock_finish(struct madway_layer *layer);
double madway_dock_ease(double progress);

#endif
