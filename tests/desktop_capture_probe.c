/* Private screenshot fixture: arranges real clients and right-clicks empty space. */
#define _GNU_SOURCE
#include "main.h"
#include "view.h"
#include <assert.h>
#include <dlfcn.h>
#include <linux/input-event-codes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <wlr/interfaces/wlr_keyboard.h>
#include <wlr/interfaces/wlr_pointer.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_pointer.h>
static struct madway_server *server;
static struct wlr_keyboard keyboard;
static struct wlr_pointer pointer;
static struct wl_event_source *timer;
static struct wl_listener destroy;
static bool menu_opened;
static const struct wlr_keyboard_impl keyboard_impl={.name="capture-keyboard"};
static const struct wlr_pointer_impl pointer_impl={.name="capture-pointer"};
static int arrange(void *unused)
{
    (void)unused;
    struct madway_view *view;
    wl_list_for_each(view,&server->layout_views,layout_link)
    {
        if(!view->mapped)continue;
        const char *id=view->toplevel->app_id,*title=view->toplevel->title;
        int x=28,y=54,w=700,h=420;
        if(id && !strcmp(id,"org.madway.Settings")){x=28;y=530;w=700;h=420;}
        else if((id && strstr(id,"firefox")) || (title && strstr(title,"Firefox"))){x=760;y=54;w=800;h=650;}
        wlr_scene_node_set_position(&view->scene_tree->node,x,y);
        if(view->toplevel->base->geometry.width!=w || view->toplevel->base->geometry.height!=h)
            wlr_xdg_toplevel_set_size(view->toplevel,w,h);
    }
    const char *command=getenv("MADWAY_CAPTURE_MENU");
    if(!menu_opened && command && access(command,F_OK)==0)
    {
        menu_opened=true;
        struct wlr_pointer_motion_absolute_event motion={.pointer=&pointer,.time_msec=100,.x=1460.0/1600,.y=880.0/1000};
        wl_signal_emit_mutable(&pointer.events.motion_absolute,&motion);
        wl_signal_emit_mutable(&pointer.events.frame,NULL);
        for(int pressed=1;pressed>=0;--pressed)
        {
            struct wlr_pointer_button_event button={.pointer=&pointer,.time_msec=100,.button=BTN_RIGHT,.state=pressed?WL_POINTER_BUTTON_STATE_PRESSED:WL_POINTER_BUTTON_STATE_RELEASED};
            wlr_pointer_notify_button(&pointer,&button);
            wl_signal_emit_mutable(&pointer.events.frame,NULL);
        }
    }
    wl_event_source_timer_update(timer,100);return 0;
}
static void finish(struct wl_listener *listener,void *data)
{
    (void)data;wl_list_remove(&listener->link);wl_event_source_remove(timer);
    wlr_keyboard_finish(&keyboard);wlr_pointer_finish(&pointer);
}
bool wlr_backend_start(struct wlr_backend *backend)
{
    typedef bool(*start_fn)(struct wlr_backend *);
    start_fn real=(start_fn)dlsym(RTLD_NEXT,"wlr_backend_start");
    if(server || wl_list_empty(&backend->events.new_input.listener_list))return real(backend);
    struct wl_listener *listener=wl_container_of(backend->events.new_input.listener_list.next,listener,link);
    server=wl_container_of(listener,server,new_input);
    if(!real(backend))return false;
    wlr_keyboard_init(&keyboard,&keyboard_impl,"capture-keyboard");
    wlr_pointer_init(&pointer,&pointer_impl,"capture-pointer");
    wl_signal_emit_mutable(&backend->events.new_input,&keyboard.base);
    wl_signal_emit_mutable(&backend->events.new_input,&pointer.base);
    destroy.notify=finish;wl_signal_add(&backend->events.destroy,&destroy);
    timer=wl_event_loop_add_timer(wl_display_get_event_loop(server->display),arrange,NULL);
    wl_event_source_timer_update(timer,100);return true;
}
