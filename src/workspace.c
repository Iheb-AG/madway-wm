#include "workspace.h"

#include "main.h"
#include "view.h"
#include "window.h"
#include "decoration.h"
#include "input.h"
#include "session.h"
#include "layer.h"
#include <string.h>
#include <wlr/util/edges.h>
#include <wlr/util/log.h>

bool madway_view_visible(struct madway_view *view)
{
    return view->mapped && view->workspace == view->server->active_workspace;
}

static struct madway_view *fullscreen_on(struct madway_server *server, struct madway_output *output)
{
    struct madway_view *view;
    wl_list_for_each_reverse(view, &server->views, link)
        if (madway_view_visible(view) && view->output == output && view->fullscreen)
            return view;
    return NULL;
}

static bool is_tile(struct madway_view *view, struct madway_output *output)
{
    return madway_view_visible(view) && view->output == output &&
        !view->floating && !view->maximized && !view->fullscreen;
}

static void configure_tile(struct madway_view *view, int x, int y, int width, int height)
{
    view->tile_geometry = (struct wlr_box){x, y, width, height};
    view->resize_anchor_pending = false;
    int border, title;
    madway_frame_extents(view, &border, &title);
    width -= 2 * border;
    height -= 2 * border + title;
    wlr_scene_node_set_position(&view->scene_tree->node, x, y);
    wlr_xdg_toplevel_set_tiled(view->toplevel, WLR_EDGE_TOP | WLR_EDGE_BOTTOM | WLR_EDGE_LEFT | WLR_EDGE_RIGHT);
    wlr_xdg_toplevel_set_size(view->toplevel, width > 0 ? width : 1, height > 0 ? height : 1);
    madway_frame_update(view);
}

void madway_workspace_arrange(struct madway_server *server)
{
    if (server->shutting_down) return;
    struct madway_view *view;
    wl_list_for_each(view, &server->views, link)
    {
        if (view->output == NULL || !view->output->output->enabled)
        {
            view->output = NULL;
            struct madway_output *candidate;
            wl_list_for_each(candidate, &server->outputs, link)
                if (candidate->output->enabled) { view->output = candidate; break; }
        }
        bool visible = view->output != NULL && madway_view_visible(view);
        struct madway_view *fullscreen = visible ? fullscreen_on(server, view->output) : NULL;
        if (fullscreen != NULL && view != fullscreen && !view->keep_above) visible = false;
        wlr_scene_node_set_enabled(&view->scene_tree->node, visible);
    }

    struct madway_output *output;
    wl_list_for_each(output, &server->outputs, link)
    {
        if (!output->output->enabled) continue;
        int width = output->usable_area.width, height = output->usable_area.height;
        int x = output->usable_area.x, y = output->usable_area.y;
        int gap = server->config.tile_gap;
        unsigned count = 0;
        double total_weight = 0, before_weight = 0;
        wl_list_for_each(view, &server->layout_views, layout_link)
            if (is_tile(view, output)) {
                if (count > 0) total_weight += view->tile_weight > 0 ? view->tile_weight : 1;
                ++count;
            }
        unsigned index = 0;
        wl_list_for_each(view, &server->layout_views, layout_link)
        {
            if (!madway_view_visible(view) || view->output != output) continue;
            if (view->maximized || view->fullscreen)
            {
                wlr_xdg_toplevel_set_tiled(view->toplevel, 0);
                madway_apply_window_state(view);
            }
            else if (view->floating)
            {
                wlr_xdg_toplevel_set_tiled(view->toplevel, 0);
                madway_frame_update(view);
            }
            else if (count == 1)
                configure_tile(view, x, y, width, height);
            else
            {
                // No outer padding. Master on the left; equally divided stack on the right.
                int master_width = (width - gap) * (output->master_percent ? output->master_percent : server->config.master_percent) / 100;
                if (index == 0)
                    configure_tile(view, x, y, master_width, height);
                else
                {
                    int stack_count = (int)count - 1, slot = (int)index - 1;
                    int available = height - gap * (stack_count - 1);
                    if (available < stack_count) available = stack_count;
                    double weight = view->tile_weight > 0 ? view->tile_weight : 1;
                    int extra = available - stack_count;
                    int top = slot + (int)(extra * before_weight / total_weight);
                    int bottom = slot + 1 == stack_count ? available : slot + 1 + (int)(extra * (before_weight + weight) / total_weight);
                    before_weight += weight;
                    configure_tile(view, x + master_width + gap,
                            y + top + gap * slot,
                            width - master_width - gap, bottom - top);
                }
                ++index;
            }
        }
    }
    struct madway_layer *layer;
    wl_list_for_each(layer, &server->layers, link)
        if (strncmp(layer->surface->namespace, "madway-panel", 12) == 0)
        {
            struct madway_output *output;
            wl_list_for_each(output, &server->outputs, link)
                if (output->output == layer->surface->output)
                    wlr_scene_node_set_enabled(&layer->tree->node, layer->mapped && output->output->enabled &&
                            fullscreen_on(server, output) == NULL);
        }
    madway_session_publish_state(server);
    if (server->interactive_view == NULL) madway_rebase_cursor(server);
}

