#include "input.h"
#include "main.h"
#include "view.h"
#include "decoration.h"
#include "window.h"
#include "workspace.h"
#include "layer.h"
#include "session.h"

#include <stdlib.h>
#include <wlr/backend/session.h>
#include <stdio.h>
#include <string.h>
#include <spawn.h>
#include <signal.h>
#include <time.h>
#include <linux/input-event-codes.h>
#include <wlr/types/wlr_data_device.h>
#include <wlr/types/wlr_primary_selection.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_pointer.h>
#include <wlr/util/log.h>
#include <wlr/util/edges.h>
#include <xkbcommon/xkbcommon.h>
#include <xkbcommon/xkbcommon-keysyms.h>

extern char **environ;

struct madway_keyboard
{
    struct madway_server *server;
    struct wlr_keyboard *keyboard;
    struct wl_list link;
    struct wl_listener key;
    struct wl_listener modifiers;
    struct wl_listener destroy;
    bool consumed_keys[KEY_CNT];
};

struct madway_pointer
{
    struct madway_server *server;
    struct wlr_input_device *device;
    struct wl_list link;
    struct wl_listener destroy;
};

static void set_cursor_shape(struct madway_server *server, const char *name)
{
    if (server->cursor_shape != NULL && strcmp(server->cursor_shape, name) == 0) return;
    wlr_cursor_set_xcursor(server->cursor, server->cursor_manager, name);
    server->cursor_shape = name;
}

static struct wlr_output *pointer_output(struct madway_server *server, struct wlr_pointer *pointer)
{
    struct madway_output *output;
    wl_list_for_each(output, &server->outputs, link)
        if (output->output->enabled && pointer->output_name != NULL &&
            strcmp(output->output->name, pointer->output_name) == 0)
            return output->output;
    return NULL;
}

static bool pointer_position_valid(struct madway_server *server, struct wlr_pointer *pointer)
{
    if (pointer->output_name == NULL || pointer->output_name[0] == '\0') return true;
    struct wlr_output *output = pointer_output(server, pointer);
    return output != NULL && wlr_output_layout_contains_point(server->output_layout, output,
            server->cursor->x, server->cursor->y);
}

void madway_map_pointer_outputs(struct madway_server *server)
{
    if (server->cursor == NULL) return;
    struct madway_pointer *state;
    wl_list_for_each(state, &server->pointers, link)
    {
        struct wlr_pointer *pointer = wlr_pointer_from_input_device(state->device);
        if (pointer->output_name != NULL && pointer->output_name[0] != '\0')
            wlr_cursor_map_input_to_output(server->cursor, state->device, pointer_output(server, pointer));
    }
}

static void update_seat_capabilities(struct madway_server *server)
{
    uint32_t capabilities = 0;
    if (!wl_list_empty(&server->keyboards))
    {
        capabilities |= WL_SEAT_CAPABILITY_KEYBOARD;
    }
    if (!wl_list_empty(&server->pointers))
    {
        capabilities |= WL_SEAT_CAPABILITY_POINTER;
    }
    wlr_seat_set_capabilities(server->seat, capabilities);
}

static struct madway_view *view_at(struct madway_server *server, double x, double y,
        struct wlr_surface **surface, double *sx, double *sy)
{
    *surface = NULL;
    if (madway_layer_at(server, true, x, y, surface, sx, sy) != NULL) return NULL;
    struct wlr_scene_node *node = wlr_scene_node_at(&server->windows->node, x, y, sx, sy);
    if (node == NULL)
    {
        madway_layer_at(server, false, x, y, surface, sx, sy);
        return NULL;
    }
    if (node->type == WLR_SCENE_NODE_BUFFER)
    {
        struct wlr_scene_surface *scene_surface = wlr_scene_surface_try_from_buffer(
                wlr_scene_buffer_from_node(node));
        if (scene_surface != NULL) *surface = scene_surface->surface;
    }
    // Each application container carries its madway_view on node.data.
    while (node != NULL && node->data == NULL)
    {
        node = node->parent != NULL ? &node->parent->node : NULL;
    }
    return node != NULL ? node->data : NULL;
}

