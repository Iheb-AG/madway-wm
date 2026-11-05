/* Private headless gesture injection; never opens a host input device. */
#define _GNU_SOURCE
#include "main.h"
#include "view.h"
#include <assert.h>
#include <dlfcn.h>
#include <linux/input-event-codes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wlr/interfaces/wlr_keyboard.h>
#include <wlr/interfaces/wlr_pointer.h>

static struct madway_server *server;
static struct wlr_pointer pointers[2];
static bool attached[2];
static struct wlr_keyboard keyboard;
static struct wl_listener destroy;
static struct wl_event_source *timer;
static unsigned last_command,time_ms;
static const struct wlr_pointer_impl pointer_impl={.name="private-gesture-pointer"};
static const struct wlr_keyboard_impl keyboard_impl={.name="private-gesture-keyboard"};

static void attach(unsigned index)
{
    if(attached[index])return;
    wlr_pointer_init(&pointers[index],&pointer_impl,"private-gesture-pointer");
    wl_signal_emit_mutable(&server->backend->events.new_input,&pointers[index].base);
    attached[index]=true;
}

static void inject(const char *op,double x,double y,unsigned fingers,unsigned device)
{
    struct wlr_pointer *pointer=&pointers[device];time_ms+=10;
    if(!strcmp(op,"sb")) {
        struct wlr_pointer_swipe_begin_event event={.pointer=pointer,.time_msec=time_ms,.fingers=fingers};
        wl_signal_emit_mutable(&pointer->events.swipe_begin,&event);
    } else if(!strcmp(op,"su")) {
        struct wlr_pointer_swipe_update_event event={.pointer=pointer,.time_msec=time_ms,.fingers=fingers,.dx=x,.dy=y};
        wl_signal_emit_mutable(&pointer->events.swipe_update,&event);
    } else if(!strcmp(op,"se")) {
        struct wlr_pointer_swipe_end_event event={.pointer=pointer,.time_msec=time_ms,.cancelled=x!=0};
        wl_signal_emit_mutable(&pointer->events.swipe_end,&event);
    } else if(!strcmp(op,"pb")) {
        struct wlr_pointer_pinch_begin_event event={.pointer=pointer,.time_msec=time_ms,.fingers=fingers};
        wl_signal_emit_mutable(&pointer->events.pinch_begin,&event);
    } else if(!strcmp(op,"pu")) {
        struct wlr_pointer_pinch_update_event event={.pointer=pointer,.time_msec=time_ms,.fingers=fingers,.dx=2,.dy=3,.scale=x,.rotation=y};
        wl_signal_emit_mutable(&pointer->events.pinch_update,&event);
    } else if(!strcmp(op,"pe")) {
        struct wlr_pointer_pinch_end_event event={.pointer=pointer,.time_msec=time_ms,.cancelled=x!=0};
        wl_signal_emit_mutable(&pointer->events.pinch_end,&event);
    } else if(!strcmp(op,"hb")) {
        struct wlr_pointer_hold_begin_event event={.pointer=pointer,.time_msec=time_ms,.fingers=fingers};
        wl_signal_emit_mutable(&pointer->events.hold_begin,&event);
    } else if(!strcmp(op,"he")) {
        struct wlr_pointer_hold_end_event event={.pointer=pointer,.time_msec=time_ms,.cancelled=x!=0};
        wl_signal_emit_mutable(&pointer->events.hold_end,&event);
    } else if(!strcmp(op,"focus")) {
        struct madway_view *view;
        bool found=false;
        wl_list_for_each(view,&server->views,link) {
            if(view->mapped && view->toplevel->title &&
                !strcmp(view->toplevel->title,x==1?"gesture-fixture":"gesture-other")) {
                wlr_seat_pointer_notify_enter(server->seat,view->toplevel->base->surface,20,20);found=true;break;
            }
        }
        if(!found || x==0)wlr_seat_pointer_notify_clear_focus(server->seat);
    } else if(!strcmp(op,"button")) {
        struct wlr_pointer_button_event event={.pointer=pointer,.time_msec=time_ms,.button=BTN_LEFT,
            .state=x?WL_POINTER_BUTTON_STATE_PRESSED:WL_POINTER_BUTTON_STATE_RELEASED};
        wlr_pointer_notify_button(pointer,&event);
    } else if(!strcmp(op,"escape")) {
        struct wlr_keyboard_key_event event={.time_msec=time_ms,.keycode=KEY_ESC,.state=WL_KEYBOARD_KEY_STATE_PRESSED,.update_state=true};
        wlr_keyboard_notify_key(&keyboard,&event);event.state=WL_KEYBOARD_KEY_STATE_RELEASED;wlr_keyboard_notify_key(&keyboard,&event);
    } else if(!strcmp(op,"remove")) {
        wlr_pointer_finish(pointer);attached[device]=false;
    } else if(!strcmp(op,"add"))attach(device);
}

static int tick(void *unused)
{
    (void)unused;const char *root=getenv("MADWAY_GESTURE_TEST");char path[1024];
    snprintf(path,sizeof(path),"%s/command",root);FILE *file=fopen(path,"r");
    if(file) {
        unsigned command,fingers,device;char op[32];double x,y;
        if(fscanf(file,"%u %31s %lf %lf %u %u",&command,op,&x,&y,&fingers,&device)==6 && command!=last_command) {
            assert(device<2);last_command=command;inject(op,x,y,fingers,device);
        }
        fclose(file);
    }
    snprintf(path,sizeof(path),"%s/state.tmp",root);file=fopen(path,"w");assert(file);
    fprintf(file,"{\"command\":%u,\"workspace\":%u,\"transition\":%s,\"sleeping\":%s,\"locked\":%s,\"enabled\":%s,\"invert\":%s,\"threshold\":%d}\n",
        last_command,server->active_workspace,server->workspace_transition?"true":"false",server->sleeping?"true":"false",server->locked?"true":"false",
        server->config.workspace_swipe?"true":"false",server->config.swipe_invert?"true":"false",server->config.swipe_threshold);
    fclose(file);char target[1024];snprintf(target,sizeof(target),"%s/state.json",root);rename(path,target);
    wl_event_source_timer_update(timer,10);return 0;
}

static void finished(struct wl_listener *listener,void *data)
{
    (void)data;wl_list_remove(&listener->link);wl_event_source_remove(timer);
    for(unsigned i=0;i<2;++i)if(attached[i])wlr_pointer_finish(&pointers[i]);
    wlr_keyboard_finish(&keyboard);
}

bool wlr_backend_start(struct wlr_backend *backend)
{
    typedef bool(*start_fn)(struct wlr_backend *);start_fn real=(start_fn)dlsym(RTLD_NEXT,"wlr_backend_start");
    if(server || wl_list_empty(&backend->events.new_input.listener_list))return real(backend);
    struct wl_listener *listener=wl_container_of(backend->events.new_input.listener_list.next,listener,link);
    server=wl_container_of(listener,server,new_input);if(!real(backend))return false;
    attach(0);attach(1);wlr_keyboard_init(&keyboard,&keyboard_impl,"private-gesture-keyboard");
    wl_signal_emit_mutable(&backend->events.new_input,&keyboard.base);
    destroy.notify=finished;wl_signal_add(&backend->events.destroy,&destroy);
    timer=wl_event_loop_add_timer(wl_display_get_event_loop(server->display),tick,NULL);
    wl_event_source_timer_update(timer,10);return true;
}
