#ifndef MADWAY_MAIN_H
#define MADWAY_MAIN_H

#include <stdbool.h>
#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/render/allocator.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/types/wlr_output.h>

struct madway_server
{
    struct wl_display *display;    // Holds the Wayland server infrastructure: connected clients, protocol objects, and the event loop
    struct wlr_backend *backend;   // Provides access to display outputs and input devices, either through hardware or your existing desktop
    struct wlr_renderer *renderer; // Provides operations for drawing images into buffers. A buffer is memory holding pixels
    struct wlr_allocator *allocator; // Allocates pixel buffers that the renderer and backend can use

    // TODO: using sockets as a communication endpoint to connect

    struct wlr_xdg_shell *xdg_shell;
    struct wl_listener new_xdg_surface;

    // The backend announces outputs; each output has its own frame listeners.
    struct wl_listener new_output;
    struct wl_listener backend_destroy;
    struct wl_list outputs; // Contains struct madway_output.link entries
};

struct madway_output
{
    struct madway_server *server;
    struct wlr_output *output;
    struct wl_list link;
    struct wl_listener frame;
    struct wl_listener request_state;
    struct wl_listener destroy;
    bool first_frame_drawn;
};

#endif // MADWAY_MAIN_H
