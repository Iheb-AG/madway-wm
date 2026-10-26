#include "session.h"
#include "main.h"
#include "view.h"
#include "decoration.h"
#include "workspace.h"
#include "input.h"
#include "monitors.h"
#include "window.h"
#include "theme.h"
#include <glib/gstdio.h>

#include <errno.h>
#include <glib.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>
#include <wlr/util/log.h>

extern char **environ;

bool madway_spawn(struct madway_server *server, char *const arguments[], pid_t *pid)
{
    size_t count = 0;
    while (environ[count] != NULL) ++count;
    char **environment = calloc(count + 4, sizeof(*environment));
    char *display = g_strdup_printf("WAYLAND_DISPLAY=%s", server->socket_name);
    if (environment == NULL || display == NULL) { free(environment); g_free(display); return false; }
    size_t index = 0;
    for (size_t i = 0; i < count; ++i)
        if (strncmp(environ[i], "WAYLAND_DISPLAY=", 16) && strncmp(environ[i], "WAYLAND_SOCKET=", 15) &&
            strncmp(environ[i], "XDG_CURRENT_DESKTOP=", 20) && strncmp(environ[i], "XDG_SESSION_TYPE=", 17))
            environment[index++] = environ[i];
    environment[index++] = display;
    environment[index++] = "XDG_CURRENT_DESKTOP=madway";
    environment[index] = "XDG_SESSION_TYPE=wayland";
    posix_spawnattr_t attributes;
    int status = posix_spawnattr_init(&attributes);
    if (status == 0)
    {
        sigset_t mask;
        sigemptyset(&mask);
        status = posix_spawnattr_setsigmask(&attributes, &mask);
        if (status == 0) status = posix_spawnattr_setpgroup(&attributes, 0);
        if (status == 0) status = posix_spawnattr_setflags(&attributes,
                POSIX_SPAWN_SETSIGMASK | POSIX_SPAWN_SETPGROUP);
        pid_t child;
        if (status == 0) status = posix_spawnp(&child, arguments[0], NULL, &attributes, arguments, environment);
        if (status == 0 && pid != NULL) *pid = child;
        posix_spawnattr_destroy(&attributes);
    }
    if (status != 0) wlr_log(WLR_ERROR, "Could not launch %s: %s", arguments[0], strerror(status));
    g_free(display);
    free(environment);
    return status == 0;
}

void madway_launch_kitty(struct madway_server *server)
{
    char *arguments[] = {"kitty", "-o", "linux_display_server=wayland", NULL};
    madway_spawn(server, arguments, NULL);
}

void madway_session_reload(struct madway_server *server)
{
    int previous_master = server->config.master_percent;
    GKeyFile *file = g_key_file_new();
    char *path = g_build_filename(g_get_user_config_dir(), "madway", "settings.ini", NULL);
    server->config = (struct madway_config){.title_height = 14, .tile_gap = 1,
        .master_percent = 50, .repeat_rate = 25, .repeat_delay = 600, .default_floating = true};
    if (g_key_file_load_from_file(file, path, G_KEY_FILE_NONE, NULL))
    {
        if (g_key_file_has_key(file, "appearance", "title_height", NULL))
            server->config.title_height = CLAMP(g_key_file_get_integer(file, "appearance", "title_height", NULL), 12, 24);
        if (g_key_file_has_key(file, "appearance", "tile_gap", NULL))
            server->config.tile_gap = CLAMP(g_key_file_get_integer(file, "appearance", "tile_gap", NULL), 0, 12);
        if (g_key_file_has_key(file, "windows", "default_mode", NULL))
        {
            char *mode = g_key_file_get_string(file, "windows", "default_mode", NULL);
            server->config.default_floating = g_strcmp0(mode, "tiled") != 0;
            g_free(mode);
        }
        if (g_key_file_has_key(file, "windows", "master_percent", NULL))
            server->config.master_percent = CLAMP(g_key_file_get_integer(file, "windows", "master_percent", NULL), 25, 75);
        if (g_key_file_has_key(file, "input", "repeat_rate", NULL))
            server->config.repeat_rate = CLAMP(g_key_file_get_integer(file, "input", "repeat_rate", NULL), 1, 100);
        if (g_key_file_has_key(file, "input", "repeat_delay", NULL))
            server->config.repeat_delay = CLAMP(g_key_file_get_integer(file, "input", "repeat_delay", NULL), 100, 1500);
        server->config.focus_follows_mouse = g_key_file_get_boolean(file, "input", "focus_follows_mouse", NULL);
        char *modifier = g_key_file_get_string(file, "input", "modifier", NULL);
        server->config.use_super = g_strcmp0(modifier, "super") == 0;
        g_free(modifier);
    }
    char *theme = g_key_file_get_string(file, "appearance", "theme", NULL);
    madway_theme_load(&server->config, theme);
    g_free(theme);
    g_key_file_unref(file);
    g_free(path);
    if (previous_master != server->config.master_percent) {
        struct madway_output *output;
        wl_list_for_each(output, &server->outputs, link) output->master_percent = 0;
    }
    madway_reload_input(server);
    struct madway_view *view;
    wl_list_for_each(view, &server->views, link)
    {
        view->frame_visible = false;
        madway_frame_update(view);
    }
    if (server->scene != NULL) madway_workspace_arrange(server);
    madway_reload_outputs(server);
}

