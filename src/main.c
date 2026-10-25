#include "main.h"

#include <signal.h>
#include <stdlib.h>
#include <wlr/backend/wayland.h>
#include <wlr/render/pass.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/util/log.h>

static void handle_output_frame(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_output *output = wl_container_of(listener, output, frame);
    struct wlr_output *display_output = output->output;

    struct wlr_output_state state;
    wlr_output_state_init(&state);

    // Acquire a pixel buffer and begin recording drawing operations into it.
    struct wlr_render_pass *pass =
        wlr_output_begin_render_pass(display_output, &state, NULL);
    if (pass == NULL)
    {
        wlr_log(WLR_ERROR, "Could not begin a frame for %s", display_output->name);
        wlr_output_state_finish(&state);
        return;
    }

    // Cover the whole output with opaque black: red=0, green=0, blue=0, alpha=1.
    wlr_render_pass_add_rect(pass, &(struct wlr_render_rect_options){
        .box = {.width = display_output->width, .height = display_output->height},
        .color = {.r = 0, .g = 0, .b = 0, .a = 1},
        .blend_mode = WLR_RENDER_BLEND_MODE_NONE,
    });

    bool drawn = wlr_render_pass_submit(pass);
    bool committed = drawn && wlr_output_commit_state(display_output, &state);
    wlr_output_state_finish(&state);

    if (!committed)
    {
        wlr_log(WLR_ERROR, "Could not draw or commit a frame for %s", display_output->name);
    }
    else if (!output->first_frame_drawn)
    {
        output->first_frame_drawn = true;
        wlr_log(WLR_INFO, "First black frame committed on %s (%dx%d)",
                display_output->name, display_output->width, display_output->height);
    }
}

static void handle_output_request_state(struct wl_listener *listener, void *data)
{
    struct madway_output *output = wl_container_of(listener, output, request_state);
    struct wlr_output_event_request_state *event = data;

    // A nested window requests a new output size when the user resizes it.
    if (!wlr_output_commit_state(output->output, event->state))
    {
        wlr_log(WLR_ERROR, "Could not apply requested state for %s", output->output->name);
        return;
    }
    wlr_output_schedule_frame(output->output);
}

static void handle_output_destroy(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_output *output = wl_container_of(listener, output, destroy);
    struct madway_server *server = output->server;

    wl_list_remove(&output->frame.link);
    wl_list_remove(&output->request_state.link);
    wl_list_remove(&output->destroy.link);
    wl_list_remove(&output->link);
    free(output);

    // Closing the last nested window ends this demonstration.
    if (wl_list_empty(&server->outputs))
    {
        wl_display_terminate(server->display);
    }
}

static void handle_new_output(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, new_output);
    struct wlr_output *display_output = data;
    wlr_log(WLR_INFO, "Output detected: %s", display_output->name);

    if (!wlr_output_init_render(display_output, server->allocator, server->renderer))
    {
        wlr_log(WLR_ERROR, "Could not initialize rendering for %s", display_output->name);
        return;
    }

    struct madway_output *output = calloc(1, sizeof(*output));
    if (output == NULL)
    {
        wlr_log(WLR_ERROR, "Could not allocate output state");
        return;
    }
    output->server = server;
    output->output = display_output;

    // Connect each event to a handler before enabling the output.
    output->frame.notify = handle_output_frame;
    wl_signal_add(&display_output->events.frame, &output->frame);
    output->request_state.notify = handle_output_request_state;
    wl_signal_add(&display_output->events.request_state, &output->request_state);
    output->destroy.notify = handle_output_destroy;
    wl_signal_add(&display_output->events.destroy, &output->destroy);
    wl_list_insert(&server->outputs, &output->link);

    if (wlr_output_is_wl(display_output))
    {
        wlr_wl_output_set_title(display_output, "madway-wm — black background");
    }

    struct wlr_output_state state;
    wlr_output_state_init(&state);
    wlr_output_state_set_enabled(&state, true);
    struct wlr_output_mode *mode = wlr_output_preferred_mode(display_output);
    if (mode != NULL)
    {
        wlr_output_state_set_mode(&state, mode);
    }
    bool enabled = wlr_output_commit_state(display_output, &state);
    wlr_output_state_finish(&state);

    if (!enabled)
    {
        wlr_log(WLR_ERROR, "Could not enable %s", display_output->name);
        // Disconnect our listeners and release our state for this output.
        handle_output_destroy(&output->destroy, NULL);
        return;
    }

    // Ask for the first frame. Subsequent frame events are handled the same way.
    wlr_output_schedule_frame(display_output);
}

static void handle_backend_destroy(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_server *server = wl_container_of(listener, server, backend_destroy);
    wl_list_remove(&server->new_output.link);
    wl_list_remove(&server->backend_destroy.link);
    server->backend = NULL;
    wl_display_terminate(server->display);
}

static int handle_stop_signal(int signal_number, void *data)
{
    (void)signal_number;
    wl_display_terminate(data);
    return 0;
}

int main(void)
{
    wlr_log_init(WLR_INFO, NULL);
    struct madway_server server = {0};
    wl_list_init(&server.outputs);
    int result = EXIT_FAILURE;

    // display context
    server.display = wl_display_create();
    if (server.display == NULL)
    {
        wlr_log(WLR_ERROR, "Could not create the Wayland server");
        return result;
    }
    struct wl_event_loop *event_loop = wl_display_get_event_loop(server.display);
    if (wl_event_loop_add_signal(event_loop, SIGINT, handle_stop_signal, server.display) == NULL ||
        wl_event_loop_add_signal(event_loop, SIGTERM, handle_stop_signal, server.display) == NULL)
    {
        wlr_log(WLR_ERROR, "Could not register shutdown signals");
        goto cleanup;
    }
    // wlroots backend
    server.backend = wlr_backend_autocreate(
        event_loop, NULL);
    if (server.backend == NULL)
    {
        wlr_log(WLR_ERROR, "Could not create the backend");
        goto cleanup;
    }
    server.backend_destroy.notify = handle_backend_destroy;
    wl_signal_add(&server.backend->events.destroy, &server.backend_destroy);
    server.new_output.notify = handle_new_output;
    wl_signal_add(&server.backend->events.new_output, &server.new_output);

    // initialize rendering and core wayland globals
    server.renderer = wlr_renderer_autocreate(server.backend);
    if (server.renderer == NULL)
    {
        wlr_log(WLR_ERROR, "Could not create the renderer");
        goto cleanup;
    }
    server.allocator = wlr_allocator_autocreate(server.backend, server.renderer);
    if (server.allocator == NULL ||
        !wlr_renderer_init_wl_display(server.renderer, server.display) ||
        wlr_compositor_create(server.display, 5, server.renderer) == NULL)
    {
        wlr_log(WLR_ERROR, "Could not initialize rendering resources");
        goto cleanup;
    }

    // starting the backend and run the main event loop
    if (!wlr_backend_start(server.backend))
    {
        wlr_log(WLR_ERROR, "Could not start the backend");
        goto cleanup;
    }

    // run event loop
    wl_display_run(server.display);
    result = EXIT_SUCCESS;

    // cleanup
cleanup:
    wl_display_destroy_clients(server.display);
    if (server.backend != NULL)
    {
        wlr_backend_destroy(server.backend);
    }
    if (server.allocator != NULL)
    {
        wlr_allocator_destroy(server.allocator);
    }
    if (server.renderer != NULL)
    {
        wlr_renderer_destroy(server.renderer);
    }
    wl_display_destroy(server.display);

    return result;
}
