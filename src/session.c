#include "session.h"
#include "main.h"
#include "view.h"
#include "decoration.h"
#include "workspace.h"

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
    GKeyFile *file = g_key_file_new();
    char *path = g_build_filename(g_get_user_config_dir(), "madway", "settings.ini", NULL);
    server->config = (struct madway_config){18, 2};
    if (g_key_file_load_from_file(file, path, G_KEY_FILE_NONE, NULL))
    {
        if (g_key_file_has_key(file, "appearance", "title_height", NULL))
            server->config.title_height = CLAMP(g_key_file_get_integer(file, "appearance", "title_height", NULL), 14, 24);
        if (g_key_file_has_key(file, "appearance", "tile_gap", NULL))
            server->config.tile_gap = CLAMP(g_key_file_get_integer(file, "appearance", "tile_gap", NULL), 0, 12);
    }
    g_key_file_unref(file);
    g_free(path);
    struct madway_view *view;
    wl_list_for_each(view, &server->views, link)
    {
        view->frame_visible = false;
        madway_frame_update(view);
    }
    if (server->scene != NULL) madway_workspace_arrange(server);
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
