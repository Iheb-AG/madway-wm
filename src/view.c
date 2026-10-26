#include "view.h"
#include "main.h"
#include "decoration.h"
#include "input.h"
#include "window.h"
#include "workspace.h"
#include "layer.h"
#include "session.h"
#include <string.h>

#include <stdlib.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/util/log.h>
#include <wlr/util/edges.h>

void madway_focus_view(struct madway_server *server, struct madway_view *view)
{
    if (server->seat == NULL || (view != NULL && !madway_view_visible(view)))
    {
        return;
    }
    if (view != NULL && !view->keep_above) {
        struct madway_view *entry;
        wl_list_for_each(entry, &server->views, link)
            if (entry != view && madway_view_visible(entry) && entry->fullscreen && entry->output == view->output)
                madway_set_fullscreen(entry, false);
    }
    if (server->focused_view != NULL && server->focused_view != view &&
        server->focused_view->toplevel->base->initialized)
    {
        wlr_xdg_toplevel_set_activated(server->focused_view->toplevel, false);
    }
    struct madway_view *previous = server->focused_view;
    server->focused_view = view;
    madway_session_publish_state(server);
    if (previous != NULL) madway_frame_update(previous);
    if (view == NULL)
    {
        if (server->keyboard_layer != NULL && server->keyboard_layer->mapped)
        { madway_layer_focus(server->keyboard_layer); return; }
        wlr_seat_keyboard_notify_clear_focus(server->seat);
        return;
    }
    wlr_scene_node_raise_to_top(&view->scene_tree->node);
    // Keep the view list in stacking order for focus fallback on window closure.
    wl_list_remove(&view->link);
    wl_list_insert(server->views.prev, &view->link);
    wlr_xdg_toplevel_set_activated(view->toplevel, true);
    madway_frame_update(view);
    if (server->keyboard_layer != NULL && server->keyboard_layer->mapped)
    {
        madway_layer_focus(server->keyboard_layer);
        return;
    }
    struct wlr_keyboard *keyboard = wlr_seat_get_keyboard(server->seat);
    if (keyboard != NULL)
    {
        wlr_seat_keyboard_notify_enter(server->seat, view->toplevel->base->surface,
                keyboard->keycodes, keyboard->num_keycodes, &keyboard->modifiers);
    }
}

static void focus_after_view_removal(struct madway_view *removed)
{
    struct madway_server *server = removed->server;
    bool focused = server->focused_view == removed;
    if (focused) madway_focus_view(server, NULL);
    madway_workspace_arrange(server);
    if (focused) madway_workspace_focus(server);
}

static void handle_view_commit(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_view *view = wl_container_of(listener, view, commit);

    // The first commit has no pixels. Reply with a configure before the client
    // acknowledges it and attaches its first buffer. Zero lets it choose a size.
    if (view->toplevel->base->initial_commit)
    {
        if (view->decoration != NULL)
        {
            enum wlr_xdg_toplevel_decoration_v1_mode mode = view->decoration->requested_mode;
            if (mode != WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_CLIENT_SIDE)
                mode = WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE;
            wlr_xdg_toplevel_decoration_v1_set_mode(view->decoration, mode);
        }
        wlr_xdg_toplevel_set_wm_capabilities(view->toplevel,
                WLR_XDG_TOPLEVEL_WM_CAPABILITIES_MAXIMIZE | WLR_XDG_TOPLEVEL_WM_CAPABILITIES_FULLSCREEN);
        wlr_xdg_toplevel_set_size(view->toplevel, 0, 0);
        if (view->toplevel->requested.fullscreen) madway_set_fullscreen(view, true);
        else if (view->toplevel->requested.maximized) madway_set_maximized(view, true);
    }
    if (view->decoration != NULL && !view->compact_frame)
    {
        bool previous_mode = view->decorated;
        view->decorated = view->decoration->current.mode == WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE;
        if (previous_mode != view->decorated)
        {
            wlr_log(WLR_INFO, "Window decoration mode: %s", view->decorated ? "madway server-side frame" : "application-side frame");
            if (view->mapped) madway_workspace_arrange(view->server);
        }
    }
    if (view->resize_anchor_pending)
    {
        int x = view->scene_tree->node.x, y = view->scene_tree->node.y;
        if (view->resize_edges & WLR_EDGE_LEFT) x = view->anchor_right - view->toplevel->base->geometry.width;
        if (view->resize_edges & WLR_EDGE_TOP) y = view->anchor_bottom - view->toplevel->base->geometry.height;
        wlr_scene_node_set_position(&view->scene_tree->node, x, y);
        if ((int32_t)(view->toplevel->base->current.configure_serial - view->resize_serial) >= 0)
            view->resize_anchor_pending = false;
    }
    madway_frame_update(view);
}

