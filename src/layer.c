#include "layer.h"
#include "main.h"
#include "view.h"
#include "input.h"
#include "workspace.h"

#include <stdlib.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/util/log.h>

void madway_layer_focus(struct madway_layer *layer)
{
    struct madway_server *server = layer->server;
    if (!layer->mapped || !layer->surface->output->enabled || layer->surface->current.keyboard_interactive ==
            ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_NONE) return;
    server->keyboard_layer = layer;
    struct wlr_keyboard *keyboard = wlr_seat_get_keyboard(server->seat);
    struct wlr_keyboard_modifiers modifiers = {0};
    wlr_seat_keyboard_notify_enter(server->seat, layer->surface->surface,
            keyboard != NULL ? keyboard->keycodes : NULL,
            keyboard != NULL ? keyboard->num_keycodes : 0,
            keyboard != NULL ? &keyboard->modifiers : &modifiers);
}

static void restore_focus(struct madway_server *server)
{
    if (server->shutting_down) return;
    struct madway_layer *layer;
    wl_list_for_each_reverse(layer, &server->layers, link)
        if (layer->mapped && layer->surface->output->enabled && layer->surface->current.layer >= ZWLR_LAYER_SHELL_V1_LAYER_TOP &&
            layer->surface->current.keyboard_interactive == ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_EXCLUSIVE)
        { madway_layer_focus(layer); return; }
    if (server->focused_view != NULL && madway_view_visible(server->focused_view))
        madway_focus_view(server, server->focused_view);
    else madway_workspace_focus(server);
}

void madway_arrange_layers(struct madway_server *server)
{
    if (server->shutting_down) return;
    struct madway_layer *entry;
    wl_list_for_each(entry, &server->layers, link)
        wlr_scene_node_set_enabled(&entry->tree->node, entry->mapped && entry->surface->output->enabled);
    if (server->keyboard_layer != NULL && !server->keyboard_layer->surface->output->enabled)
    {
        server->keyboard_layer = NULL;
        wlr_seat_keyboard_notify_clear_focus(server->seat);
    }
    struct madway_output *output;
    wl_list_for_each(output, &server->outputs, link)
    {
        if (!output->output->enabled) continue;
        int width, height;
        wlr_output_effective_resolution(output->output, &width, &height);
        struct wlr_box full = {output->scene_output->x, output->scene_output->y, width, height};
        struct wlr_box usable = full;
        // Reserve panels before positioning non-exclusive notifications/launchers.
        for (int exclusive = 1; exclusive >= 0; --exclusive)
            for (int index = 3; index >= 0; --index)
            {
                struct madway_layer *layer;
                wl_list_for_each(layer, &server->layers, link)
                {
                    struct wlr_layer_surface_v1 *surface = layer->surface;
                    if (surface->output != output->output || !surface->initialized ||
                        (int)surface->current.layer != index ||
                        (surface->current.exclusive_zone > 0) != exclusive) continue;
                    wlr_scene_node_reparent(&layer->tree->node, server->layer_trees[index]);
                    struct wlr_box proposed = usable;
                    wlr_scene_layer_surface_v1_configure(layer->scene_layer, &full, &proposed);
                    if (layer->mapped || surface->initial_commit) usable = proposed;
                }
            }
        output->usable_area = usable;
    }
}

static void handle_layer_commit(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_layer *layer = wl_container_of(listener, layer, commit);
    if (layer->surface->initial_commit || layer->surface->current.committed != 0)
    {
        madway_arrange_layers(layer->server);
        madway_workspace_arrange(layer->server);
        if (layer->server->keyboard_layer == layer &&
            layer->surface->current.keyboard_interactive == ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_NONE)
        {
            layer->server->keyboard_layer = NULL;
            restore_focus(layer->server);
        }
        if (layer->mapped && layer->surface->current.layer >= ZWLR_LAYER_SHELL_V1_LAYER_TOP &&
            layer->surface->current.keyboard_interactive ==
            ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_EXCLUSIVE)
            madway_layer_focus(layer);
    }
}

static void handle_layer_map(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_layer *layer = wl_container_of(listener, layer, map);
    layer->mapped = true;
    wlr_scene_node_set_enabled(&layer->tree->node, true);
    madway_arrange_layers(layer->server);
    madway_workspace_arrange(layer->server);
    if (layer->surface->current.layer >= ZWLR_LAYER_SHELL_V1_LAYER_TOP &&
        layer->surface->current.keyboard_interactive == ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_EXCLUSIVE)
        madway_layer_focus(layer);
    madway_rebase_cursor(layer->server);
    wlr_log(WLR_INFO, "Desktop layer mapped: %s", layer->surface->namespace);
}

static void handle_layer_unmap(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_layer *layer = wl_container_of(listener, layer, unmap);
    layer->mapped = false;
    wlr_scene_node_set_enabled(&layer->tree->node, false);
    if (layer->server->keyboard_layer == layer)
    {
        layer->server->keyboard_layer = NULL;
        restore_focus(layer->server);
    }
    madway_arrange_layers(layer->server);
    madway_workspace_arrange(layer->server);
}

