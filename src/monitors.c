#include "monitors.h"
#include "main.h"
#include "view.h"
#include "input.h"
#include "workspace.h"
#include "layer.h"
#include <glib.h>
#include <glib/gstdio.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wlr/util/log.h>

static void json_string(GString *json, const char *text)
{
    g_string_append_c(json, '"');
    for (const unsigned char *p = (const unsigned char *)(text ? text : ""); *p; ++p)
        if (*p == '"' || *p == '\\') { g_string_append_c(json, '\\'); g_string_append_c(json, *p); }
        else if (*p < 32) g_string_append_printf(json, "\\u%04x", *p);
        else g_string_append_c(json, *p);
    g_string_append_c(json, '"');
}

void madway_publish_outputs(struct madway_server *server)
{
    if (server->shutting_down || server->output_manager == NULL) return;
    struct wlr_output_configuration_v1 *configuration = wlr_output_configuration_v1_create();
    if (configuration == NULL) return;
    GString *json = g_string_new("{\"error\":");
    json_string(json, server->output_error);
    g_string_append(json, ",\"outputs\":[");
    bool first = true;
    struct madway_output *output;
    wl_list_for_each(output, &server->outputs, link)
    {
        struct wlr_output *display = output->output;
        struct wlr_output_configuration_head_v1 *head = wlr_output_configuration_head_v1_create(configuration, display);
        if (head != NULL) { head->state.x = output->layout_x; head->state.y = output->layout_y; }
        if (!first) g_string_append_c(json, ',');
        first = false;
        g_string_append(json, "{\"name\":"); json_string(json, display->name);
        g_string_append(json, ",\"description\":"); json_string(json, display->description);
        char scale[G_ASCII_DTOSTR_BUF_SIZE]; g_ascii_dtostr(scale, sizeof(scale), display->scale);
        g_string_append_printf(json, ",\"enabled\":%s,\"width\":%d,\"height\":%d,\"refresh\":%d,\"x\":%d,\"y\":%d,\"scale\":%s,\"transform\":%d,\"modes\":[",
                display->enabled ? "true" : "false", display->width, display->height, display->refresh,
                output->layout_x, output->layout_y, scale, display->transform);
        bool first_mode = true;
        struct wlr_output_mode *mode;
        wl_list_for_each(mode, &display->modes, link)
        {
            g_string_append_printf(json, "%s{\"width\":%d,\"height\":%d,\"refresh\":%d}",
                    first_mode ? "" : ",", mode->width, mode->height, mode->refresh);
            first_mode = false;
        }
        g_string_append(json, "]}");
    }
    g_string_append(json, "]}\n");
    wlr_output_manager_v1_set_configuration(server->output_manager, configuration);
    if (server->socket_name != NULL && g_getenv("XDG_RUNTIME_DIR") != NULL)
    {
        char *name = g_strdup_printf("madway-%s", server->socket_name);
        char *directory = g_build_filename(g_getenv("XDG_RUNTIME_DIR"), name, NULL);
        if (g_mkdir_with_parents(directory, 0700) == 0)
        {
            char *path = g_build_filename(directory, "outputs.json", NULL);
            g_file_set_contents(path, json->str, (gssize)json->len, NULL);
            g_free(path);
        }
        g_free(directory); g_free(name);
    }
    g_string_free(json, true);
}