static void handle_view_map(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_view *view = wl_container_of(listener, view, map);

    int offset = 16 + 24 * ((wl_list_length(&view->server->views) - 1) % 8);
    struct madway_output *output;
    struct wlr_output *target = wlr_output_layout_output_at(view->server->output_layout,
            view->server->cursor->x, view->server->cursor->y);
    wl_list_for_each(output, &view->server->outputs, link)
        if (output->output == target) { view->output = output; break; }
    if (view->output == NULL)
        wl_list_for_each(output, &view->server->outputs, link)
            if (output->output->enabled) { view->output = output; break; }
    int x = view->output != NULL ? view->output->usable_area.x + offset : offset;
    int y = view->output != NULL ? view->output->usable_area.y + offset : offset;
    if (!view->maximized && !view->fullscreen)
        wlr_scene_node_set_position(&view->scene_tree->node, x, y);
    view->mapped = true;
    if (view->toplevel->parent != NULL ||
        (view->toplevel->app_id != NULL && !strcmp(view->toplevel->app_id, "org.madway.Settings")))
        view->floating = true;
    if (view->toplevel->app_id != NULL && !strcmp(view->toplevel->app_id, "org.madway.Settings"))
    {
        view->compact_frame = true;
        view->decorated = true;
    }
    view->floating_geometry = (struct wlr_box){.x = x, .y = y,
        .width = view->toplevel->base->geometry.width, .height = view->toplevel->base->geometry.height};
    if (view->toplevel->parent != NULL)
    {
        struct madway_view *parent;
        wl_list_for_each(parent, &view->server->views, link)
            if (parent->toplevel == view->toplevel->parent)
            {
                view->workspace = parent->workspace;
                view->output = parent->output;
                view->floating_geometry.x = parent->scene_tree->node.x + 32;
                view->floating_geometry.y = parent->scene_tree->node.y + 32;
                if (!view->maximized && !view->fullscreen)
                    wlr_scene_node_set_position(&view->scene_tree->node,
                            view->floating_geometry.x, view->floating_geometry.y);
                break;
            }
    }
    madway_workspace_arrange(view->server);
    if (madway_view_visible(view)) madway_focus_view(view->server, view);
    madway_rebase_cursor(view->server);
    wlr_log(WLR_INFO, "Window mapped: %s", view->toplevel->title != NULL
            ? view->toplevel->title : "(untitled)");
}

static void handle_view_unmap(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_view *view = wl_container_of(listener, view, unmap);
    view->mapped = false;
    if (view->server->interactive_view == view || view->server->interactive_neighbor_id == view->id)
        madway_end_interactive(view->server);
    wlr_scene_node_set_enabled(&view->scene_tree->node, false);
    focus_after_view_removal(view);
    madway_rebase_cursor(view->server);
    wlr_log(WLR_INFO, "Window unmapped");
}

