/* Drives only a private parent compositor; observes its nested child. */
#define _GNU_SOURCE
#include "main.h"
#include "view.h"
#include <assert.h>
#include <dlfcn.h>
#include <linux/input-event-codes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <wlr/backend/wayland.h>
#include <wlr/interfaces/wlr_keyboard.h>
#include <wlr/interfaces/wlr_pointer.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_pointer.h>

static struct madway_server *server;
static struct wlr_keyboard keyboard;
static struct wlr_pointer pointer;
static struct wl_event_source *timer;
static struct wl_listener destroy;
static bool parent;
static unsigned last_command;
static const struct wlr_keyboard_impl keyboard_impl = {.name="nested-test-keyboard"};
static const struct wlr_pointer_impl pointer_impl = {.name="nested-test-pointer"};
static const char *last_pointer="";
static unsigned cursor_updates;

void wlr_cursor_set_xcursor(struct wlr_cursor *cursor, struct wlr_xcursor_manager *manager, const char *name)
{
    typedef void (*set_fn)(struct wlr_cursor *, struct wlr_xcursor_manager *, const char *);
    set_fn real=(set_fn)dlsym(RTLD_NEXT,"wlr_cursor_set_xcursor");
    ++cursor_updates;real(cursor,manager,name);
}

void wlr_cursor_warp_absolute(struct wlr_cursor *cursor, struct wlr_input_device *device, double x, double y)
{
    typedef void (*warp_fn)(struct wlr_cursor *, struct wlr_input_device *, double, double);
    warp_fn real=(warp_fn)dlsym(RTLD_NEXT,"wlr_cursor_warp_absolute");
    real(cursor,device,x,y);
    if (!parent && device && device->type==WLR_INPUT_DEVICE_POINTER)
    {
        struct wlr_pointer *source=wlr_pointer_from_input_device(device);
        last_pointer=source->output_name ? source->output_name : "(unmapped)";
    }
}

