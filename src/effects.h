#ifndef MADWAY_EFFECTS_H
#define MADWAY_EFFECTS_H
#include <stdbool.h>
struct madway_server;
struct madway_output;
struct madway_layer;
void madway_effects_init(struct madway_server *server);
void madway_effects_map(struct madway_layer *layer);
void madway_effects_commit(struct madway_layer *layer);
void madway_effects_unmap(struct madway_layer *layer);
void madway_effects_drop(struct madway_layer *layer);
void madway_effects_frame(struct madway_output *output,double now);
bool madway_effects_active(struct madway_output *output);
void madway_effects_cancel(struct madway_server *server);
void madway_effects_output_destroy(struct madway_output *output);
#endif