static void process_cursor_motion(struct madway_server *server, uint32_t time_msec)
{
    if (server->interactive_view != NULL)
    {
        madway_update_interactive(server);
        return;
    }
    struct wlr_seat_pointer_state *pointer = &server->seat->pointer_state;
    if (pointer->button_count > 0 && pointer->focused_surface != NULL)
    {
        // Keep selection drags with the surface where the first button was pressed.
        wlr_seat_pointer_notify_motion(server->seat, time_msec,
                server->cursor->x - server->grab_origin_x,
                server->cursor->y - server->grab_origin_y);
        return;
    }

    struct wlr_surface *surface;
    double sx, sy;
    struct madway_view *view = view_at(server, server->cursor->x, server->cursor->y, &surface, &sx, &sy);
    if (surface == NULL)
    {
        uint32_t edges = view != NULL ? madway_frame_edges(view, server->cursor->x, server->cursor->y) : 0;
        const char *name = (edges & (WLR_EDGE_LEFT | WLR_EDGE_RIGHT)) && (edges & (WLR_EDGE_TOP | WLR_EDGE_BOTTOM))
            ? (((edges & WLR_EDGE_LEFT) != 0) == ((edges & WLR_EDGE_TOP) != 0) ? "nwse-resize" : "nesw-resize")
            : (edges & (WLR_EDGE_LEFT | WLR_EDGE_RIGHT)) ? "ew-resize"
            : (edges & (WLR_EDGE_TOP | WLR_EDGE_BOTTOM)) ? "ns-resize" : "left_ptr";
        set_cursor_shape(server, name);
        wlr_seat_pointer_notify_clear_focus(server->seat);
        return;
    }
    if (pointer->focused_surface != surface)
    {
        set_cursor_shape(server, "left_ptr");
    }
    wlr_seat_pointer_notify_enter(server->seat, surface, sx, sy);
    wlr_seat_pointer_notify_motion(server->seat, time_msec, sx, sy);
}

void madway_rebase_cursor(struct madway_server *server)
{
    if (!server->input_initialized || server->shutting_down)
    {
        return;
    }
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    uint32_t time_msec = (uint32_t)((uint64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000);
    process_cursor_motion(server, time_msec);
    wlr_seat_pointer_notify_frame(server->seat);
}

void madway_cancel_pointer_grab(struct madway_server *server)
{
    struct wlr_seat_pointer_state *pointer = &server->seat->pointer_state;
    struct wlr_seat_pointer_button buttons[WLR_POINTER_BUTTONS_CAP];
    size_t count = pointer->button_count;
    memcpy(buttons, pointer->buttons, count * sizeof(*buttons));
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    uint32_t time_msec = (uint32_t)((uint64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000);
    for (size_t i = 0; i < count; ++i)
    {
        if (server->cancelled_button_count < WLR_POINTER_BUTTONS_CAP)
            server->cancelled_buttons[server->cancelled_button_count++] = buttons[i];
        for (size_t press = 0; press < buttons[i].n_pressed; ++press)
            wlr_seat_pointer_notify_button(server->seat, time_msec, buttons[i].button, WL_POINTER_BUTTON_STATE_RELEASED);
    }
    if (wlr_seat_pointer_has_grab(server->seat)) wlr_seat_pointer_end_grab(server->seat);
    wlr_seat_pointer_notify_frame(server->seat);
    wlr_seat_pointer_clear_focus(server->seat);
}

static void handle_cursor_motion(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, cursor_motion);
    struct wlr_pointer_motion_event *event = data;
    if (event->pointer->output_name != NULL && event->pointer->output_name[0] != '\0' &&
        pointer_output(server, event->pointer) == NULL) return;
    wlr_cursor_move(server->cursor, &event->pointer->base, event->delta_x, event->delta_y);
    process_cursor_motion(server, event->time_msec);
}

static void handle_cursor_motion_absolute(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, cursor_motion_absolute);
    struct wlr_pointer_motion_absolute_event *event = data;
    // Nested coordinates belong to one host window, not the entire desktop.
    if (event->pointer->output_name != NULL && event->pointer->output_name[0] != '\0' &&
        pointer_output(server, event->pointer) == NULL) return;
    wlr_cursor_warp_absolute(server->cursor, &event->pointer->base, event->x, event->y);
    process_cursor_motion(server, event->time_msec);
}

