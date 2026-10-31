#include "taskbar.h"
#include "main.h"
#include "view.h"
#include "window.h"
#include "workspace.h"
#include <wlr/types/wlr_foreign_toplevel_management_v1.h>

static void activate(struct wl_listener *listener, void *data)
{
    struct madway_view *view = wl_container_of(listener, view, task_activate);
    struct wlr_foreign_toplevel_handle_v1_activated_event *event = data;
    if (view->server->locked || event->seat != view->server->seat || !view->mapped) return;
    madway_workspace_switch(view->server, view->workspace);
    madway_focus_view(view->server, view);
}

static void minimize(struct wl_listener *listener, void *data)
{
    struct madway_view *view = wl_container_of(listener, view, task_minimize);
    struct wlr_foreign_toplevel_handle_v1_minimized_event *event = data;
    if (!view->server->locked) madway_set_minimized(view, event->minimized);
}

static void maximize(struct wl_listener *listener, void *data)
{
    struct madway_view *view = wl_container_of(listener, view, task_maximize);
    struct wlr_foreign_toplevel_handle_v1_maximized_event *event = data;
    if (!view->server->locked) madway_set_maximized(view, event->maximized);
}

static void fullscreen(struct wl_listener *listener, void *data)
{
    struct madway_view *view = wl_container_of(listener, view, task_fullscreen);
    struct wlr_foreign_toplevel_handle_v1_fullscreen_event *event = data;
    if (!view->server->locked) madway_set_fullscreen(view, event->fullscreen);
}

static void close_window(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_view *view = wl_container_of(listener, view, task_close);
    if (!view->server->locked) wlr_xdg_toplevel_send_close(view->toplevel);
}

void madway_taskbar_remove(struct madway_view *view)
{
    if (view->task == NULL) return;
    wl_list_remove(&view->task_activate.link);
    wl_list_remove(&view->task_minimize.link);
    wl_list_remove(&view->task_maximize.link);
    wl_list_remove(&view->task_fullscreen.link);
    wl_list_remove(&view->task_close.link);
    wlr_foreign_toplevel_handle_v1_destroy(view->task);
    view->task = NULL;
}

void madway_taskbar_sync(struct madway_server *server)
{
    if (server->task_manager == NULL) return;
    struct madway_view *view;
    wl_list_for_each(view, &server->views, link) {
        if (!view->mapped || view->desktop_overlay || server->locked) {
            madway_taskbar_remove(view);
            continue;
        }
        if (view->task == NULL) {
            view->task = wlr_foreign_toplevel_handle_v1_create(server->task_manager);
            if (view->task == NULL) continue;
            view->task_activate.notify = activate;
            wl_signal_add(&view->task->events.request_activate, &view->task_activate);
            view->task_minimize.notify = minimize;
            wl_signal_add(&view->task->events.request_minimize, &view->task_minimize);
            view->task_maximize.notify = maximize;
            wl_signal_add(&view->task->events.request_maximize, &view->task_maximize);
            view->task_fullscreen.notify = fullscreen;
            wl_signal_add(&view->task->events.request_fullscreen, &view->task_fullscreen);
            view->task_close.notify = close_window;
            wl_signal_add(&view->task->events.request_close, &view->task_close);
        }
        wlr_foreign_toplevel_handle_v1_set_title(view->task, view->toplevel->title ? view->toplevel->title : "Untitled");
        wlr_foreign_toplevel_handle_v1_set_app_id(view->task, view->toplevel->app_id ? view->toplevel->app_id : "");
        wlr_foreign_toplevel_handle_v1_set_minimized(view->task, view->minimized);
        wlr_foreign_toplevel_handle_v1_set_maximized(view->task, view->maximized);
        wlr_foreign_toplevel_handle_v1_set_fullscreen(view->task, view->fullscreen);
        wlr_foreign_toplevel_handle_v1_set_activated(view->task, server->focused_view == view && madway_view_visible(view));
        struct wlr_output *target = view->output && view->output->output->enabled ? view->output->output : NULL;
        struct wlr_foreign_toplevel_handle_v1_output *output, *temporary;
        wl_list_for_each_safe(output, temporary, &view->task->outputs, link)
            if (output->output != target) wlr_foreign_toplevel_handle_v1_output_leave(view->task, output->output);
        if (target) wlr_foreign_toplevel_handle_v1_output_enter(view->task, target);
    }
    wl_list_for_each(view, &server->views, link) {
        if (!view->task) continue;
        struct wlr_foreign_toplevel_handle_v1 *parent = NULL;
        struct madway_view *candidate;
        wl_list_for_each(candidate, &server->views, link)
            if (candidate->toplevel == view->toplevel->parent) { parent = candidate->task; break; }
        wlr_foreign_toplevel_handle_v1_set_parent(view->task, parent);
    }
}

bool madway_taskbar_init(struct madway_server *server)
{
    server->task_manager = wlr_foreign_toplevel_manager_v1_create(server->display);
    return server->task_manager != NULL;
}
