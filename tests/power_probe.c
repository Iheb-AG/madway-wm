/* Fake native session and switches on headless outputs. No real seat/VT access. */
#define _GNU_SOURCE
#include "main.h"
#include "view.h"
#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <wlr/backend/session.h>
#include <wlr/backend/headless.h>
#include <wlr/backend/multi.h>
#include <wlr/interfaces/wlr_switch.h>
#include <wlr/interfaces/wlr_keyboard.h>
static struct madway_server *server;
static struct wlr_session session;
static struct wlr_switch lid;
static struct wlr_keyboard keyboard;
static struct wlr_backend *headless;
static struct wl_listener output_name, destroy;
static struct wl_event_source *timer;
static int output_count,last_command;
static const struct wlr_switch_impl switch_impl={.name="fake-lid-switch"};
static const struct wlr_keyboard_impl keyboard_impl={.name="fake-power-keyboard"};
static void find_headless(struct wlr_backend *backend,void *data)
{
    (void)data;if(wlr_backend_is_headless(backend))headless=backend;
}
static void name_output(struct wl_listener *listener,void *data)
{
    (void)listener;
    wlr_output_set_name(data,output_count++==0?"eDP-1":"HDMI-A-1");
}
struct wlr_backend *wlr_backend_autocreate(struct wl_event_loop *loop,struct wlr_session **session_ptr)
{
    typedef struct wlr_backend *(*create_fn)(struct wl_event_loop *,struct wlr_session **);
    create_fn real=(create_fn)dlsym(RTLD_NEXT,"wlr_backend_autocreate");
    struct wlr_backend *backend=real(loop,session_ptr);
    assert(backend && *session_ptr==NULL);
    session.active=true;session.event_loop=loop;
    wl_signal_init(&session.events.active);wl_signal_init(&session.events.destroy);
    wl_signal_init(&session.events.add_drm_card);wl_list_init(&session.devices);
    *session_ptr=&session;
    output_name.notify=name_output;wl_signal_add(&backend->events.new_output,&output_name);
    wlr_multi_for_each_backend(backend,find_headless,NULL);assert(headless);
    return backend;
}
static void toggle(bool closed)
{
    struct wlr_switch_toggle_event event={.time_msec=100,.switch_type=WLR_SWITCH_TYPE_LID,
        .switch_state=closed?WLR_SWITCH_STATE_ON:WLR_SWITCH_STATE_OFF};
    wl_signal_emit_mutable(&lid.events.toggle,&event);
}
static int tick(void *data)
{
    (void)data;
    const char *path=getenv("MADWAY_POWER_COMMAND");FILE *file=path?fopen(path,"r"):NULL;
    int command=0;
    if(file){if(fscanf(file,"%d",&command)!=1)command=0;fclose(file);}
    if(command==last_command || !command)goto again;
    last_command=command;
    struct madway_output *internal=NULL,*external=NULL,*output,*tmp;
    wl_list_for_each(output,&server->outputs,link)
        if(output->output->name[0]=='e')internal=output;else external=output;
    if(command==1) {
        assert(server->managing_lid && internal && external && server->config.lid_auto);
        toggle(true);
        assert(!internal->output->enabled && internal->lid_disabled && external->output->enabled);
        fprintf(stderr,"POWER DOCKED LID CLOSE PASS\n");
    } else if(command==2) {
        toggle(false);
        assert(internal && internal->output->enabled && !internal->lid_disabled);
        fprintf(stderr,"POWER LID REOPEN RESTORES SCREEN PASS\n");
    } else if(command==3) {
        assert(internal && external);toggle(true);wlr_output_destroy(external->output);
        assert(internal->output->enabled && !internal->lid_disabled);
        fprintf(stderr,"POWER EXTERNAL UNPLUG RECOVERY PASS\n");
    } else if(command==4) {
        assert(server->sleeping && server->seat->keyboard_state.focused_surface==NULL);
        session.active=false;wl_signal_emit_mutable(&session.events.active,NULL);
        fprintf(stderr,"POWER SESSION INACTIVE PASS\n");
    } else if(command==5) {
        session.active=true;wl_signal_emit_mutable(&session.events.active,NULL);
        fprintf(stderr,"POWER SESSION ACTIVE PASS\n");
    } else if(command==6) {
        wl_list_for_each_safe(output,tmp,&server->outputs,link)wlr_output_destroy(output->output);
        assert(wl_list_empty(&server->outputs));
        fprintf(stderr,"POWER LAST NATIVE OUTPUT REMOVED PASS\n");
    } else if(command==7) {
        assert(wlr_headless_add_output(headless,1280,720));
        fprintf(stderr,"POWER NATIVE OUTPUT RECONNECTED PASS\n");
    } else if(command==8) {
        assert(!server->sleeping && server->focused_view!=NULL);
        assert(server->seat->keyboard_state.focused_surface==server->focused_view->toplevel->base->surface);
        fprintf(stderr,"POWER KEYBOARD FOCUS RESTORED PASS\n");
    }
again:
    wl_event_source_timer_update(timer,70);return 0;
}
static void finish(struct wl_listener *listener,void *data)
{
    (void)data;wl_list_remove(&listener->link);wl_list_remove(&output_name.link);
    wl_event_source_remove(timer);wlr_switch_finish(&lid);wlr_keyboard_finish(&keyboard);
}
bool wlr_backend_start(struct wlr_backend *backend)
{
    typedef bool(*start_fn)(struct wlr_backend *);
    start_fn real=(start_fn)dlsym(RTLD_NEXT,"wlr_backend_start");
    if(server || wl_list_empty(&backend->events.new_input.listener_list))return real(backend);
    struct wl_listener *listener=wl_container_of(backend->events.new_input.listener_list.next,listener,link);
    server=wl_container_of(listener,server,new_input);
    if(!real(backend))return false;
    wlr_switch_init(&lid,&switch_impl,"fake-lid-switch");
    wlr_keyboard_init(&keyboard,&keyboard_impl,"fake-power-keyboard");
    wl_signal_emit_mutable(&backend->events.new_input,&keyboard.base);
    wl_signal_emit_mutable(&backend->events.new_input,&lid.base);toggle(false);
    destroy.notify=finish;wl_signal_add(&backend->events.destroy,&destroy);
    timer=wl_event_loop_add_timer(wl_display_get_event_loop(server->display),tick,NULL);
    wl_event_source_timer_update(timer,70);return true;
}