static void handle_cursor_button(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, cursor_button);
    struct wlr_pointer_button_event *event = data;
    // A host enter can precede its first motion. Never click another output
    // using the previous window's cursor position while awaiting that motion.
    if (event->state == WL_POINTER_BUTTON_STATE_PRESSED &&
        !pointer_position_valid(server, event->pointer))
    {
        server->consumed_button = event->button;
        return;
    }
    if (event->state == WL_POINTER_BUTTON_STATE_RELEASED)
        for (size_t i = 0; i < server->cancelled_button_count; ++i)
            if (server->cancelled_buttons[i].button == event->button)
            {
                if (--server->cancelled_buttons[i].n_pressed == 0)
                    server->cancelled_buttons[i] = server->cancelled_buttons[--server->cancelled_button_count];
                process_cursor_motion(server, event->time_msec);
                return;
            }
    if (event->state == WL_POINTER_BUTTON_STATE_RELEASED && server->consumed_button == event->button)
    {
        server->consumed_button = 0;
        process_cursor_motion(server, event->time_msec);
        return;
    }
    if (server->interactive_view != NULL)
    {
        if (event->state == WL_POINTER_BUTTON_STATE_RELEASED && server->interactive_button == event->button)
        {
            bool forward = server->interactive_forward_button;
            madway_end_interactive(server);
            if (forward)
                wlr_seat_pointer_notify_button(server->seat, event->time_msec, event->button, event->state);
            process_cursor_motion(server, event->time_msec);
        }
        return;
    }
    process_cursor_motion(server, event->time_msec);
    if (event->state == WL_POINTER_BUTTON_STATE_PRESSED &&
        server->seat->pointer_state.button_count == 0)
    {
        struct wlr_surface *surface;
        double sx, sy;
        struct madway_view *view = view_at(server, server->cursor->x, server->cursor->y,
                &surface, &sx, &sy);
        struct madway_layer *layer = NULL;
        if (view == NULL && surface != NULL)
        {
            layer = madway_layer_at(server, true, server->cursor->x, server->cursor->y, &surface, &sx, &sy);
            if (layer == NULL) layer = madway_layer_at(server, false, server->cursor->x, server->cursor->y, &surface, &sx, &sy);
        }
        if (server->keyboard_layer != NULL &&
            strcmp(server->keyboard_layer->surface->namespace, "madway-menu") == 0 &&
            layer != server->keyboard_layer)
        {
            madway_session_action(server, "close-menu");
            server->keyboard_layer = NULL;
        }
        bool desktop = view == NULL && (surface == NULL || (layer != NULL &&
                layer->surface->current.layer <= ZWLR_LAYER_SHELL_V1_LAYER_BOTTOM));
        if (event->button == BTN_RIGHT && desktop)
        {
            madway_session_menu(server, server->cursor->x, server->cursor->y);
            server->consumed_button = event->button;
            return;
        }
        if (layer != NULL)
        {
            madway_layer_focus(layer);
            if (layer->surface->current.layer < ZWLR_LAYER_SHELL_V1_LAYER_TOP && server->keyboard_layer == NULL)
                madway_focus_view(server, NULL);
        }
        else
        {
            if (server->keyboard_layer != NULL && server->keyboard_layer->surface->current.keyboard_interactive ==
                    ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_ON_DEMAND) server->keyboard_layer = NULL;
            madway_focus_view(server, view);
        }
        if (view != NULL)
        {
            struct wlr_keyboard *keyboard = wlr_seat_get_keyboard(server->seat);
            bool alt = keyboard != NULL && (wlr_keyboard_get_modifiers(keyboard) &
                    (server->config.use_super ? WLR_MODIFIER_LOGO : WLR_MODIFIER_ALT));
            uint32_t edges = madway_frame_edges(view, server->cursor->x, server->cursor->y);
            enum madway_frame_part part = madway_frame_at(view, server->cursor->x, server->cursor->y);
            if (event->button == BTN_LEFT && part == MADWAY_FRAME_CLOSE)
            {
                wlr_xdg_toplevel_send_close(view->toplevel);
                server->consumed_button = event->button;
                return;
            }
            if (event->button == BTN_LEFT && part == MADWAY_FRAME_MAXIMIZE)
            {
                madway_set_maximized(view, !view->maximized);
                server->consumed_button = event->button;
                return;
            }
            bool move = event->button == BTN_LEFT && (part == MADWAY_FRAME_TITLE || alt);
            bool resize = (event->button == BTN_LEFT && edges != 0) || (alt && event->button == BTN_RIGHT);
            if (move || resize)
            {
                if (edges == 0) edges = WLR_EDGE_BOTTOM | WLR_EDGE_RIGHT;
                madway_begin_interactive(view, resize ? MADWAY_RESIZE : MADWAY_MOVE, edges);
                server->interactive_button = event->button;
                if (server->interactive_view == NULL) server->consumed_button = event->button;
                return;
            }
        }
        server->grab_origin_x = server->cursor->x - server->seat->pointer_state.sx;
        server->grab_origin_y = server->cursor->y - server->seat->pointer_state.sy;
    }
    wlr_seat_pointer_notify_button(server->seat, event->time_msec, event->button, event->state);
    if (event->state == WL_POINTER_BUTTON_STATE_RELEASED &&
        server->seat->pointer_state.button_count == 0)
    {
        process_cursor_motion(server, event->time_msec);
    }
}

