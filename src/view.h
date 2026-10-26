#ifndef MADWAY_VIEW_H
#define MADWAY_VIEW_H

#include <stdbool.h>
#include <wayland-server-core.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/types/wlr_xdg_decoration_v1.h>
#include <wlr/util/box.h>

struct madway_server;
struct madway_output;

struct madway_view
{
    struct madway_server *server;
    struct madway_output *output;
    unsigned workspace;
    bool mapped, floating, compact_frame;
    struct wlr_box floating_geometry;
    struct wl_list layout_link;
    struct wlr_xdg_toplevel *toplevel;
    struct wlr_xdg_toplevel_decoration_v1 *decoration;
    struct wlr_scene_tree *scene_tree; // Our container; the client's surface tree is its child
    struct wlr_scene_tree *content_tree;
    struct wlr_scene_rect *borders[4];
    struct wlr_scene_buffer *title_buffer;
    char *frame_title;
    int frame_width, frame_height, frame_title_height;
    bool frame_active, frame_visible, decorated, maximized, fullscreen;
    bool restore_maximized;
    struct wlr_box restore_geometry;
    bool resize_anchor_pending;
    uint32_t resize_serial, resize_edges;
    int anchor_right, anchor_bottom;
    struct wl_list link;
    struct wl_listener commit;
    struct wl_listener map;
    struct wl_listener unmap;
    struct wl_listener destroy;
    struct wl_listener request_maximize;
    struct wl_listener request_fullscreen;
    struct wl_listener request_move;
    struct wl_listener request_resize;
    struct wl_listener set_title;
};


bool madway_init_shell(struct madway_server *server);
void madway_focus_view(struct madway_server *server, struct madway_view *view);
void madway_add_popup_scene(struct madway_server *server, struct wlr_xdg_popup *popup,
        struct wlr_scene_tree *parent);

#endif
