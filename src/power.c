#include "power.h"
#include "main.h"
#include "input.h"
#include "monitors.h"
#include "workspace.h"
#include "view.h"
#include "lock.h"
#include "transition.h"
#include <glib.h>
#include <stdlib.h>
#include <string.h>
#include <wlr/backend/session.h>
#include <wlr/backend/libinput.h>
#include <wlr/types/wlr_damage_ring.h>
#include <wlr/types/wlr_switch.h>
#include <wlr/util/log.h>

struct madway_switch {
    struct madway_server *server;
    struct wl_list link;
    bool lid, closed;
    struct wl_listener toggle, destroy;
};

static bool internal_output(const char *name)
{
    return name != NULL && (g_str_has_prefix(name,"eDP-") || g_str_has_prefix(name,"LVDS-") || g_str_has_prefix(name,"DSI-"));
}

static bool profile_disabled(const char *name)
{
    GKeyFile *file = g_key_file_new();
    char *path = g_build_filename(g_get_user_config_dir(),"madway","settings.ini",NULL);
    char *group = g_strdup_printf("output:%s",name);
    g_key_file_load_from_file(file,path,G_KEY_FILE_NONE,NULL);
    bool disabled = g_key_file_has_key(file,group,"enabled",NULL) && !g_key_file_get_boolean(file,group,"enabled",NULL);
    g_free(path);g_free(group);g_key_file_unref(file);return disabled;
}

void madway_power_lid_outputs(struct madway_server *server)
{
    if (server->session == NULL || !server->session->active || server->shutting_down || !server->power_initialized) return;
    bool external = false;
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link)
        if (output->output->enabled && !internal_output(output->output->name)) external = true;
    bool blank = server->managing_lid && server->lid_closed && server->config.lid_auto && external;
    wl_list_for_each(output,&server->outputs,link) {
        if (!internal_output(output->output->name)) continue;
        bool disable = blank && output->output->enabled;
        bool restore = !blank && output->lid_disabled;
        if (restore && profile_disabled(output->output->name)) {output->lid_disabled=false;continue;}
        if (!disable && !restore) continue;
        struct wlr_output_state state;wlr_output_state_init(&state);
        wlr_output_state_set_enabled(&state,!disable);
        bool ok = madway_lock_secure_output(output,&state) && wlr_output_test_state(output->output,&state) && wlr_output_commit_state(output->output,&state);
        wlr_output_state_finish(&state);
        if (ok) {
            output->lid_disabled=disable;
            wlr_log(WLR_INFO,"Lid: %s built-in output %s",disable?"disabled":"restored",output->output->name);
        } else wlr_log(WLR_ERROR,"Could not update built-in output %s for lid state",output->output->name);
    }
}

void madway_power_prepare_sleep(struct madway_server *server)
{
    if (server->shutting_down) return;
    server->sleeping = true;
    madway_transition_finish(server);
    if (server->interactive_view != NULL && !server->interactive_forward_button)
        server->consumed_button=server->interactive_button;
    madway_end_interactive(server);
    madway_cancel_pointer_grab(server);
    madway_switcher_finish(server,false);
    wlr_seat_keyboard_notify_clear_focus(server->seat);
    server->cursor_shape = NULL;
    wlr_log(WLR_INFO,"Preparing compositor for system sleep");
    madway_session_publish_state(server);
}

void madway_power_resume(struct madway_server *server)
{
    if (server->shutting_down) return;
    server->sleeping = false;
    if (server->session != NULL && !server->session->active) return;
    madway_arrange_outputs(server);
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link) {
        if (!output->output->enabled) continue;
        wlr_damage_ring_add_whole(&output->scene_output->damage_ring);
        wlr_output_schedule_frame(output->output);
    }
    server->cursor_shape=NULL;
    madway_rebase_cursor(server);
    madway_focus_view(server,server->focused_view);
    wlr_log(WLR_INFO,"Session resumed: output layout, full repaint and input focus restored");
    madway_session_publish_state(server);
}

