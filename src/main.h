#ifndef MADWAY_MAIN_H
#define MADWAY_MAIN_H

#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/types/wlr_output.h>

struct madway_server
{
    struct wl_display *display;    // Holds the Wayland server infrastructure: connected clients, protocol objects, and the event loop
    struct wlr_backend *backend;   // Provides access to display outputs and input devices, either through hardware or your existing desktop
    struct wlr_renderer *renderer; // Provides operations for drawing images into buffers. A buffer is memory holding pixels

    // TODO: using sockets as a communication endpoint to connect

    struct wlr_xdg_shell *xdg_shell;
    struct wl_listener new_xdg_surface;

    // Output and frame management
    struct wl_listener new_output; // ex : display
    struct wlr_output *output;
    struct wl_listener frame;
};

#endif // MADWAY_MAIN_H