void madway_session_start(struct madway_server *server)
{
    if (g_strcmp0(g_getenv("MADWAY_SESSION"), "1") != 0) return;
    // Installed binaries use their sibling helper, including staged installations.
    char *executable = g_file_read_link("/proc/self/exe", NULL);
    char *directory = executable != NULL ? g_path_get_dirname(executable) : NULL;
    char *sibling = directory != NULL ? g_build_filename(directory, "madway-shell", NULL) : NULL;
    const char *helper = sibling != NULL && g_file_test(sibling, G_FILE_TEST_IS_EXECUTABLE)
        ? sibling : g_file_test(MADWAY_HELPER_SOURCE, G_FILE_TEST_IS_EXECUTABLE)
        ? MADWAY_HELPER_SOURCE : MADWAY_HELPER_INSTALLED;
    char pid[32];
    snprintf(pid, sizeof(pid), "%ld", (long)getpid());
    char *arguments[] = {(char *)helper, "serve", "--compositor-pid", pid, NULL};
    madway_spawn(server, arguments, &server->session_pid);
    g_free(sibling);
    g_free(directory);
    g_free(executable);
}

void madway_session_stop(struct madway_server *server)
{
    pid_t pid = server->session_pid;
    if (pid <= 0 || waitpid(pid, NULL, WNOHANG) != 0) return;
    kill(pid, SIGTERM);
    // Allow the helper's bounded sound playback to finish before forcing cleanup.
    for (int i = 0; i < 900; ++i)
    {
        if (waitpid(pid, NULL, WNOHANG) != 0) { server->session_pid = 0; return; }
        usleep(10000);
    }
    kill(-pid, SIGKILL);
    waitpid(pid, NULL, 0);
    server->session_pid = 0;
}

void madway_session_action(struct madway_server *server, const char *action)
{
    const char *runtime = g_getenv("XDG_RUNTIME_DIR");
    if (runtime == NULL || server->session_pid <= 0)
    {
        wlr_log(WLR_ERROR, "Desktop actions require starting scripts/madway-session");
        return;
    }
    char *directory = g_strdup_printf("madway-%s", server->socket_name);
    char *path = g_build_filename(runtime, directory, "control.sock", NULL);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof(address.sun_path)) { g_free(directory); g_free(path); return; }
    strcpy(address.sun_path, path);
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (fd >= 0)
    {
        char message[128];
        int length = snprintf(message, sizeof(message), "{\"action\":\"%s\"}", action);
        if (length > 0 && (size_t)length < sizeof(message) &&
            sendto(fd, message, (size_t)length, 0, (struct sockaddr *)&address, sizeof(address)) < 0)
            wlr_log(WLR_ERROR, "Desktop helper not ready: %s", strerror(errno));
        close(fd);
    }
    g_free(directory);
    g_free(path);
}

static char *session_path(struct madway_server *server, const char *name)
{
    char *directory = g_strdup_printf("madway-%s", server->socket_name);
    char *path = g_build_filename(g_getenv("XDG_RUNTIME_DIR"), directory, name, NULL);
    g_free(directory);
    return path;
}

