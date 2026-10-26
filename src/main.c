#include "main.h"
#include "input.h"
#include "view.h"
#include "window.h"
#include "workspace.h"
#include "layer.h"
#include "session.h"
#include "monitors.h"

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/wait.h>
#include <wlr/backend/wayland.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_screencopy_v1.h>
#include <wlr/types/wlr_subcompositor.h>
#include <wlr/types/wlr_data_device.h>
#include <wlr/types/wlr_primary_selection_v1.h>
#include <wlr/types/wlr_xdg_output_v1.h>
#include <wlr/util/log.h>

static void handle_output_frame(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_output *output = wl_container_of(listener, output, frame);
    struct wlr_output *display_output = output->output;

    // The scene tracks changed regions and draws its nodes using our renderer.
    bool needs_frame = wlr_scene_output_needs_frame(output->scene_output);
    if (needs_frame && !wlr_scene_output_commit(output->scene_output, NULL))
    {
        wlr_log(WLR_ERROR, "Could not commit the scene for %s", display_output->name);
        return;
    }

    // Notify visible application surfaces so they can pace their drawing.
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    wlr_scene_output_send_frame_done(output->scene_output, &now);

    if (needs_frame && !output->first_frame_drawn)
    {
        output->first_frame_drawn = true;
        wlr_log(WLR_INFO, "First scene frame committed on %s (%dx%d)",
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
    madway_arrange_outputs(output->server);
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
    madway_layer_output_destroy(server, output->output);
    struct madway_view *view;
    wl_list_for_each(view, &server->views, link)
        if (view->output == output)
        {
            view->output = NULL;
            // Keep a floating window reachable after its monitor disappears.
            view->floating_geometry.x = view->restore_geometry.x = 32;
            view->floating_geometry.y = view->restore_geometry.y = 32;
            if (view->floating && !view->maximized && !view->fullscreen)
                wlr_scene_node_set_position(&view->scene_tree->node, 32, 32);
        }
    if (server->output_layout != NULL)
    {
        wlr_output_layout_remove(server->output_layout, output->output);
    }
    wlr_scene_node_destroy(&output->background->node);
    // wlroots destroys the scene-output viewport when its wlr_output is destroyed.
    free(output);
    madway_arrange_outputs(server);

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

    // Create persistent scene objects once, rather than drawing a rectangle by hand
    // on every frame. Its dimensions are set after the output has been enabled.
    const float black[4] = {0, 0, 0, 1};
    output->scene_output = wlr_scene_output_create(server->scene, display_output);
    output->background = wlr_scene_rect_create(server->backgrounds, 0, 0, black);
    if (output->scene_output == NULL || output->background == NULL)
    {
        wlr_log(WLR_ERROR, "Could not create scene objects for %s", display_output->name);
        if (output->scene_output != NULL)
        {
            wlr_scene_output_destroy(output->scene_output);
        }
        if (output->background != NULL)
        {
            wlr_scene_node_destroy(&output->background->node);
        }
        free(output);
        return;
    }

    // Connect each event to a handler before enabling the output.
    output->frame.notify = handle_output_frame;
    wl_signal_add(&display_output->events.frame, &output->frame);
    output->request_state.notify = handle_output_request_state;
    wl_signal_add(&display_output->events.request_state, &output->request_state);
    output->destroy.notify = handle_output_destroy;
    wl_signal_add(&display_output->events.destroy, &output->destroy);
    wl_list_insert(server->outputs.prev, &output->link);

    if (wlr_output_is_wl(display_output))
    {
        wlr_wl_output_set_title(display_output, "madway-wm");
        // Host cursor queues can exhaust during shape changes across nested windows.
        // Render the nested cursor in our scene; native outputs keep hardware cursors.
        wlr_output_lock_software_cursors(display_output, true);
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
        wlr_scene_output_destroy(output->scene_output);
        // Disconnect our listeners and release our state for this output.
        handle_output_destroy(&output->destroy, NULL);
        return;
    }

    madway_arrange_outputs(server);
    madway_reload_outputs(server);

    if (server->cursor_manager != NULL)
    {
        wlr_xcursor_manager_load(server->cursor_manager, display_output->scale);
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
    if (server->input_initialized)
    {
        wl_list_remove(&server->new_input.link);
        wl_list_init(&server->new_input.link);
    }
    server->backend = NULL;
    wl_display_terminate(server->display);
}

static int handle_stop_signal(int signal_number, void *data)
{
    (void)signal_number;
    wl_display_terminate(data);
    return 0;
}

static int handle_child_exit(int signal_number, void *data)
{
    (void)signal_number;
    struct madway_server *server = data;
    pid_t pid;
    while ((pid = waitpid(-1, NULL, WNOHANG)) > 0)
        if (pid == server->session_pid) server->session_pid = 0;
    return 0;
}

static int handle_reload(int signal_number, void *data)
{
    (void)signal_number;
    madway_session_reload(data);
    return 0;
}

int main(int argc, char *argv[])
{
    if (argc == 2 && strcmp(argv[1], "--version") == 0)
    {
        printf("madway %s\n", MADWAY_VERSION);
        return EXIT_SUCCESS;
    }
    if (argc == 2 && (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0))
    {
        puts("Usage: madway [--version | --help]\nStart the complete desktop with madway-session.");
        return EXIT_SUCCESS;
    }
    if (argc != 1)
    {
        fprintf(stderr, "Unknown argument; use --help for usage.\n");
        return EXIT_FAILURE;
    }
    wlr_log_init(WLR_INFO, NULL);
    struct madway_server server = {.session_control_fd = -1};
    wl_list_init(&server.outputs);
    wl_list_init(&server.views);
    wl_list_init(&server.layout_views);
    wl_list_init(&server.keyboards);
    wl_list_init(&server.pointers);
    wl_list_init(&server.layers);
    madway_session_reload(&server);
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
        wl_event_loop_add_signal(event_loop, SIGTERM, handle_stop_signal, server.display) == NULL ||
        wl_event_loop_add_signal(event_loop, SIGCHLD, handle_child_exit, &server) == NULL ||
        wl_event_loop_add_signal(event_loop, SIGHUP, handle_reload, &server) == NULL)
    {
        wlr_log(WLR_ERROR, "Could not register shutdown signals");
        goto cleanup;
    }
    // wlroots backend
    server.backend = wlr_backend_autocreate(
        event_loop, &server.session);
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
        wlr_compositor_create(server.display, 5, server.renderer) == NULL ||
        wlr_subcompositor_create(server.display) == NULL ||
        wlr_screencopy_manager_v1_create(server.display) == NULL ||
        wlr_data_device_manager_create(server.display) == NULL ||
        wlr_primary_selection_v1_device_manager_create(server.display) == NULL)
    {
        wlr_log(WLR_ERROR, "Could not initialize rendering resources");
        goto cleanup;
    }

    server.scene = wlr_scene_create();
    if (server.scene == NULL)
    {
        wlr_log(WLR_ERROR, "Could not create the scene graph");
        goto cleanup;
    }
    server.backgrounds = wlr_scene_tree_create(&server.scene->tree);
    server.windows = wlr_scene_tree_create(&server.scene->tree);
    if (server.backgrounds == NULL || server.windows == NULL ||
        !madway_init_shell(&server))
    {
        wlr_log(WLR_ERROR, "Could not initialize scene layers and application support");
        goto cleanup;
    }

    server.output_layout = wlr_output_layout_create(server.display);
    if (server.output_layout == NULL ||
        wlr_xdg_output_manager_v1_create(server.display, server.output_layout) == NULL ||
        !madway_init_input(&server) || !madway_init_layers(&server) || !madway_init_monitors(&server))
    {
        wlr_log(WLR_ERROR, "Could not initialize input handling");
        goto cleanup;
    }

    server.socket_name = wl_display_add_socket_auto(server.display);
    if (server.socket_name == NULL)
    {
        wlr_log(WLR_ERROR, "Could not create the Wayland socket in XDG_RUNTIME_DIR");
        goto cleanup;
    }

    if (!madway_session_init(&server))
    {
        wlr_log(WLR_ERROR, "Could not initialize desktop control socket");
        goto cleanup;
    }

    // starting the backend and run the main event loop
    if (!wlr_backend_start(server.backend))
    {
        wlr_log(WLR_ERROR, "Could not start the backend");
        goto cleanup;
    }

    wlr_log(WLR_INFO, "Listening on WAYLAND_DISPLAY=%s", server.socket_name);
    wlr_log(WLR_INFO, "Launch a client from another terminal: WAYLAND_DISPLAY=%s kitty -o linux_display_server=wayland",
            server.socket_name);
    wlr_log(WLR_INFO, "Modifier=%s; Enter: Kitty; T/Space: floating; D: apps; Shift+D: commands; Comma: settings; 1..9: workspace",
            server.config.use_super ? "Super" : "Alt");
    madway_session_start(&server);

    // run event loop
    wl_display_run(server.display);
    result = EXIT_SUCCESS;

    // cleanup
cleanup:
    madway_session_stop(&server);
    server.shutting_down = true;
    madway_session_finish(&server);
    madway_finish_monitors(&server);
    wl_display_destroy_clients(server.display);
    if (server.xdg_shell != NULL)
    {
        wl_list_remove(&server.new_toplevel.link);
        wl_list_remove(&server.new_popup.link);
    }
    if (server.decoration_manager != NULL) wl_list_remove(&server.new_decoration.link);
    if (server.output_manager != NULL)
    { wl_list_remove(&server.output_apply.link); wl_list_remove(&server.output_test.link); }
    if (server.layer_shell != NULL) wl_list_remove(&server.new_layer.link);
    madway_finish_input(&server);
    if (server.backend != NULL)
    {
        wlr_backend_destroy(server.backend);
    }
    if (server.output_layout != NULL)
    {
        wlr_output_layout_destroy(server.output_layout);
    }
    if (server.scene != NULL)
    {
        // Destroying the root recursively releases any remaining child nodes.
        wlr_scene_node_destroy(&server.scene->tree.node);
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