void madway_arrange_outputs(struct madway_server *server)
{
    if (server->shutting_down) return;
    struct madway_output *output;
    bool any_enabled = false;
    wl_list_for_each(output, &server->outputs, link) any_enabled |= output->output->enabled;
    if (!any_enabled)
        wl_list_for_each(output, &server->outputs, link)
        {
            // Recover a connected screen when the sole enabled output is unplugged.
            struct wlr_output_state state;
            wlr_output_state_init(&state);
            wlr_output_state_set_enabled(&state, true);
            bool recovered = wlr_output_test_state(output->output, &state) &&
                wlr_output_commit_state(output->output, &state);
            wlr_output_state_finish(&state);
            if (recovered) break;
        }
    wl_list_for_each(output, &server->outputs, link)
    {
        if (!output->positioned)
        {
            int right = 0;
            struct madway_output *other;
            wl_list_for_each(other, &server->outputs, link)
                if (other != output && other->positioned && other->output->enabled)
                {
                    int width, height; wlr_output_effective_resolution(other->output, &width, &height);
                    if (other->layout_x + width > right) right = other->layout_x + width;
                }
            output->layout_x = right; output->positioned = true;
        }
        wlr_scene_node_set_enabled(&output->background->node, output->output->enabled);
        if (!output->output->enabled)
        { wlr_output_layout_remove(server->output_layout, output->output); continue; }
        int width, height; wlr_output_effective_resolution(output->output, &width, &height);
        wlr_scene_output_set_position(output->scene_output, output->layout_x, output->layout_y);
        wlr_scene_node_set_position(&output->background->node, output->layout_x, output->layout_y);
        wlr_scene_rect_set_size(output->background, width, height);
        wlr_output_layout_add(server->output_layout, output->output, output->layout_x, output->layout_y);
    }
    madway_arrange_layers(server);
    madway_workspace_arrange(server);
    struct madway_view *view;
    wl_list_for_each(view, &server->views, link)
    {
        if (!view->mapped || !view->floating || view->fullscreen || view->maximized || view->output == NULL) continue;
        struct wlr_box window = {view->scene_tree->node.x, view->scene_tree->node.y,
            view->toplevel->base->geometry.width, 16};
        bool reachable = false;
        wl_list_for_each(output, &server->outputs, link)
        {
            struct wlr_box bounds, intersection;
            if (!output->output->enabled) continue;
            wlr_output_layout_get_box(server->output_layout, output->output, &bounds);
            if (wlr_box_intersection(&intersection, &window, &bounds)) reachable = true;
        }
        if (!reachable)
        {
            int x = view->output->layout_x + 16, y = view->output->layout_y + 16;
            wlr_scene_node_set_position(&view->scene_tree->node, x, y);
            view->floating_geometry.x = view->restore_geometry.x = x;
            view->floating_geometry.y = view->restore_geometry.y = y;
        }
    }
    if (server->cursor != NULL)
    {
        madway_map_pointer_outputs(server);
        wlr_cursor_warp_closest(server->cursor, NULL, server->cursor->x, server->cursor->y);
        madway_rebase_cursor(server);
    }
    madway_publish_outputs(server);
}

static bool configure(struct madway_server *server, struct wlr_output_configuration_v1 *config, bool test)
{
    bool enabled = false;
    struct wlr_output_configuration_head_v1 *head;
    wl_list_for_each(head, &config->heads, link)
    {
        enabled |= head->state.enabled;
        if (!isfinite(head->state.scale) || head->state.scale < .5 || head->state.scale > 4 ||
            (unsigned)head->state.transform > WL_OUTPUT_TRANSFORM_FLIPPED_270 ||
            head->state.x < -32768 || head->state.x > 32768 || head->state.y < -32768 || head->state.y > 32768)
            return false;
    }
    if (!enabled) return false;
    size_t count = 0;
    struct wlr_backend_output_state *states = wlr_output_configuration_v1_build_state(config, &count);
    if (states == NULL) return false;
    bool ok = wlr_backend_test(server->backend, states, count);
    if (ok && !test) ok = wlr_backend_commit(server->backend, states, count);
    for (size_t i = 0; i < count; ++i) wlr_output_state_finish(&states[i].base);
    free(states);
    if (ok && !test)
    {
        wl_list_for_each(head, &config->heads, link)
        {
            struct madway_output *output;
            wl_list_for_each(output, &server->outputs, link)
                if (output->output == head->state.output)
                {
                    int dx = head->state.x - output->layout_x, dy = head->state.y - output->layout_y;
                    struct madway_view *view;
                    wl_list_for_each(view, &server->views, link)
                        if (view->output == output)
                        {
                            view->floating_geometry.x += dx; view->floating_geometry.y += dy;
                            view->restore_geometry.x += dx; view->restore_geometry.y += dy;
                            if (view->floating && !view->maximized && !view->fullscreen)
                                wlr_scene_node_set_position(&view->scene_tree->node,
                                        view->scene_tree->node.x + dx, view->scene_tree->node.y + dy);
                        }
                    output->layout_x = head->state.x; output->layout_y = head->state.y; output->positioned = true;
                }
        }
        server->output_error[0] = '\0';
        madway_arrange_outputs(server);
        madway_workspace_focus(server);
    }
    return ok;
}

