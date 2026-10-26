#include "window.h"
#include "main.h"
#include "view.h"
#include "decoration.h"
#include "workspace.h"
#include "session.h"

#include <linux/input-event-codes.h>
#include <wlr/util/edges.h>

void madway_view_output_box(struct madway_view *view, struct wlr_box *box)
{
    struct wlr_output_layout *layout = view->server->output_layout;
    struct wlr_output *output = view->output != NULL ? view->output->output : wlr_output_layout_output_at(layout,
            view->scene_tree->node.x, view->scene_tree->node.y);
    if (output == NULL) output = wlr_output_layout_get_center_output(layout);
    wlr_output_layout_get_box(layout, output, box);
}

static void save_geometry(struct madway_view *view)
{
    view->restore_geometry = (struct wlr_box){
        .x = view->scene_tree->node.x, .y = view->scene_tree->node.y,
        .width = view->toplevel->base->geometry.width,
        .height = view->toplevel->base->geometry.height,
    };
    if (view->floating) view->floating_geometry = view->restore_geometry;
}

void madway_apply_window_state(struct madway_view *view)
{
    if (view->maximized || view->fullscreen)
    {
        struct wlr_box box;
        madway_view_output_box(view, &box);
        if (!view->fullscreen && view->output != NULL) box = view->output->usable_area;
        int border, title;
        madway_frame_extents(view, &border, &title);
        if (box.width <= 2 * border || box.height <= title + 2 * border) return;
        wlr_scene_node_set_position(&view->scene_tree->node, box.x, box.y);
        wlr_xdg_toplevel_set_size(view->toplevel, box.width - 2 * border,
                box.height - title - 2 * border);
    }
    else
    {
        wlr_scene_node_set_position(&view->scene_tree->node,
                view->restore_geometry.x, view->restore_geometry.y);
        wlr_xdg_toplevel_set_size(view->toplevel,
                view->restore_geometry.width, view->restore_geometry.height);
    }
    // Invalidate the cached title so its maximize/restore icon also changes.
    view->frame_visible = false;
    madway_frame_update(view);
}

void madway_set_keep_above(struct madway_view *view, bool above)
{
    view->keep_above = above;
    wlr_scene_node_reparent(&view->scene_tree->node, above ? view->server->above_windows : view->server->windows);
    madway_workspace_arrange(view->server);
    if (madway_view_visible(view)) madway_focus_view(view->server, view);
}

void madway_set_maximized(struct madway_view *view, bool maximized)
{
    if (view->fullscreen)
    {
        wlr_xdg_toplevel_set_maximized(view->toplevel, view->maximized);
        return;
    }
    if (view->maximized == maximized)
    {
        wlr_xdg_toplevel_set_maximized(view->toplevel, maximized);
        return;
    }
    if (maximized && !view->maximized) save_geometry(view);
    view->maximized = maximized;
    wlr_xdg_toplevel_set_maximized(view->toplevel, maximized);
    if (!maximized && view->floating) madway_apply_window_state(view);
    madway_workspace_arrange(view->server);
    if (maximized && madway_view_visible(view)) madway_focus_view(view->server, view);
}

void madway_set_fullscreen(struct madway_view *view, bool fullscreen)
{
    if (view->fullscreen == fullscreen)
    {
        wlr_xdg_toplevel_set_fullscreen(view->toplevel, fullscreen);
        return;
    }
    if (fullscreen && !view->fullscreen)
    {
        view->restore_maximized = view->maximized;
        if (!view->maximized) save_geometry(view);
    }
    view->fullscreen = fullscreen;
    if (!fullscreen) view->maximized = view->restore_maximized;
    wlr_xdg_toplevel_set_fullscreen(view->toplevel, fullscreen);
    wlr_xdg_toplevel_set_maximized(view->toplevel, view->maximized);
    if (!fullscreen && !view->maximized && view->floating) madway_apply_window_state(view);
    madway_workspace_arrange(view->server);
    if (fullscreen && madway_view_visible(view)) madway_focus_view(view->server, view);
}

void madway_arrange_views(struct madway_server *server)
{
    madway_workspace_arrange(server);
}