static void handle_cursor_axis(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, cursor_axis);
    struct wlr_pointer_axis_event *event = data;
    if (!pointer_position_valid(server, event->pointer)) return;
    wlr_seat_pointer_notify_axis(server->seat, event->time_msec, event->orientation,
            event->delta, event->delta_discrete, event->source, event->relative_direction);
}

static void handle_cursor_frame(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_server *server = wl_container_of(listener, server, cursor_frame);
    wlr_seat_pointer_notify_frame(server->seat);
}

static void handle_request_cursor(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, request_cursor);
    struct wlr_seat_pointer_request_set_cursor_event *event = data;
    if (event->seat_client == server->seat->pointer_state.focused_client &&
        wlr_seat_client_validate_event_serial(event->seat_client, event->serial))
    {
        wlr_cursor_set_surface(server->cursor, event->surface, event->hotspot_x, event->hotspot_y);
        server->cursor_shape = NULL;
    }
}

static void handle_request_selection(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, request_selection);
    struct wlr_seat_request_set_selection_event *event = data;
    wlr_seat_set_selection(server->seat, event->source, event->serial);
}

static void handle_request_primary_selection(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, request_primary_selection);
    struct wlr_seat_request_set_primary_selection_event *event = data;
    wlr_seat_set_primary_selection(server->seat, event->source, event->serial);
}

static void handle_keyboard_modifiers(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_keyboard *keyboard = wl_container_of(listener, keyboard, modifiers);
    wlr_seat_set_keyboard(keyboard->server->seat, keyboard->keyboard);
    wlr_seat_keyboard_notify_modifiers(keyboard->server->seat, &keyboard->keyboard->modifiers);
}