static void handle_view_destroy(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_view *view = wl_container_of(listener, view, destroy);
    view->mapped = false;
    if (view->server->interactive_view == view || view->server->interactive_neighbor_id == view->id)
        madway_end_interactive(view->server);
    wlr_scene_node_set_enabled(&view->scene_tree->node, false);
    focus_after_view_removal(view);
    wl_list_remove(&view->commit.link);
    wl_list_remove(&view->map.link);
    wl_list_remove(&view->unmap.link);
    wl_list_remove(&view->destroy.link);
    wl_list_remove(&view->request_maximize.link);
    wl_list_remove(&view->request_fullscreen.link);
    wl_list_remove(&view->request_move.link);
    wl_list_remove(&view->request_resize.link);
    wl_list_remove(&view->set_title.link);
    wl_list_remove(&view->link);
    wl_list_remove(&view->layout_link);
    view->toplevel->base->data = NULL;
    wlr_scene_node_destroy(&view->scene_tree->node);
    free(view->frame_title);
    free(view);
    wlr_log(WLR_INFO, "Window destroyed");
}

static void handle_view_request_maximize(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_view *view = wl_container_of(listener, view, request_maximize);
    if (view->toplevel->base->initialized)
    {
        madway_set_maximized(view, view->toplevel->requested.maximized);
    }
}

static void handle_view_request_fullscreen(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_view *view = wl_container_of(listener, view, request_fullscreen);
    if (view->toplevel->base->initialized)
    {
        madway_set_fullscreen(view, view->toplevel->requested.fullscreen);
    }
}

static void handle_view_request_move(struct wl_listener *listener, void *data)
{
    struct madway_view *view = wl_container_of(listener, view, request_move);
    struct wlr_xdg_toplevel_move_event *event = data;
    if (event->seat->seat == view->server->seat &&
        wlr_seat_validate_pointer_grab_serial(view->server->seat, view->toplevel->base->surface, event->serial))
    {
        madway_begin_interactive(view, MADWAY_MOVE, 0);
        if (view->server->interactive_view == view)
        {
            view->server->interactive_forward_button = true;
            view->server->interactive_button = view->server->seat->pointer_state.grab_button;
        }
    }
}

static void handle_view_request_resize(struct wl_listener *listener, void *data)
{
    struct madway_view *view = wl_container_of(listener, view, request_resize);
    struct wlr_xdg_toplevel_resize_event *event = data;
    if (event->edges != 0 && event->seat->seat == view->server->seat &&
        wlr_seat_validate_pointer_grab_serial(view->server->seat, view->toplevel->base->surface, event->serial))
    {
        madway_begin_interactive(view, MADWAY_RESIZE, event->edges);
        if (view->server->interactive_view == view)
        {
            view->server->interactive_forward_button = true;
            view->server->interactive_button = view->server->seat->pointer_state.grab_button;
        }
    }
}

static void handle_view_title(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_view *view = wl_container_of(listener, view, set_title);
    madway_session_publish_state(view->server);
    madway_frame_update(view);
}

static void handle_new_toplevel(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, new_toplevel);
    struct wlr_xdg_toplevel *toplevel = data;
    struct madway_view *view = calloc(1, sizeof(*view));
    if (view == NULL)
    {
        wl_client_post_no_memory(toplevel->base->client->client);
        return;
    }
    view->server = server;
    view->floating = server->config.default_floating;
    view->workspace = server->active_workspace;
    view->toplevel = toplevel;
    view->scene_tree = wlr_scene_tree_create(server->windows);
    if (view->scene_tree != NULL && madway_frame_create(view))
        view->content_tree = wlr_scene_xdg_surface_create(view->scene_tree, toplevel->base);
    if (view->content_tree == NULL)
    {
        if (view->scene_tree != NULL)
        {
            wlr_scene_node_destroy(&view->scene_tree->node);
        }
        free(view);
        wl_client_post_no_memory(toplevel->base->client->client);
        return;
    }
    view->id = ++server->next_view_id;
    view->tile_weight = 1;
    view->scene_tree->node.data = view;
    toplevel->base->data = view->content_tree; // Popup scene nodes use their parent's content tree.
    wlr_scene_node_set_enabled(&view->scene_tree->node, false);
    wl_list_insert(server->views.prev, &view->link);
    wl_list_insert(server->layout_views.prev, &view->layout_link);

    view->commit.notify = handle_view_commit;
    wl_signal_add(&toplevel->base->surface->events.commit, &view->commit);
    view->map.notify = handle_view_map;
    wl_signal_add(&toplevel->base->surface->events.map, &view->map);
    view->unmap.notify = handle_view_unmap;
    wl_signal_add(&toplevel->base->surface->events.unmap, &view->unmap);
    view->destroy.notify = handle_view_destroy;
    wl_signal_add(&toplevel->events.destroy, &view->destroy);
    view->request_maximize.notify = handle_view_request_maximize;
    wl_signal_add(&toplevel->events.request_maximize, &view->request_maximize);
    view->request_fullscreen.notify = handle_view_request_fullscreen;
    wl_signal_add(&toplevel->events.request_fullscreen, &view->request_fullscreen);
    view->request_move.notify = handle_view_request_move;
    wl_signal_add(&toplevel->events.request_move, &view->request_move);
    view->request_resize.notify = handle_view_request_resize;
    wl_signal_add(&toplevel->events.request_resize, &view->request_resize);
    view->set_title.notify = handle_view_title;
    wl_signal_add(&toplevel->events.set_title, &view->set_title);
    wlr_log(WLR_INFO, "Application requested a new window");
}

