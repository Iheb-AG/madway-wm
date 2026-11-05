#include "gestures.h"
#include "main.h"
#include "layer.h"
#include "workspace.h"
#include "pointer-gestures-unstable-v1-protocol.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <wlr/backend/session.h>
#include <wlr/types/wlr_pointer.h>
#include <wlr/types/wlr_pointer_gestures_v1.h>

enum gesture_kind { GESTURE_NONE, GESTURE_SWIPE, GESTURE_PINCH, GESTURE_HOLD };
struct madway_gestures {
    struct madway_server *server;
    struct wlr_pointer_gestures_v1 *manager;
    struct wlr_pointer *pointer;
    struct madway_output *output;
    struct wl_client *client;
    enum gesture_kind kind;
    bool workspace_swipe;
    unsigned workspace,fingers;
    double dx,dy;
    uint32_t time;
    struct wl_listener swipe_begin,swipe_update,swipe_end;
    struct wl_listener pinch_begin,pinch_update,pinch_end,hold_begin,hold_end;
    struct wl_listener focus_change;
};

static bool available(struct madway_server *server)
{
    return !server->locked && !server->sleeping && !server->shutting_down &&
        (!server->session || server->session->active);
}

static bool workspace_available(struct madway_server *server)
{
    bool shell_grab=server->keyboard_layer &&
        strcmp(server->keyboard_layer->surface->namespace,"madway-desktop");
    if (!available(server) || shell_grab || server->switcher_active ||
        server->interactive_view || server->seat->drag || server->seat->pointer_state.button_count ||
        wlr_seat_pointer_has_grab(server->seat)) return false;
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link) if (output->output->enabled) return true;
    return false;
}

// End goes to the original recipient, even after pointer focus has changed.
// This compositor exposes one seat; all manager resources belong to that seat.
static void end(struct madway_gestures *state,uint32_t time,bool cancelled)
{
    if (state->client) {
        struct wl_list *resources=state->kind==GESTURE_SWIPE?&state->manager->swipes:
            state->kind==GESTURE_PINCH?&state->manager->pinches:&state->manager->holds;
        struct wlr_seat_client *client=wlr_seat_client_for_wl_client(state->server->seat,state->client);
        if (client) {
            uint32_t serial=wlr_seat_client_next_serial(client);
            struct wl_resource *resource;
            wl_resource_for_each(resource,resources) {
                if (wl_resource_get_client(resource)!=state->client) continue;
                if (state->kind==GESTURE_SWIPE) zwp_pointer_gesture_swipe_v1_send_end(resource,serial,time,cancelled);
                else if (state->kind==GESTURE_PINCH) zwp_pointer_gesture_pinch_v1_send_end(resource,serial,time,cancelled);
                else zwp_pointer_gesture_hold_v1_send_end(resource,serial,time,cancelled);
            }
        }
    }
    state->kind=GESTURE_NONE;state->pointer=NULL;state->client=NULL;
    state->workspace_swipe=false;state->dx=state->dy=0;
}

void madway_gestures_cancel(struct madway_server *server)
{
    if (server->gestures) end(server->gestures,server->gestures->time,true);
}

void madway_gestures_remove_pointer(struct madway_server *server,struct wlr_pointer *pointer)
{
    if (server->gestures && server->gestures->pointer==pointer) madway_gestures_cancel(server);
}

static bool begin(struct madway_gestures *state,struct wlr_pointer *pointer,
        enum gesture_kind kind,uint32_t time,unsigned fingers)
{
    // Another device cannot splice into or finish the active seat gesture.
    if (state->pointer && state->pointer!=pointer) return false;
    end(state,time,true);
    struct madway_server *server=state->server;
    if (!available(server) || server->interactive_view || server->seat->drag ||
        server->seat->pointer_state.button_count || wlr_seat_pointer_has_grab(server->seat)) return false;
    bool workspace=kind==GESTURE_SWIPE && fingers==3 && server->config.workspace_swipe;
    if (workspace && !workspace_available(server)) return false;
    struct wlr_surface *surface=server->seat->pointer_state.focused_surface;
    if (!workspace && !surface) return false;
    state->pointer=pointer;state->kind=kind;state->fingers=fingers;state->time=time;
    state->output=madway_workspace_output(server);
    state->workspace_swipe=workspace;state->workspace=state->output?state->output->workspace:0;
    state->client=workspace?NULL:wl_resource_get_client(surface->resource);
    return true;
}

static bool matches(struct madway_gestures *state,struct wlr_pointer *pointer,enum gesture_kind kind,uint32_t time)
{
    if (state->pointer!=pointer || state->kind!=kind) return false;
    state->time=time;
    if (!available(state->server) || (state->workspace_swipe &&
        (!workspace_available(state->server) || state->output!=madway_workspace_output(state->server) || state->workspace!=state->output->workspace))) {
        end(state,time,true);return false;
    }
    return true;
}

static void swipe_begin(struct wl_listener *listener,void *data)
{
    struct madway_gestures *state=wl_container_of(listener,state,swipe_begin);
    struct wlr_pointer_swipe_begin_event *event=data;
    if (begin(state,event->pointer,GESTURE_SWIPE,event->time_msec,event->fingers) && !state->workspace_swipe)
        wlr_pointer_gestures_v1_send_swipe_begin(state->manager,state->server->seat,event->time_msec,event->fingers);
}

