#ifndef MADWAY_LAYER_H
#define MADWAY_LAYER_H

#include <stdbool.h>
#include <wayland-server-core.h>
#include <wlr/types/wlr_layer_shell_v1.h>
#include <wlr/types/wlr_scene.h>

struct madway_server;
struct madway_layer
{
    struct madway_server *server;
    struct wlr_layer_surface_v1 *surface;
    struct wlr_scene_tree *tree;
    struct wlr_scene_layer_surface_v1 *scene_layer;
    struct wl_list link;
    struct wl_listener commit, map, unmap, destroy, new_popup;
    bool mapped;
    struct madway_dock *dock;
};

bool madway_init_layers(struct madway_server *server);
bool madway_arrange_layers(struct madway_server *server);
void madway_layer_output_destroy(struct madway_server *server, struct wlr_output *output);
void madway_layer_focus(struct madway_layer *layer);
struct madway_layer *madway_layer_at(struct madway_server *server, bool above_windows,
        double x, double y, struct wlr_surface **surface, double *sx, double *sy);

#endif
