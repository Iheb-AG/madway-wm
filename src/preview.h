#ifndef MADWAY_PREVIEW_H
#define MADWAY_PREVIEW_H
struct madway_server;
struct madway_view;
struct madway_output;
struct wlr_buffer;
struct wlr_buffer *madway_window_snapshot(struct madway_view *view);
struct wlr_buffer *madway_scene_snapshot(struct madway_server *server,struct madway_output *output);
void madway_preview_capture(struct madway_server *server);
void madway_preview_remove(struct madway_view *view);
void madway_preview_clear(struct madway_server *server);
#endif
