#include "main.h"

#include <wlr/types/wlr_compositor.h>

int main(void)
{
    struct madway_server server = {0};

    // display context
    server.display = wl_display_create();
    // wlroots backend
    server.backend = wlr_backend_autocreate(
        wl_display_get_event_loop(server.display), NULL);

    // initialize rendering and core wayland globals
    server.renderer = wlr_renderer_autocreate(server.backend);
    wlr_renderer_init_wl_display(server.renderer, server.display);
    wlr_compositor_create(server.display, 5, server.renderer);

    // starting the backend and run the main event loop
    if (!wlr_backend_start(server.backend))
    {
        wlr_backend_destroy(server.backend);
        wl_display_destroy(server.display);

        return 1;
    }

    // run event loop
    wl_display_run(server.display);

    // cleanup
    wl_display_destroy_clients(server.display);
    wl_display_destroy(server.display);

    return 0;
}
