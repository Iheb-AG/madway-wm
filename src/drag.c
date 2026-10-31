#include "drag.h"
#include "main.h"
#include "input.h"
#include <stdlib.h>
#include <math.h>
#include <wlr/types/wlr_data_device.h>

struct madway_drag {
    struct madway_server *server;
    struct wlr_scene_tree *tree;
    struct wlr_drag *active;
    struct wl_listener request,start,destroy;
};

void madway_drag_update(struct madway_server *server)
{
    struct madway_drag *state=server->drag;
    if (state && state->tree) {
        wlr_scene_node_set_position(&state->tree->node,(int)lround(server->cursor->x),(int)lround(server->cursor->y));
        wlr_scene_node_set_enabled(&state->tree->node,!server->locked && !server->sleeping);
    }
}

static void finished(struct wl_listener *listener,void *data)
{
    (void)data;
    struct madway_drag *state=wl_container_of(listener,state,destroy);
    wl_list_remove(&state->destroy.link);state->active=NULL;
    if (state->tree) {wlr_scene_node_destroy(&state->tree->node);state->tree=NULL;}
}

void madway_drag_cancel(struct madway_server *server)
{
    if (!server->seat || !server->seat->drag) return;
    struct wlr_drag *drag=server->seat->drag;
    // Cancel before synthesizing releases: releasing first could complete a drop.
    if (drag->started && drag->pointer_grab.interface && drag->pointer_grab.interface->cancel)
        drag->pointer_grab.interface->cancel(&drag->pointer_grab);
}

static void requested(struct wl_listener *listener,void *data)
{
    struct madway_drag *state=wl_container_of(listener,state,request);
    struct madway_server *server=state->server;
    struct wlr_seat_request_start_drag_event *event=data;
    if (!server->locked && !server->sleeping && !server->interactive_view &&
            wlr_seat_validate_pointer_grab_serial(server->seat,event->origin,event->serial))
        wlr_seat_start_pointer_drag(server->seat,event->drag,event->serial);
    else if (event->drag->source) wlr_data_source_destroy(event->drag->source);
}

static void started(struct wl_listener *listener,void *data)
{
    struct madway_drag *state=wl_container_of(listener,state,start);
    struct wlr_drag *drag=data;
    state->active=drag;
    state->destroy.notify=finished;wl_signal_add(&drag->events.destroy,&state->destroy);
    if (drag->icon) {
        state->tree=wlr_scene_tree_create(state->server->desktop_tree);
        if (state->tree) {
            wlr_scene_drag_icon_create(state->tree,drag->icon);
            wlr_scene_node_raise_to_top(&state->tree->node);
        }
    }
    madway_drag_update(state->server);
    madway_rebase_cursor(state->server);
}

bool madway_drag_init(struct madway_server *server)
{
    struct madway_drag *state=calloc(1,sizeof(*state));
    if (!state) return false;
    server->drag=state;state->server=server;
    state->request.notify=requested;wl_signal_add(&server->seat->events.request_start_drag,&state->request);
    state->start.notify=started;wl_signal_add(&server->seat->events.start_drag,&state->start);
    return true;
}

void madway_drag_finish(struct madway_server *server)
{
    if (!server->drag) return;
    madway_drag_cancel(server);
    struct madway_drag *state=server->drag;
    if (state->active) finished(&state->destroy,NULL);
    wl_list_remove(&state->request.link);wl_list_remove(&state->start.link);
    free(state);server->drag=NULL;
}