static bool handle_shortcut(struct madway_server *server, struct wlr_keyboard_key_event *event,
        xkb_keysym_t symbol, uint32_t modifiers)
{
    if (server->session != NULL && symbol >= XKB_KEY_XF86Switch_VT_1 && symbol <= XKB_KEY_XF86Switch_VT_12)
    {
        wlr_session_change_vt(server->session, symbol - XKB_KEY_XF86Switch_VT_1 + 1);
        return true;
    }
    switch (symbol)
    {
    case XKB_KEY_XF86AudioRaiseVolume: madway_session_action(server, "volume-up"); return true;
    case XKB_KEY_XF86AudioLowerVolume: madway_session_action(server, "volume-down"); return true;
    case XKB_KEY_XF86AudioMute: madway_session_action(server, "volume-mute"); return true;
    case XKB_KEY_XF86MonBrightnessUp: madway_session_action(server, "brightness-up"); return true;
    case XKB_KEY_XF86MonBrightnessDown: madway_session_action(server, "brightness-down"); return true;
    default: break;
    }
    uint32_t modifier = server->config.use_super ? WLR_MODIFIER_LOGO : WLR_MODIFIER_ALT;
    if (!(modifiers & modifier) || (modifiers & (WLR_MODIFIER_CTRL |
            (server->config.use_super ? WLR_MODIFIER_ALT : WLR_MODIFIER_LOGO))))
        return false;
    struct madway_view *view = server->focused_view;
    if (event->keycode >= KEY_1 && event->keycode <= KEY_9)
    {
        unsigned workspace = event->keycode - KEY_1;
        if (modifiers & WLR_MODIFIER_SHIFT)
        {
            if (view != NULL) madway_workspace_move_view(view, workspace);
        }
        else madway_workspace_switch(server, workspace);
        return true;
    }
    switch (xkb_keysym_to_lower(symbol))
    {
    case XKB_KEY_Return:
        madway_launch_kitty(server);
        return true;
    case XKB_KEY_d:
        madway_session_action(server, modifiers & WLR_MODIFIER_SHIFT ? "run" : "launcher");
        return true;
    case XKB_KEY_comma:
        madway_session_action(server, "settings");
        return true;
    case XKB_KEY_Escape:
        wl_display_terminate(server->display);
        return true;
    case XKB_KEY_f:
        if (view != NULL) madway_set_fullscreen(view, !view->fullscreen);
        return true;
    case XKB_KEY_m:
        if (view != NULL) madway_set_maximized(view, !view->maximized);
        return true;
    case XKB_KEY_space:
    case XKB_KEY_t:
        if (view != NULL) madway_toggle_floating(view);
        return true;
    case XKB_KEY_Tab:
    case XKB_KEY_ISO_Left_Tab:
        madway_cycle_focus(server, (modifiers & WLR_MODIFIER_SHIFT) != 0);
        return true;
    case XKB_KEY_q:
        if (view != NULL) wlr_xdg_toplevel_send_close(view->toplevel);
        return true;
    default:
        return false;
    }
}

static void handle_keyboard_key(struct wl_listener *listener, void *data)
{
    struct madway_keyboard *keyboard = wl_container_of(listener, keyboard, key);
    struct madway_server *server = keyboard->server;
    struct wlr_keyboard_key_event *event = data;
    wlr_seat_set_keyboard(server->seat, keyboard->keyboard);

    // XKB uses an offset of 8; Wayland key events keep the original evdev code.
    xkb_keysym_t symbol = xkb_state_key_get_one_sym(keyboard->keyboard->xkb_state,
            event->keycode + 8);
    uint32_t modifiers = wlr_keyboard_get_modifiers(keyboard->keyboard);
    if (event->state == WL_KEYBOARD_KEY_STATE_RELEASED && event->keycode < KEY_CNT &&
        keyboard->consumed_keys[event->keycode])
    {
        keyboard->consumed_keys[event->keycode] = false;
        return;
    }
    if (event->state == WL_KEYBOARD_KEY_STATE_PRESSED &&
        handle_shortcut(server, event, symbol, modifiers))
    {
        if (event->keycode < KEY_CNT) keyboard->consumed_keys[event->keycode] = true;
        return;
    }
    wlr_seat_keyboard_notify_key(server->seat, event->time_msec, event->keycode, event->state);
}

