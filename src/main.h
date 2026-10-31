#ifndef MADWAY_MAIN_H
#define MADWAY_MAIN_H

#include <stdbool.h>
#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/render/allocator.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/types/wlr_output.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_cursor.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/types/wlr_xdg_decoration_v1.h>
#include <wlr/util/box.h>

#include "window.h"
#include "session.h"
#include <wlr/types/wlr_output_management_v1.h>

struct madway_view;
struct madway_layer;
struct madway_lock;
struct madway_lock_output;

struct madway_server
{
    struct wl_display *display;    // Holds the Wayland server infrastructure: connected clients, protocol objects, and the event loop
    struct wlr_backend *backend;   // Provides access to display outputs and input devices, either through hardware or your existing desktop
    struct wlr_renderer *renderer; // Provides operations for drawing images into buffers. A buffer is memory holding pixels
    struct wlr_allocator *allocator; // Allocates pixel buffers that the renderer and backend can use
    struct wlr_scene *scene; // Root of the tree describing everything we display
    struct wlr_scene_tree *desktop_tree;
    struct madway_lock *screen_lock;
    bool locked;
    struct wlr_scene_tree *backgrounds; // Bottom layer, below application windows
    struct wlr_scene_tree *windows; // Application surfaces are drawn above backgrounds
    struct wlr_scene_tree *layer_trees[4];
    struct wlr_layer_shell_v1 *layer_shell;
    struct wl_listener new_layer;
    struct wl_list layers;
    struct madway_layer *keyboard_layer;
    struct madway_config config;
    char input_error[160];
    struct madway_transition *workspace_transition;
    struct madway_motion *window_motion;
    struct madway_drag *drag;
    unsigned next_view_id, switcher_origin;
    bool switcher_active;
    pid_t session_pid;
    int session_control_fd;
    struct wl_event_source *session_control_event;
    struct wlr_session *session;
    struct wl_listener session_active;
    struct wl_listener session_destroy;
    struct wl_event_source *resume_idle;
    struct wl_list switches;
    bool power_initialized, lid_present, lid_closed, sleeping, managing_lid;
    const char *socket_name; // Owned by wl_display; clients connect using WAYLAND_DISPLAY

    struct wlr_xdg_shell *xdg_shell;
    struct wlr_foreign_toplevel_manager_v1 *task_manager;
    struct wl_listener new_toplevel;
    struct wl_listener new_popup;
    struct wlr_xdg_decoration_manager_v1 *decoration_manager;
    struct wl_listener new_decoration;
    struct wl_list views; // Contains struct madway_view.link entries
    struct wlr_scene_tree *above_windows;
    struct wl_list layout_views; // Stable tiling order, independent of focus/stacking
    unsigned active_workspace;
    struct madway_view *focused_view;

    struct wlr_output_layout *output_layout; // Shared coordinates for outputs and cursor
    struct wlr_seat *seat; // Routes keyboard and pointer events to clients
    struct wlr_cursor *cursor;
    struct wlr_xcursor_manager *cursor_manager;
    const char *cursor_shape; // NULL while a client supplies the cursor image.
    struct wl_list keyboards;
    struct wl_list pointers;
    struct wl_listener new_input;
    struct wl_listener cursor_motion;
    struct wl_listener cursor_motion_absolute;
    struct wl_listener cursor_button;
    struct wl_listener cursor_axis;
    struct wl_listener cursor_frame;
    struct wl_listener request_cursor;
    struct wl_listener request_selection;
    struct wl_listener request_primary_selection;
    struct madway_view *interactive_view;
    enum madway_interactive_mode interactive_mode;
    uint32_t interactive_edges, interactive_button;
    uint32_t consumed_button;
    struct wlr_seat_pointer_button cancelled_buttons[WLR_POINTER_BUTTONS_CAP];
    size_t cancelled_button_count;
    bool interactive_forward_button;
    double interactive_x, interactive_y;
    struct wlr_box interactive_geometry;
    unsigned interactive_neighbor_id;
    int interactive_master_percent, interactive_pair_height;
    double interactive_weight_total;
    double grab_origin_x, grab_origin_y;
    bool input_initialized;
    bool shutting_down;

    // The backend announces outputs; each output has its own frame listeners.
    struct wl_listener new_output;
    struct wl_listener backend_destroy;
    struct wlr_output_manager_v1 *output_manager;
    struct wl_listener output_apply, output_test;
    char output_error[192];
    struct wl_list outputs; // Contains struct madway_output.link entries
};

struct madway_output
{
    struct madway_server *server;
    struct wlr_output *output;
    struct wlr_scene_output *scene_output; // The part of the scene displayed by this output
    struct wlr_scene_rect *background; // Persistent black rectangle for this output
    struct madway_lock_output *lock_data;
    struct wlr_box usable_area;
    int layout_x, layout_y;
    bool positioned;
    bool lid_disabled;
    int master_percent; // Zero uses the configured default; drags override this output.
    struct wl_list link;
    struct wl_listener frame;
    struct wl_listener request_state;
    struct wl_listener destroy;
    bool first_frame_drawn;
    struct wl_event_source *frame_retry;
    unsigned failed_frames;
    bool frame_retry_pending;
};


#endif // MADWAY_MAIN_H