static void handle_layer_destroy(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_layer *layer = wl_container_of(listener, layer, destroy);
    struct madway_server *server = layer->server;
    layer->mapped = false;
    if (server->keyboard_layer == layer) { server->keyboard_layer = NULL; restore_focus(server); }
    wl_list_remove(&layer->commit.link);
    wl_list_remove(&layer->map.link);
    wl_list_remove(&layer->unmap.link);
    wl_list_remove(&layer->destroy.link);
    wl_list_remove(&layer->new_popup.link);
    wl_list_remove(&layer->link);
    wlr_scene_node_destroy(&layer->tree->node);
    free(layer);
    madway_arrange_layers(server);
    madway_workspace_arrange(server);
}

static void handle_layer_popup(struct wl_listener *listener, void *data)
{
    struct madway_layer *layer = wl_container_of(listener, layer, new_popup);
    madway_add_popup_scene(layer->server, data, layer->scene_layer->tree);
}

static void handle_new_layer(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, new_layer);
    struct wlr_layer_surface_v1 *surface = data;
    if (surface->output == NULL && server->cursor != NULL)
        surface->output = wlr_output_layout_output_at(server->output_layout, server->cursor->x, server->cursor->y);
    if (surface->output == NULL) surface->output = wlr_output_layout_get_center_output(server->output_layout);
    if (surface->output == NULL) { wlr_layer_surface_v1_destroy(surface); return; }
    struct madway_layer *layer = calloc(1, sizeof(*layer));
    if (layer == NULL) { wl_client_post_no_memory(wl_resource_get_client(surface->resource)); return; }
    layer->server = server;
    layer->surface = surface;
    layer->tree = wlr_scene_tree_create(server->layer_trees[surface->pending.layer]);
    if (layer->tree != NULL)
        layer->scene_layer = wlr_scene_layer_surface_v1_create(layer->tree, surface);
    if (layer->scene_layer == NULL)
    {
        if (layer->tree != NULL) wlr_scene_node_destroy(&layer->tree->node);
        free(layer);
        wl_client_post_no_memory(wl_resource_get_client(surface->resource));
        return;
    }
    wl_list_insert(server->layers.prev, &layer->link);
    layer->tree->node.data = layer;
    wlr_scene_node_set_enabled(&layer->tree->node, false);
    layer->commit.notify = handle_layer_commit;
    wl_signal_add(&surface->surface->events.commit, &layer->commit);
    layer->map.notify = handle_layer_map;
    wl_signal_add(&surface->surface->events.map, &layer->map);
    layer->unmap.notify = handle_layer_unmap;
    wl_signal_add(&surface->surface->events.unmap, &layer->unmap);
    layer->destroy.notify = handle_layer_destroy;
    wl_signal_add(&surface->events.destroy, &layer->destroy);
    layer->new_popup.notify = handle_layer_popup;
    wl_signal_add(&surface->events.new_popup, &layer->new_popup);
}

bool madway_init_layers(struct madway_server *server)
{
    server->layer_shell = wlr_layer_shell_v1_create(server->display, 4);
    if (server->layer_shell == NULL) return false;
    server->new_layer.notify = handle_new_layer;
    wl_signal_add(&server->layer_shell->events.new_surface, &server->new_layer);
    for (int i = 0; i < 4; ++i)
    {
        server->layer_trees[i] = wlr_scene_tree_create(&server->scene->tree);
        if (server->layer_trees[i] == NULL) return false;
        if (i < 2) wlr_scene_node_place_below(&server->layer_trees[i]->node, &server->windows->node);
    }
    return true;
}

void madway_layer_output_destroy(struct madway_server *server, struct wlr_output *output)
{
    struct madway_layer *layer, *tmp;
    wl_list_for_each_safe(layer, tmp, &server->layers, link)
        if (layer->surface->output == output) wlr_layer_surface_v1_destroy(layer->surface);
}

struct madway_layer *madway_layer_at(struct madway_server *server, bool above_windows,
        double x, double y, struct wlr_surface **surface, double *sx, double *sy)
{
    for (int i = above_windows ? 3 : 1; i >= (above_windows ? 2 : 0); --i)
    {
        struct wlr_scene_node *node = wlr_scene_node_at(&server->layer_trees[i]->node, x, y, sx, sy);
        if (node == NULL || node->type != WLR_SCENE_NODE_BUFFER) continue;
        struct wlr_scene_surface *scene = wlr_scene_surface_try_from_buffer(wlr_scene_buffer_from_node(node));
        if (scene == NULL) continue;
        *surface = scene->surface;
        while (node != NULL && node->data == NULL) node = node->parent != NULL ? &node->parent->node : NULL;
        return node != NULL ? node->data : NULL;
    }
    return NULL;
}