static void handle_keyboard_destroy(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_keyboard *keyboard = wl_container_of(listener, keyboard, destroy);
    struct madway_server *server = keyboard->server;
    bool was_active = wlr_seat_get_keyboard(server->seat) == keyboard->keyboard;
    if (was_active)
    {
        wlr_seat_set_keyboard(server->seat, NULL);
    }
    wl_list_remove(&keyboard->key.link);
    wl_list_remove(&keyboard->modifiers.link);
    wl_list_remove(&keyboard->destroy.link);
    wl_list_remove(&keyboard->link);
    free(keyboard);
    if (was_active && !wl_list_empty(&server->keyboards))
    {
        struct madway_keyboard *next = wl_container_of(server->keyboards.next, next, link);
        wlr_seat_set_keyboard(server->seat, next->keyboard);
        if (!server->shutting_down)
        {
            madway_focus_view(server, server->focused_view);
        }
    }
    update_seat_capabilities(server);
}

void madway_reload_input(struct madway_server *server)
{
    struct madway_keyboard *keyboard;
    wl_list_for_each(keyboard, &server->keyboards, link)
        wlr_keyboard_set_repeat_info(keyboard->keyboard,
                server->config.repeat_rate, server->config.repeat_delay);
}

static void add_keyboard(struct madway_server *server, struct wlr_input_device *device)
{
    struct wlr_keyboard *keyboard = wlr_keyboard_from_input_device(device);
    // Nested backends can supply the host's keymap. Preserve it when available.
    if (keyboard->keymap == NULL)
    {
        struct xkb_context *context = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
        struct xkb_keymap *keymap = context != NULL
            ? xkb_keymap_new_from_names(context, NULL, XKB_KEYMAP_COMPILE_NO_FLAGS) : NULL;
        bool configured = keymap != NULL && wlr_keyboard_set_keymap(keyboard, keymap);
        xkb_keymap_unref(keymap);
        xkb_context_unref(context);
        if (!configured)
        {
            wlr_log(WLR_ERROR, "Could not configure the keyboard keymap");
            return;
        }
    }
    wlr_keyboard_set_repeat_info(keyboard, server->config.repeat_rate, server->config.repeat_delay);
    struct madway_keyboard *state = calloc(1, sizeof(*state));
    if (state == NULL)
    {
        wlr_log(WLR_ERROR, "Could not allocate keyboard state");
        return;
    }
    state->server = server;
    state->keyboard = keyboard;
    state->key.notify = handle_keyboard_key;
    wl_signal_add(&keyboard->events.key, &state->key);
    state->modifiers.notify = handle_keyboard_modifiers;
    wl_signal_add(&keyboard->events.modifiers, &state->modifiers);
    state->destroy.notify = handle_keyboard_destroy;
    wl_signal_add(&device->events.destroy, &state->destroy);
    wl_list_insert(server->keyboards.prev, &state->link);
    wlr_seat_set_keyboard(server->seat, keyboard);
    update_seat_capabilities(server);
    madway_focus_view(server, server->focused_view);
}

static void handle_pointer_destroy(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_pointer *pointer = wl_container_of(listener, pointer, destroy);
    struct madway_server *server = pointer->server;
    wlr_cursor_detach_input_device(server->cursor, pointer->device);
    wl_list_remove(&pointer->destroy.link);
    wl_list_remove(&pointer->link);
    free(pointer);
    update_seat_capabilities(server);
    if (wl_list_empty(&server->pointers))
    {
        wlr_seat_pointer_notify_clear_focus(server->seat);
    }
}