void madway_workspace_focus(struct madway_server *server)
{
    if (server->shutting_down) return;
    struct madway_view *view;
    wl_list_for_each_reverse(view, &server->views, link)
        if (madway_view_visible(view) && view->scene_tree->node.enabled)
        {
            madway_focus_view(server, view);
            return;
        }
    madway_focus_view(server, NULL);
}

void madway_workspace_switch(struct madway_server *server, unsigned workspace)
{
    if (workspace >= MADWAY_WORKSPACE_COUNT || workspace == server->active_workspace) return;
    if (server->interactive_view != NULL && !server->interactive_forward_button)
        server->consumed_button = server->interactive_button;
    madway_end_interactive(server);
    madway_cancel_pointer_grab(server);
    madway_focus_view(server, NULL);
    server->active_workspace = workspace;
    madway_workspace_arrange(server);
    madway_workspace_focus(server);
    wlr_log(WLR_INFO, "Workspace %u", workspace + 1);
}

void madway_workspace_move_view(struct madway_view *view, unsigned workspace)
{
    if (workspace >= MADWAY_WORKSPACE_COUNT || view->workspace == workspace) return;
    struct madway_server *server = view->server;
    if (server->interactive_view != NULL && !server->interactive_forward_button)
        server->consumed_button = server->interactive_button;
    madway_end_interactive(server);
    madway_cancel_pointer_grab(server);
    view->workspace = workspace;
    if (server->focused_view == view) madway_focus_view(server, NULL);
    madway_workspace_arrange(server);
    madway_workspace_focus(server);
    wlr_log(WLR_INFO, "Moved window to workspace %u", workspace + 1);
}

void madway_toggle_floating(struct madway_view *view)
{
    if (view->server->interactive_view == view)
    {
        if (!view->server->interactive_forward_button)
            view->server->consumed_button = view->server->interactive_button;
        madway_end_interactive(view->server);
    }
    madway_cancel_pointer_grab(view->server);
    bool restore_floating = view->fullscreen || view->maximized;
    if (view->fullscreen) madway_set_fullscreen(view, false);
    if (view->maximized) madway_set_maximized(view, false);
    if (restore_floating) view->floating = false;
    if (view->floating)
        view->floating_geometry = (struct wlr_box){
            .x = view->scene_tree->node.x, .y = view->scene_tree->node.y,
            .width = view->toplevel->base->geometry.width,
            .height = view->toplevel->base->geometry.height,
        };
    view->floating = !view->floating;
    if (view->floating)
    {
        wlr_scene_node_set_position(&view->scene_tree->node,
                view->floating_geometry.x, view->floating_geometry.y);
        wlr_xdg_toplevel_set_size(view->toplevel,
                view->floating_geometry.width, view->floating_geometry.height);
    }
    view->frame_visible = false;
    madway_workspace_arrange(view->server);
    madway_focus_view(view->server, view);
    wlr_log(WLR_INFO, "Window mode: %s", view->floating ? "floating" : "tiled");
}

void madway_cycle_focus(struct madway_server *server, bool backwards)
{
    if (wl_list_empty(&server->layout_views)) return;
    struct wl_list *head = &server->layout_views;
    struct wl_list *position = server->focused_view != NULL ? &server->focused_view->layout_link : head;
    int remaining = wl_list_length(head);
    while (remaining-- > 0)
    {
        position = backwards ? position->prev : position->next;
        if (position == head) position = backwards ? position->prev : position->next;
        struct madway_view *view = wl_container_of(position, view, layout_link);
        if (madway_view_visible(view))
        {
            madway_focus_view(server, view);
            madway_rebase_cursor(server);
            return;
        }
    }
}