static void swipe_update(struct wl_listener *listener,void *data)
{
    struct madway_gestures *state=wl_container_of(listener,state,swipe_update);
    struct wlr_pointer_swipe_update_event *event=data;
    if (!matches(state,event->pointer,GESTURE_SWIPE,event->time_msec)) return;
    if (event->fingers!=state->fingers || !isfinite(event->dx) || !isfinite(event->dy)) {
        end(state,event->time_msec,true);return;
    }
    if (state->workspace_swipe) {state->dx+=event->dx;state->dy+=event->dy;}
    else wlr_pointer_gestures_v1_send_swipe_update(state->manager,state->server->seat,event->time_msec,event->dx,event->dy);
}

static void swipe_end(struct wl_listener *listener,void *data)
{
    struct madway_gestures *state=wl_container_of(listener,state,swipe_end);
    struct wlr_pointer_swipe_end_event *event=data;
    if (!matches(state,event->pointer,GESTURE_SWIPE,event->time_msec)) return;
    struct madway_server *server=state->server;
    bool switch_workspace=state->workspace_swipe && !event->cancelled && isfinite(state->dx) && isfinite(state->dy) &&
        fabs(state->dx)>=server->config.swipe_threshold && fabs(state->dx)>1.5*fabs(state->dy);
    int direction=(state->dx<0?1:-1)*(server->config.swipe_invert?-1:1);
    int target=(int)state->workspace+direction;
    struct madway_output *output=state->output;
    end(state,event->time_msec,event->cancelled);
    if (switch_workspace && target>=0 && target<MADWAY_WORKSPACE_COUNT)
        madway_workspace_switch_output(server,output,(unsigned)target);
}

static void pinch_begin(struct wl_listener *listener,void *data)
{
    struct madway_gestures *state=wl_container_of(listener,state,pinch_begin);
    struct wlr_pointer_pinch_begin_event *event=data;
    if (begin(state,event->pointer,GESTURE_PINCH,event->time_msec,event->fingers))
        wlr_pointer_gestures_v1_send_pinch_begin(state->manager,state->server->seat,event->time_msec,event->fingers);
}

static void pinch_update(struct wl_listener *listener,void *data)
{
    struct madway_gestures *state=wl_container_of(listener,state,pinch_update);
    struct wlr_pointer_pinch_update_event *event=data;
    if (!matches(state,event->pointer,GESTURE_PINCH,event->time_msec)) return;
    if (event->fingers!=state->fingers || !isfinite(event->dx) || !isfinite(event->dy) ||
        !isfinite(event->scale) || event->scale<=0 || !isfinite(event->rotation)) {
        end(state,event->time_msec,true);return;
    }
    wlr_pointer_gestures_v1_send_pinch_update(state->manager,state->server->seat,event->time_msec,
        event->dx,event->dy,event->scale,event->rotation);
}

static void pinch_end(struct wl_listener *listener,void *data)
{
    struct madway_gestures *state=wl_container_of(listener,state,pinch_end);
    struct wlr_pointer_pinch_end_event *event=data;
    if (matches(state,event->pointer,GESTURE_PINCH,event->time_msec)) end(state,event->time_msec,event->cancelled);
}

static void hold_begin(struct wl_listener *listener,void *data)
{
    struct madway_gestures *state=wl_container_of(listener,state,hold_begin);
    struct wlr_pointer_hold_begin_event *event=data;
    if (begin(state,event->pointer,GESTURE_HOLD,event->time_msec,event->fingers))
        wlr_pointer_gestures_v1_send_hold_begin(state->manager,state->server->seat,event->time_msec,event->fingers);
}

static void hold_end(struct wl_listener *listener,void *data)
{
    struct madway_gestures *state=wl_container_of(listener,state,hold_end);
    struct wlr_pointer_hold_end_event *event=data;
    if (matches(state,event->pointer,GESTURE_HOLD,event->time_msec)) end(state,event->time_msec,event->cancelled);
}

static void focus_change(struct wl_listener *listener,void *data)
{
    struct madway_gestures *state=wl_container_of(listener,state,focus_change);
    struct wlr_seat_pointer_focus_change_event *event=data;
    if (state->client && event->old_surface!=event->new_surface) end(state,state->time,true);
}

bool madway_gestures_init(struct madway_server *server)
{
    struct madway_gestures *state=calloc(1,sizeof(*state));
    if (!state) return false;
    state->manager=wlr_pointer_gestures_v1_create(server->display);
    if (!state->manager) {free(state);return false;}
    server->gestures=state;state->server=server;
#define LISTEN(name) state->name.notify=name;wl_signal_add(&server->cursor->events.name,&state->name)
    LISTEN(swipe_begin);LISTEN(swipe_update);LISTEN(swipe_end);
    LISTEN(pinch_begin);LISTEN(pinch_update);LISTEN(pinch_end);LISTEN(hold_begin);LISTEN(hold_end);
#undef LISTEN
    state->focus_change.notify=focus_change;
    wl_signal_add(&server->seat->pointer_state.events.focus_change,&state->focus_change);
    return true;
}

void madway_gestures_finish(struct madway_server *server)
{
    struct madway_gestures *state=server->gestures;
    if (!state) return;
    end(state,state->time,true);
    wl_list_remove(&state->swipe_begin.link);wl_list_remove(&state->swipe_update.link);wl_list_remove(&state->swipe_end.link);
    wl_list_remove(&state->pinch_begin.link);wl_list_remove(&state->pinch_update.link);wl_list_remove(&state->pinch_end.link);
    wl_list_remove(&state->hold_begin.link);wl_list_remove(&state->hold_end.link);wl_list_remove(&state->focus_change.link);
    free(state);server->gestures=NULL;
}