static void request_config(struct madway_server *server, struct wlr_output_configuration_v1 *config, bool test)
{
    if (configure(server, config, test)) wlr_output_configuration_v1_send_succeeded(config);
    else wlr_output_configuration_v1_send_failed(config);
    wlr_output_configuration_v1_destroy(config);
}
static void handle_apply(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, output_apply);
    request_config(server, data, false);
}
static void handle_test(struct wl_listener *listener, void *data)
{
    struct madway_server *server = wl_container_of(listener, server, output_test);
    request_config(server, data, true);
}
bool madway_init_monitors(struct madway_server *server)
{
    server->output_manager = wlr_output_manager_v1_create(server->display);
    if (server->output_manager == NULL) return false;
    server->output_apply.notify = handle_apply;
    wl_signal_add(&server->output_manager->events.apply, &server->output_apply);
    server->output_test.notify = handle_test;
    wl_signal_add(&server->output_manager->events.test, &server->output_test);
    return true;
}

void madway_reload_outputs(struct madway_server *server)
{
    if (server->backend == NULL || server->output_manager == NULL || wl_list_empty(&server->outputs)) return;
    GKeyFile *file = g_key_file_new();
    char *path = g_build_filename(g_get_user_config_dir(), "madway", "settings.ini", NULL);
    g_key_file_load_from_file(file, path, G_KEY_FILE_NONE, NULL); g_free(path);
    struct wlr_output_configuration_v1 *config = wlr_output_configuration_v1_create();
    if (config == NULL) { g_key_file_unref(file); return; }
    bool valid = true, changed = false;
    struct madway_output *output;
    wl_list_for_each(output, &server->outputs, link)
    {
        struct wlr_output_configuration_head_v1 *head = wlr_output_configuration_head_v1_create(config, output->output);
        if (head == NULL) { valid = false; break; }
        head->state.x = output->layout_x; head->state.y = output->layout_y;
        char *group = g_strdup_printf("output:%s", output->output->name);
        if (g_key_file_has_group(file, group))
        {
            changed = true;
            if (g_key_file_has_key(file, group, "enabled", NULL)) head->state.enabled = g_key_file_get_boolean(file, group, "enabled", NULL);
            if (g_key_file_has_key(file, group, "x", NULL)) head->state.x = g_key_file_get_integer(file, group, "x", NULL);
            if (g_key_file_has_key(file, group, "y", NULL)) head->state.y = g_key_file_get_integer(file, group, "y", NULL);
            if (g_key_file_has_key(file, group, "scale", NULL)) head->state.scale = (float)g_key_file_get_double(file, group, "scale", NULL);
            if (g_key_file_has_key(file, group, "transform", NULL)) head->state.transform = g_key_file_get_integer(file, group, "transform", NULL);
            char *mode = g_key_file_get_string(file, group, "mode", NULL);
            if (mode != NULL && strcmp(mode, "preferred") != 0)
            {
                int width, height, refresh; char extra;
                if (sscanf(mode, "%dx%d@%d%c", &width, &height, &refresh, &extra) != 3 ||
                    width < 1 || width > 16384 || height < 1 || height > 16384 || refresh < 0 || refresh > 1000000)
                    valid = false;
                else
                {
                    head->state.mode = NULL;
                    head->state.custom_mode.width = width; head->state.custom_mode.height = height; head->state.custom_mode.refresh = refresh;
                    struct wlr_output_mode *candidate;
                    wl_list_for_each(candidate, &output->output->modes, link)
                        if (candidate->width == width && candidate->height == height && candidate->refresh == refresh)
                        { head->state.mode = candidate; break; }
                }
            }
            else if (mode != NULL && wlr_output_preferred_mode(output->output) != NULL)
                head->state.mode = wlr_output_preferred_mode(output->output);
            g_free(mode);
        }
        g_free(group);
    }
    if (changed && (!valid || !configure(server, config, false)))
    {
        snprintf(server->output_error, sizeof(server->output_error), "Display configuration rejected; keep at least one enabled output and choose supported modes/scales.");
        wlr_log(WLR_ERROR, "%s", server->output_error);
    }
    wlr_output_configuration_v1_destroy(config); g_key_file_unref(file);
    madway_publish_outputs(server);
}

void madway_finish_monitors(struct madway_server *server)
{
    if (server->socket_name == NULL || g_getenv("XDG_RUNTIME_DIR") == NULL) return;
    char *name = g_strdup_printf("madway-%s", server->socket_name);
    char *directory = g_build_filename(g_getenv("XDG_RUNTIME_DIR"), name, NULL);
    char *path = g_build_filename(directory, "outputs.json", NULL);
    g_unlink(path);
    g_rmdir(directory);
    g_free(path); g_free(directory); g_free(name);
}