struct madway_decoration
{
    struct madway_server *server;
    struct wlr_xdg_toplevel_decoration_v1 *decoration;
    struct wl_listener request_mode, destroy;
};

static struct madway_view *find_view(struct madway_server *server, struct wlr_xdg_toplevel *toplevel)
{
    struct madway_view *view;
    wl_list_for_each(view, &server->views, link)
        if (view->toplevel == toplevel) return view;
    return NULL;
}

static void handle_decoration_mode(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_decoration *state = wl_container_of(listener, state, request_mode);
    // Requests can arrive before the initial empty commit; configure then.
    if (!state->decoration->toplevel->base->initialized) return;
    enum wlr_xdg_toplevel_decoration_v1_mode mode = state->decoration->requested_mode;
    if (mode != WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_CLIENT_SIDE)
        mode = WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE;
    wlr_xdg_toplevel_decoration_v1_set_mode(state->decoration, mode);
}

static void handle_decoration_destroy(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_decoration *state = wl_container_of(listener, state, destroy);
    struct madway_view *view = find_view(state->server, state->decoration->toplevel);
    if (view != NULL)
    {
        view->decoration = NULL;
        view->decorated = false;
        madway_frame_update(view);
    }
    wl_list_remove(&state->request_mode.link);
    wl_list_remove(&state->destroy.link);
    free(state);
}

static void handle_new_decoration(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, new_decoration);
    struct wlr_xdg_toplevel_decoration_v1 *decoration = data;
    struct madway_decoration *state = calloc(1, sizeof(*state));
    if (state == NULL) { wl_client_post_no_memory(decoration->toplevel->base->client->client); return; }
    state->server = server;
    state->decoration = decoration;
    struct madway_view *view = find_view(server, decoration->toplevel);
    if (view != NULL) view->decoration = decoration;
    state->request_mode.notify = handle_decoration_mode;
    wl_signal_add(&decoration->events.request_mode, &state->request_mode);
    state->destroy.notify = handle_decoration_destroy;
    wl_signal_add(&decoration->events.destroy, &state->destroy);
    handle_decoration_mode(&state->request_mode, NULL);
}

struct madway_popup
{
    struct madway_server *server;
    struct wlr_xdg_popup *popup;
    struct wlr_scene_tree *scene_tree;
    struct wl_listener commit, destroy, scene_destroy;
};