static int handle_control(int fd, uint32_t mask, void *data)
{
    (void)mask;
    struct madway_server *server = data;
    char command[128];
    ssize_t length;
    while ((length = recv(fd, command, sizeof(command) - 1, 0)) > 0)
    {
        command[length] = '\0';
        unsigned workspace, identity;
        if (sscanf(command, "workspace %u", &workspace) == 1 && workspace < MADWAY_WORKSPACE_COUNT)
            madway_workspace_switch(server, workspace);
        else if (sscanf(command, "move-workspace %u", &workspace) == 1 && workspace < MADWAY_WORKSPACE_COUNT)
        {
            if (server->focused_view != NULL) madway_workspace_move_view(server->focused_view, workspace);
        }
        else if (sscanf(command, "focus %u", &identity) == 1)
        {
            struct madway_view *target;
            wl_list_for_each(target, &server->layout_views, layout_link)
                if (target->id == identity && madway_view_visible(target))
                { madway_focus_view(server, target); break; }
            server->switcher_active = false;
            madway_session_publish_state(server);
        }
        else if (g_str_has_prefix(command, "tile "))
            madway_move_tile(server, command + 5);
        else if (strcmp(command, "focus-settings") == 0)
        {
            struct madway_view *view;
            wl_list_for_each(view, &server->views, link)
                if (view->mapped && g_strcmp0(view->toplevel->app_id, "org.madway.Settings") == 0)
                { madway_workspace_switch(server, view->workspace); madway_focus_view(server, view); break; }
        }
        else if (strcmp(command, "above") == 0 && server->focused_view != NULL)
            madway_set_keep_above(server->focused_view, !server->focused_view->keep_above);
        else if (strcmp(command, "floating") == 0 && server->focused_view != NULL)
            madway_toggle_floating(server->focused_view);
        else if (strcmp(command, "maximize") == 0 && server->focused_view != NULL)
            madway_set_maximized(server->focused_view, !server->focused_view->maximized);
        else if (strcmp(command, "fullscreen") == 0 && server->focused_view != NULL)
            madway_set_fullscreen(server->focused_view, !server->focused_view->fullscreen);
        else if (strcmp(command, "close") == 0 && server->focused_view != NULL)
            wlr_xdg_toplevel_send_close(server->focused_view->toplevel);
    }
    return 0;
}

bool madway_session_init(struct madway_server *server)
{
    char *directory = session_path(server, "");
    bool ok = g_mkdir_with_parents(directory, 0700) == 0;
    g_free(directory);
    if (!ok) return false;
    char *path = session_path(server, "compositor.sock");
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof(address.sun_path)) { g_free(path); return false; }
    strcpy(address.sun_path, path);
    g_unlink(path); g_free(path);
    server->session_control_fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (server->session_control_fd < 0 || bind(server->session_control_fd,
            (struct sockaddr *)&address, sizeof(address)) < 0) return false;
    server->session_control_event = wl_event_loop_add_fd(wl_display_get_event_loop(server->display),
            server->session_control_fd, WL_EVENT_READABLE, handle_control, server);
    return server->session_control_event != NULL;
}

void madway_session_finish(struct madway_server *server)
{
    if (server->session_control_event != NULL) wl_event_source_remove(server->session_control_event);
    if (server->session_control_fd >= 0) close(server->session_control_fd);
    if (server->socket_name == NULL) return;
    char *path = session_path(server, "compositor.sock"); g_unlink(path); g_free(path);
    path = session_path(server, "desktop.json"); g_unlink(path); g_free(path);
}

static void append_json_string(GString *text, const char *value)
{
    g_string_append_c(text, '"');
    for (const unsigned char *p = (const unsigned char *)(value ? value : ""); *p; ++p)
        if (*p == '"' || *p == '\\') { g_string_append_c(text, '\\'); g_string_append_c(text, *p); }
        else if (*p < 32) g_string_append_printf(text, "\\u%04x", *p);
        else g_string_append_c(text, *p);
    g_string_append_c(text, '"');
}

void madway_session_publish_state(struct madway_server *server)
{
    if (server->shutting_down || server->socket_name == NULL) return;
    GString *text = g_string_new(NULL);
    g_string_append_printf(text, "{\"workspace\":%u,\"title\":", server->active_workspace);
    struct madway_view *view = server->focused_view;
    append_json_string(text, view != NULL && madway_view_visible(view) ? view->toplevel->title : "");
    g_string_append_printf(text, ",\"has_window\":%s,\"switcher\":%s,\"windows\":[",
            view != NULL && madway_view_visible(view) ? "true" : "false", server->switcher_active ? "true" : "false");
    bool first = true;
    struct madway_view *entry;
    wl_list_for_each(entry, &server->layout_views, layout_link)
        if (madway_view_visible(entry))
        {
            g_string_append_printf(text, "%s{\"id\":%u,\"focused\":%s,\"title\":", first ? "" : ",", entry->id,
                    entry == server->focused_view ? "true" : "false");
            append_json_string(text, entry->toplevel->title);
            g_string_append(text, "}");first = false;
        }
    g_string_append_printf(text, "],\"keep_above\":%s,\"output_x\":%d,\"output_y\":%d}\n",
            view != NULL && view->keep_above ? "true" : "false",
            view != NULL && view->output != NULL ? view->output->layout_x : 0,
            view != NULL && view->output != NULL ? view->output->layout_y : 0);
    char *path = session_path(server, "desktop.json");
    g_file_set_contents(path, text->str, (gssize)text->len, NULL);
    g_free(path); g_string_free(text, true);
}

void madway_session_menu(struct madway_server *server, double x, double y)
{
    // The fixed numeric suffix is parsed only by madway-shell, never a shell.
    char action[96];
    snprintf(action, sizeof(action), "desktop-menu %d %d", (int)x, (int)y);
    madway_session_action(server, action);
}