static void resume_idle(void *data)
{
    struct madway_server *server=data;server->resume_idle=NULL;
    if (!server->sleeping) madway_power_resume(server);
}
static void active_changed(struct wl_listener *listener, void *data)
{
    (void)data;
    struct madway_server *server=wl_container_of(listener,server,session_active);
    if (!server->session->active) {
        madway_transition_finish(server);
        if (server->interactive_view != NULL && !server->interactive_forward_button)
            server->consumed_button=server->interactive_button;
        madway_end_interactive(server);madway_cancel_pointer_grab(server);
        wlr_seat_keyboard_notify_clear_focus(server->seat);
    } else if (server->resume_idle == NULL)
        server->resume_idle=wl_event_loop_add_idle(wl_display_get_event_loop(server->display),resume_idle,server);
}
static void session_destroyed(struct wl_listener *listener,void *data)
{
    (void)data;
    struct madway_server *server=wl_container_of(listener,server,session_destroy);
    wl_list_remove(&server->session_active.link);wl_list_remove(&server->session_destroy.link);
    server->session=NULL;
}
void madway_power_init(struct madway_server *server)
{
    server->power_initialized=true;
    if (server->session != NULL) {
        server->session_active.notify=active_changed;
        wl_signal_add(&server->session->events.active,&server->session_active);
        server->session_destroy.notify=session_destroyed;
        wl_signal_add(&server->session->events.destroy,&server->session_destroy);
    }
}

static void publish_lid(struct madway_server *server)
{
    server->lid_present=false;server->lid_closed=false;
    struct madway_switch *state;
    wl_list_for_each(state,&server->switches,link) {
        server->lid_present |= state->lid;
        server->lid_closed |= state->lid && state->closed;
    }
    if (server->shutting_down) return;
    madway_arrange_outputs(server);
    madway_session_publish_state(server);
    if (!server->lid_closed) madway_power_resume(server);
}
static void switch_toggle(struct wl_listener *listener,void *data)
{
    struct madway_switch *state=wl_container_of(listener,state,toggle);
    struct wlr_switch_toggle_event *event=data;
    if (event->switch_type != WLR_SWITCH_TYPE_LID) {
        wlr_log(WLR_INFO,"Tablet/folding switch state: %s",event->switch_state==WLR_SWITCH_STATE_ON?"on":"off");return;
    }
    state->lid=true;state->closed=event->switch_state==WLR_SWITCH_STATE_ON;
    wlr_log(WLR_INFO,"Laptop lid %s",state->closed?"closed":"opened");publish_lid(state->server);
}
static void switch_destroy(struct wl_listener *listener,void *data)
{
    (void)data;
    struct madway_switch *state=wl_container_of(listener,state,destroy);
    struct madway_server *server=state->server;
    wl_list_remove(&state->toggle.link);wl_list_remove(&state->destroy.link);wl_list_remove(&state->link);
    free(state);publish_lid(server);
}
void madway_power_add_switch(struct madway_server *server,struct wlr_input_device *device)
{
    struct madway_switch *state=calloc(1,sizeof(*state));
    if (state==NULL) return;
    struct wlr_switch *input=wlr_switch_from_input_device(device);
    state->server=server;
    if (wlr_input_device_is_libinput(device))
        state->lid=libinput_device_switch_has_switch(wlr_libinput_get_device_handle(device),LIBINPUT_SWITCH_LID)>0;
    state->toggle.notify=switch_toggle;wl_signal_add(&input->events.toggle,&state->toggle);
    state->destroy.notify=switch_destroy;wl_signal_add(&device->events.destroy,&state->destroy);
    wl_list_insert(server->switches.prev,&state->link);
    publish_lid(server);
}
void madway_power_finish(struct madway_server *server)
{
    if (!server->power_initialized) return;
    if (server->resume_idle != NULL) {wl_event_source_remove(server->resume_idle);server->resume_idle=NULL;}
    if (server->session != NULL) {
        wl_list_remove(&server->session_active.link);wl_list_remove(&server->session_destroy.link);
    }
    struct madway_switch *state,*tmp;
    wl_list_for_each_safe(state,tmp,&server->switches,link) {
        wl_list_remove(&state->toggle.link);wl_list_remove(&state->destroy.link);wl_list_remove(&state->link);free(state);
    }
    server->power_initialized=false;
}
