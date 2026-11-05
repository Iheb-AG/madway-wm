#ifndef MADWAY_PREVIEW_H
#define MADWAY_PREVIEW_H
#include <stdint.h>
struct madway_server;
struct madway_view;
struct madway_output;
struct madway_layer;
struct wlr_buffer;
struct wlr_buffer *madway_window_snapshot(struct madway_view *view);
struct wlr_buffer *madway_window_snapshot_alpha(struct madway_view *view);
struct wlr_buffer *madway_scene_snapshot(struct madway_server *server,struct madway_output *output);
struct wlr_buffer *madway_layer_snapshot(struct madway_layer *layer);
void madway_preview_capture(struct madway_server *server);
void madway_preview_capture_one(struct madway_server *server, uint32_t identity);
void madway_preview_remove(struct madway_view *view);
void madway_preview_clear(struct madway_server *server);
#endif