static void handle_new_input(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, new_input);
    struct wlr_input_device *device = data;
    if (device->type == WLR_INPUT_DEVICE_KEYBOARD)
    {
        add_keyboard(server, device);
    }
    else if (device->type == WLR_INPUT_DEVICE_POINTER)
    {
        struct madway_pointer *pointer = calloc(1, sizeof(*pointer));
        if (pointer == NULL)
        {
            wlr_log(WLR_ERROR, "Could not allocate pointer state");
            return;
        }
        pointer->server = server;
        pointer->device = device;
        pointer->destroy.notify = handle_pointer_destroy;
        wl_signal_add(&device->events.destroy, &pointer->destroy);
        wl_list_insert(server->pointers.prev, &pointer->link);
        wlr_cursor_attach_input_device(server->cursor, device);
        madway_map_pointer_outputs(server);
        update_seat_capabilities(server);
    }
    wlr_log(WLR_INFO, "Input device detected: %s", device->name != NULL ? device->name : "(unnamed)");
}

bool madway_init_input(struct madway_server *server)
{
    server->seat = wlr_seat_create(server->display, "seat0");
    server->cursor = wlr_cursor_create();
    server->cursor_manager = wlr_xcursor_manager_create(NULL, 24);
    if (server->seat == NULL || server->cursor == NULL || server->cursor_manager == NULL ||
        !wlr_xcursor_manager_load(server->cursor_manager, 1))
    {
        return false;
    }
    wlr_cursor_attach_output_layout(server->cursor, server->output_layout);
    set_cursor_shape(server, "left_ptr");

    server->cursor_motion.notify = handle_cursor_motion;
    wl_signal_add(&server->cursor->events.motion, &server->cursor_motion);
    server->cursor_motion_absolute.notify = handle_cursor_motion_absolute;
    wl_signal_add(&server->cursor->events.motion_absolute, &server->cursor_motion_absolute);
    server->cursor_button.notify = handle_cursor_button;
    wl_signal_add(&server->cursor->events.button, &server->cursor_button);
    server->cursor_axis.notify = handle_cursor_axis;
    wl_signal_add(&server->cursor->events.axis, &server->cursor_axis);
    server->cursor_frame.notify = handle_cursor_frame;
    wl_signal_add(&server->cursor->events.frame, &server->cursor_frame);
    server->request_cursor.notify = handle_request_cursor;
    wl_signal_add(&server->seat->events.request_set_cursor, &server->request_cursor);
    server->request_selection.notify = handle_request_selection;
    wl_signal_add(&server->seat->events.request_set_selection, &server->request_selection);
    server->request_primary_selection.notify = handle_request_primary_selection;
    wl_signal_add(&server->seat->events.request_set_primary_selection, &server->request_primary_selection);
    server->new_input.notify = handle_new_input;
    wl_signal_add(&server->backend->events.new_input, &server->new_input);
    server->input_initialized = true;
    return true;
}

void madway_finish_input(struct madway_server *server)
{
    if (server->input_initialized)
    {
        wl_list_remove(&server->new_input.link);
        wl_list_remove(&server->cursor_motion.link);
        wl_list_remove(&server->cursor_motion_absolute.link);
        wl_list_remove(&server->cursor_button.link);
        wl_list_remove(&server->cursor_axis.link);
        wl_list_remove(&server->cursor_frame.link);
        wl_list_remove(&server->request_cursor.link);
        wl_list_remove(&server->request_selection.link);
        wl_list_remove(&server->request_primary_selection.link);
        struct madway_keyboard *keyboard, *keyboard_tmp;
        wl_list_for_each_safe(keyboard, keyboard_tmp, &server->keyboards, link)
        {
            handle_keyboard_destroy(&keyboard->destroy, NULL);
        }
        struct madway_pointer *pointer, *pointer_tmp;
        wl_list_for_each_safe(pointer, pointer_tmp, &server->pointers, link)
        {
            handle_pointer_destroy(&pointer->destroy, NULL);
        }
        server->input_initialized = false;
    }
    if (server->cursor != NULL)
    {
        wlr_cursor_destroy(server->cursor);
        server->cursor = NULL;
    }
    if (server->cursor_manager != NULL)
    {
        wlr_xcursor_manager_destroy(server->cursor_manager);
        server->cursor_manager = NULL;
    }
    if (server->seat != NULL)
    {
        wlr_seat_destroy(server->seat);
        server->seat = NULL;
    }
}