static void key(uint32_t code, enum wl_keyboard_key_state state)
{
    struct wlr_keyboard_key_event event={.time_msec=100,.keycode=code,.state=state,.update_state=true};
    wlr_keyboard_notify_key(&keyboard,&event);
}
static void move(double x, double y)
{
    struct madway_output *output=wl_container_of(server->outputs.next,output,link);
    int width,height;wlr_output_effective_resolution(output->output,&width,&height);
    struct wlr_pointer_motion_absolute_event event={.pointer=&pointer,.time_msec=100,.x=x/width,.y=y/height};
    wl_signal_emit_mutable(&pointer.events.motion_absolute,&event);
    wl_signal_emit_mutable(&pointer.events.frame,NULL);
}
static void button(uint32_t code,enum wl_pointer_button_state state)
{
    struct wlr_pointer_button_event event={.pointer=&pointer,.time_msec=100,.button=code,.state=state};
    wlr_pointer_notify_button(&pointer,&event);
    wl_signal_emit_mutable(&pointer.events.frame,NULL);
}
static int tick(void *unused)
{
    (void)unused;
    char path[512],temporary[512];
    const char *directory=getenv("MADWAY_POINTER_TEST_DIR");
    snprintf(path,sizeof(path),"%s/%s.json",directory,parent?"parent":"child");
    snprintf(temporary,sizeof(temporary),"%s/%s.tmp",directory,parent?"parent":"child");
    FILE *file=fopen(temporary,"w");assert(file);
    if(parent)
    {
        fprintf(file,"{\"cursor\":[%.3f,%.3f],\"buttons\":%zu,\"focused_surface\":%u,\"views\":[", server->cursor->x,server->cursor->y,server->seat->pointer_state.button_count,server->seat->pointer_state.focused_surface?wl_resource_get_id(server->seat->pointer_state.focused_surface->resource):0);
        bool first=true;int position=32;
        struct madway_view *view;
        wl_list_for_each(view,&server->layout_views,layout_link)
        {
            if(!view->mapped)continue;
            wlr_scene_node_set_position(&view->scene_tree->node,position,32);
            int x,y;wlr_scene_node_coords(&view->content_tree->node,&x,&y);
            fprintf(file,"%s{\"surface\":%u,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}",first?"":",",
                    wl_resource_get_id(view->toplevel->base->surface->resource),x,y,view->toplevel->base->geometry.width,view->toplevel->base->geometry.height);
            first=false;position+=view->toplevel->base->geometry.width+64;
        }
        fprintf(file,"]}");
    }
    else
    {
        fprintf(file,"{\"cursor\":[%.6f,%.6f],\"cursor_updates\":%u,\"primary\":%s,\"pointer\":\"%s\",\"outputs\":[",server->cursor->x,server->cursor->y,cursor_updates,server->seat->primary_selection_source?"true":"false",last_pointer);
        bool first=true;struct madway_output *output;
        wl_list_for_each(output,&server->outputs,link)
        {
            if(!wlr_output_is_wl(output->output))continue;
            int width,height;wlr_output_effective_resolution(output->output,&width,&height);
            fprintf(file,"%s{\"name\":\"%s\",\"surface\":%u,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d,\"pixels_w\":%d,\"pixels_h\":%d}",
                    first?"":",",output->output->name,wl_proxy_get_id((struct wl_proxy *)wlr_wl_output_get_surface(output->output)),
                    output->layout_x,output->layout_y,width,height,output->output->width,output->output->height);
            first=false;
        }
        fprintf(file,"],\"views\":[");first=true;
        struct madway_view *view;
        wl_list_for_each(view,&server->layout_views,layout_link)
        {
            if(!view->mapped)continue;
            fprintf(file,"%s{\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d,\"focused\":%s,\"pointer_focus\":%s,\"output\":\"%s\"}",
                    first?"":",",view->scene_tree->node.x,view->scene_tree->node.y,view->toplevel->base->geometry.width,
                    view->toplevel->base->geometry.height,server->focused_view==view?"true":"false",
                    server->seat->pointer_state.focused_surface==view->toplevel->base->surface?"true":"false",
                    view->output?view->output->output->name:"");first=false;
        }
        fprintf(file,"]}");
    }
    fclose(file);assert(rename(temporary,path)==0);
    if(parent)
    {
        snprintf(path,sizeof(path),"%s/command",directory);
        file=fopen(path,"r");
        if(file)
        {
            unsigned serial,code;double x,y;int state;
            if(fscanf(file,"%u %u %lf %lf %d",&serial,&code,&x,&y,&state)==5 && serial!=last_command)
            {
                last_command=serial;
                if(code==0)move(x,y);
                else if(code==1)button((uint32_t)x,(enum wl_pointer_button_state)state);
                else if(code==2)key((uint32_t)x,(enum wl_keyboard_key_state)state);
                snprintf(path,sizeof(path),"%s/ack",directory);
                FILE *ack=fopen(path,"w");assert(ack);fprintf(ack,"%u",serial);fclose(ack);
            }
            fclose(file);
        }
    }
    wl_event_source_timer_update(timer,10);return 0;
}
static void finish(struct wl_listener *listener,void *unused)
{
    (void)unused;wl_list_remove(&listener->link);wl_event_source_remove(timer);
    if(parent){wlr_keyboard_finish(&keyboard);wlr_pointer_finish(&pointer);}
}
bool wlr_backend_start(struct wlr_backend *backend)
{
    typedef bool(*start_fn)(struct wlr_backend *);
    start_fn real=(start_fn)dlsym(RTLD_NEXT,"wlr_backend_start");
    if(server || wl_list_empty(&backend->events.new_input.listener_list))return real(backend);
    struct wl_listener *listener=wl_container_of(backend->events.new_input.listener_list.next,listener,link);
    server=wl_container_of(listener,server,new_input);
    parent=!strcmp(getenv("MADWAY_POINTER_TEST_ROLE"),"parent");
    bool ok=real(backend);if(!ok)return false;
    if(parent)
    {
        struct madway_output *output=wl_container_of(server->outputs.next,output,link);
        struct wlr_output_state state;wlr_output_state_init(&state);
        wlr_output_state_set_custom_mode(&state,3000,1800,60000);
        struct wlr_output_event_request_state request={.state=&state};
        wl_signal_emit_mutable(&output->output->events.request_state,&request);
        wlr_output_state_finish(&state);
        wlr_keyboard_init(&keyboard,&keyboard_impl,"nested-test-keyboard");
        wlr_pointer_init(&pointer,&pointer_impl,"nested-test-pointer");
        wl_signal_emit_mutable(&backend->events.new_input,&keyboard.base);
        wl_signal_emit_mutable(&backend->events.new_input,&pointer.base);
    }
    destroy.notify=finish;wl_signal_add(&backend->events.destroy,&destroy);
    timer=wl_event_loop_add_timer(wl_display_get_event_loop(server->display),tick,NULL);
    wl_event_source_timer_update(timer,10);return true;
}