static void handle_popup_commit(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_popup *popup = wl_container_of(listener, popup, commit);
    if (popup->popup->base->initial_commit)
    {
        struct wlr_xdg_surface *root = popup->popup->parent != NULL
            ? wlr_xdg_surface_try_from_wlr_surface(popup->popup->parent) : NULL;
        while (root != NULL && root->role == WLR_XDG_SURFACE_ROLE_POPUP)
            root = root->popup->parent != NULL
                ? wlr_xdg_surface_try_from_wlr_surface(root->popup->parent) : NULL;
        struct madway_view *view = root != NULL && root->role == WLR_XDG_SURFACE_ROLE_TOPLEVEL
            ? find_view(popup->server, root->toplevel) : NULL;
        if (view != NULL && root->data != NULL)
        {
            struct wlr_box bounds;
            madway_view_output_box(view, &bounds);
            struct wlr_scene_tree *tree = root->data;
            int x, y;
            wlr_scene_node_coords(&tree->node, &x, &y);
            bounds.x -= x;
            bounds.y -= y;
            wlr_xdg_popup_unconstrain_from_box(popup->popup, &bounds);
        }
        wlr_xdg_surface_schedule_configure(popup->popup->base);
    }
}

static void handle_popup_scene_destroy(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_popup *popup = wl_container_of(listener, popup, scene_destroy);
    wl_list_remove(&popup->scene_destroy.link);
    popup->popup->base->data = NULL;
    popup->scene_tree = NULL;
}

static void handle_popup_destroy(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_popup *popup = wl_container_of(listener, popup, destroy);
    wl_list_remove(&popup->commit.link);
    wl_list_remove(&popup->destroy.link);
    popup->popup->base->data = NULL;
    if (popup->scene_tree != NULL)
    {
        wl_list_remove(&popup->scene_destroy.link);
        wlr_scene_node_destroy(&popup->scene_tree->node);
    }
    free(popup);
}

void madway_add_popup_scene(struct madway_server *server, struct wlr_xdg_popup *xdg_popup,
        struct wlr_scene_tree *parent)
{
    struct madway_popup *popup = calloc(1, sizeof(*popup));
    if (popup == NULL) { wl_client_post_no_memory(xdg_popup->base->client->client); return; }
    popup->popup = xdg_popup;
    popup->server = server;
    popup->scene_tree = wlr_scene_xdg_surface_create(parent, xdg_popup->base);
    if (popup->scene_tree == NULL)
    {
        free(popup);
        wl_client_post_no_memory(xdg_popup->base->client->client);
        return;
    }
    xdg_popup->base->data = popup->scene_tree;
    popup->commit.notify = handle_popup_commit;
    wl_signal_add(&xdg_popup->base->surface->events.commit, &popup->commit);
    popup->destroy.notify = handle_popup_destroy;
    wl_signal_add(&xdg_popup->events.destroy, &popup->destroy);
    popup->scene_destroy.notify = handle_popup_scene_destroy;
    wl_signal_add(&popup->scene_tree->node.events.destroy, &popup->scene_destroy);
    wlr_log(WLR_INFO, "Application requested a popup");
}

static void handle_new_popup(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, new_popup);
    struct wlr_xdg_popup *popup = data;
    // Layer-shell popups are associated with their layer parent by a later request.
    if (popup->parent == NULL) return;
    struct wlr_xdg_surface *parent = wlr_xdg_surface_try_from_wlr_surface(popup->parent);
    if (parent == NULL || parent->data == NULL) { wlr_xdg_popup_destroy(popup); return; }
    madway_add_popup_scene(server, popup, parent->data);
}

bool madway_init_shell(struct madway_server *server)
{
    server->xdg_shell = wlr_xdg_shell_create(server->display, 6);
    if (server->xdg_shell == NULL)
    {
        return false;
    }
    server->new_toplevel.notify = handle_new_toplevel;
    wl_signal_add(&server->xdg_shell->events.new_toplevel, &server->new_toplevel);
    server->new_popup.notify = handle_new_popup;
    wl_signal_add(&server->xdg_shell->events.new_popup, &server->new_popup);
    server->decoration_manager = wlr_xdg_decoration_manager_v1_create(server->display);
    if (server->decoration_manager == NULL) return false;
    server->new_decoration.notify = handle_new_decoration;
    wl_signal_add(&server->decoration_manager->events.new_toplevel_decoration, &server->new_decoration);
    return true;
}