void madway_move_tile(struct madway_server *server, const char *direction)
{
    if (server->interactive_view != NULL) return;
    struct madway_view *view = server->focused_view;
    if (view == NULL || !is_tile(view, view->output)) return;
    unsigned count = 0, current = 0;
    struct madway_view *entry;
    wl_list_for_each(entry, &server->layout_views, layout_link)
        if (is_tile(entry, view->output))
        { if (entry == view) current = count; ++count; }
    unsigned target = current;
    if (!strcmp(direction, "left") && current > 0) target = 0;
    else if (!strcmp(direction, "right") && current == 0 && count > 1) target = 1;
    else if (!strcmp(direction, "up") && current > 1) target = current - 1;
    else if (!strcmp(direction, "down") && current > 0 && current + 1 < count) target = current + 1;
    if (target == current) return;
    unsigned index = 0;
    wl_list_for_each(entry, &server->layout_views, layout_link)
        if (is_tile(entry, view->output) && index++ == target)
        {
            struct wl_list placeholder;
            wl_list_insert(&view->layout_link, &placeholder);
            wl_list_remove(&view->layout_link);
            wl_list_insert(&entry->layout_link, &view->layout_link);
            wl_list_remove(&entry->layout_link);
            wl_list_insert(&placeholder, &entry->layout_link);
            wl_list_remove(&placeholder);
            madway_workspace_arrange(server);
            return;
        }
}

void madway_switcher_step(struct madway_server *server, bool backwards)
{
    bool starting = !server->switcher_active;
    if (starting)
    {
        server->switcher_origin = server->focused_view != NULL ? server->focused_view->id : 0;
        server->switcher_active = true;
    }
    madway_cycle_focus(server, backwards);
    madway_session_publish_state(server);
    if (starting) madway_session_action(server, "switcher-show");
}

void madway_switcher_finish(struct madway_server *server, bool cancel)
{
    if (!server->switcher_active) return;
    server->switcher_active = false;
    if (cancel)
    {
        struct madway_view *entry;
        wl_list_for_each(entry, &server->layout_views, layout_link)
            if (entry->id == server->switcher_origin && madway_view_visible(entry))
            { madway_focus_view(server, entry); break; }
    }
    madway_session_publish_state(server);
    madway_session_action(server, "switcher-hide");
}


bool madway_tile_resize_begin(struct madway_view *view, uint32_t edges)
{
    struct madway_server *server = view->server;
    if (view->output == NULL || !is_tile(view, view->output)) return false;
    unsigned count = 0, index = 0;
    struct madway_view *entry, *previous = NULL, *next = NULL;
    bool found = false;
    wl_list_for_each(entry, &server->layout_views, layout_link)
        if (is_tile(entry, view->output)) {
            if (entry == view) { index = count; found = true; }
            else if (found && next == NULL) next = entry;
            else if (!found) previous = entry;
            ++count;
        }
    if (count < 2) return false;
    bool horizontal = (index == 0 && (edges & WLR_EDGE_RIGHT)) ||
        (index > 0 && (edges & WLR_EDGE_LEFT));
    struct madway_view *neighbor = index > 1 && (edges & WLR_EDGE_TOP) ? previous :
        index > 0 && (edges & WLR_EDGE_BOTTOM) ? next : NULL;
    if (!horizontal && neighbor == NULL) return false;
    server->interactive_neighbor_id = neighbor != NULL ? neighbor->id : 0;
    server->interactive_master_percent = view->output->master_percent ? view->output->master_percent : server->config.master_percent;
    if (neighbor != NULL) {
        server->interactive_pair_height = view->tile_geometry.height + neighbor->tile_geometry.height;
        server->interactive_weight_total = view->tile_weight + neighbor->tile_weight;
    }
    return true;
}

void madway_tile_resize_update(struct madway_server *server, int dx, int dy)
{
    struct madway_view *view = server->interactive_view;
    if (view == NULL || view->output == NULL || !is_tile(view, view->output)) return;
    struct madway_view *neighbor = NULL, *entry;
    wl_list_for_each(entry, &server->layout_views, layout_link)
        if (entry->id == server->interactive_neighbor_id && is_tile(entry, view->output)) neighbor = entry;
    uint32_t edges = server->interactive_edges;
    bool master = view->tile_geometry.x == view->output->usable_area.x;
    int width = view->output->usable_area.width - server->config.tile_gap;
    if (width > 0 && ((master && (edges & WLR_EDGE_RIGHT)) || (!master && (edges & WLR_EDGE_LEFT)))) {
        int percent = server->interactive_master_percent + 100 * dx / width;
        view->output->master_percent = percent < 10 ? 10 : percent > 90 ? 90 : percent;
    }
    if (neighbor != NULL && server->interactive_pair_height > 1) {
        int height = server->interactive_geometry.height + ((edges & WLR_EDGE_TOP) ? -dy : dy);
        int total = server->interactive_pair_height;
        int minimum = total >= 68 ? 33 : 1;
        if (height < minimum) height = minimum;
        if (height > total - minimum) height = total - minimum;
        view->tile_weight = server->interactive_weight_total * height / total;
        neighbor->tile_weight = server->interactive_weight_total - view->tile_weight;
    }
    madway_workspace_arrange(server);
}