void madway_begin_interactive(struct madway_view *view,
        enum madway_interactive_mode mode, uint32_t edges)
{
    struct madway_server *server = view->server;
    if (view->maximized || view->fullscreen || !madway_view_visible(view)) return;
    if (!view->floating && (mode != MADWAY_RESIZE || !madway_tile_resize_begin(view, edges))) return;
    madway_focus_view(server, view);
    server->interactive_view = view;
    server->interactive_mode = view->floating ? mode : MADWAY_TILE_RESIZE;
    server->interactive_edges = edges;
    server->interactive_button = BTN_LEFT;
    server->interactive_forward_button = false;
    server->interactive_x = server->cursor->x;
    server->interactive_y = server->cursor->y;
    server->interactive_geometry = (struct wlr_box){
        .x = view->scene_tree->node.x, .y = view->scene_tree->node.y,
        .width = view->toplevel->base->geometry.width,
        .height = view->toplevel->base->geometry.height,
    };
    if (!view->floating) server->interactive_geometry = view->tile_geometry;
    if (mode == MADWAY_RESIZE)
    {
        view->resize_edges = edges;
        view->anchor_right = server->interactive_geometry.x + server->interactive_geometry.width;
        view->anchor_bottom = server->interactive_geometry.y + server->interactive_geometry.height;
        wlr_xdg_toplevel_set_resizing(view->toplevel, true);
    }
}

void madway_end_interactive(struct madway_server *server)
{
    if (server->interactive_view != NULL && (server->interactive_mode == MADWAY_RESIZE || server->interactive_mode == MADWAY_TILE_RESIZE) &&
        server->interactive_view->toplevel->base->initialized)
        wlr_xdg_toplevel_set_resizing(server->interactive_view->toplevel, false);
    if (server->interactive_view != NULL && server->interactive_mode == MADWAY_MOVE)
    {
        struct madway_view *view = server->interactive_view;
        struct wlr_output *target = wlr_output_layout_output_at(server->output_layout,
                view->scene_tree->node.x + view->toplevel->base->geometry.width / 2,
                view->scene_tree->node.y + view->toplevel->base->geometry.height / 2);
        struct madway_output *output;
        wl_list_for_each(output, &server->outputs, link)
            if (output->output == target) { view->output = output; break; }
    }
    server->interactive_neighbor_id = 0;
    server->interactive_view = NULL;
    server->interactive_mode = MADWAY_NORMAL;
}

static int constrain_size(int size, int minimum, int maximum)
{
    if (size < minimum) size = minimum;
    if (maximum > 0 && size > maximum) size = maximum;
    return size;
}

void madway_update_interactive(struct madway_server *server)
{
    struct madway_view *view = server->interactive_view;
    if (view == NULL) return;
    int dx = (int)(server->cursor->x - server->interactive_x);
    int dy = (int)(server->cursor->y - server->interactive_y);
    struct wlr_box original = server->interactive_geometry;
    if (server->interactive_mode == MADWAY_TILE_RESIZE)
    {
        madway_tile_resize_update(server, dx, dy);
        return;
    }
    if (server->interactive_mode == MADWAY_MOVE)
    {
        wlr_scene_node_set_position(&view->scene_tree->node, original.x + dx, original.y + dy);
        return;
    }
    uint32_t edges = server->interactive_edges;
    int width = original.width + ((edges & WLR_EDGE_LEFT) ? -dx : (edges & WLR_EDGE_RIGHT) ? dx : 0);
    int height = original.height + ((edges & WLR_EDGE_TOP) ? -dy : (edges & WLR_EDGE_BOTTOM) ? dy : 0);
    struct wlr_xdg_toplevel_state *limits = &view->toplevel->current;
    width = constrain_size(width, limits->min_width > 0 ? limits->min_width : 64, limits->max_width);
    height = constrain_size(height, limits->min_height > 0 ? limits->min_height : 32, limits->max_height);
    view->resize_anchor_pending = true;
    view->resize_serial = wlr_xdg_toplevel_set_size(view->toplevel, width, height);
}
