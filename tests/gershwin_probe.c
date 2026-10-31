/* Private compositor fixture: exercise Eau title controls using virtual input. */
#define _GNU_SOURCE
#include "main.h"
#include "view.h"
#include "decoration.h"
#include <assert.h>
#include <dlfcn.h>
#include <linux/input-event-codes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <wlr/interfaces/wlr_keyboard.h>
#include <wlr/interfaces/wlr_pointer.h>
static struct madway_server *server;
static struct wlr_pointer pointer;
static struct wlr_keyboard keyboard;
static struct wl_listener destroy;
static struct wl_event_source *timer;
static int stage, delay;
static const struct wlr_pointer_impl pointer_impl = {.name="eau-test-pointer"};
static const struct wlr_keyboard_impl keyboard_impl = {.name="eau-test-keyboard"};

static void motion(double x, double y)
{
    struct wlr_pointer_motion_absolute_event event = {.pointer=&pointer,.time_msec=100,.x=x/1280,.y=y/800};
    wl_signal_emit_mutable(&pointer.events.motion_absolute,&event);
    wl_signal_emit_mutable(&pointer.events.frame,NULL);
}
static void click(void)
{
    for (int i=1;i>=0;--i) {
        struct wlr_pointer_button_event event = {.pointer=&pointer,.time_msec=101,.button=BTN_LEFT,
            .state=i ? WL_POINTER_BUTTON_STATE_PRESSED : WL_POINTER_BUTTON_STATE_RELEASED};
        wlr_pointer_notify_button(&pointer,&event);wl_signal_emit_mutable(&pointer.events.frame,NULL);
    }
}
static void key(uint32_t code, enum wl_keyboard_key_state state)
{
    struct wlr_keyboard_key_event event={.time_msec=102,.keycode=code,.state=state,.update_state=true};
    wlr_keyboard_notify_key(&keyboard,&event);
}
static int tick(void *unused)
{
    (void)unused;
    const char *go=getenv("MADWAY_EAU_TEST_GO");
    if (!go || access(go,F_OK)!=0) goto again;
    struct madway_view *view=NULL,*entry;
    wl_list_for_each(entry,&server->views,link)
        if(entry->mapped && entry->toplevel->title && !strcmp(entry->toplevel->title,"eau-client"))view=entry;
    if (!view && stage==6) {
        fprintf(stderr,"EAU TRANSPARENT CORNERS GRADIENT HOVER MINIMIZE ALTTAB MAXIMIZE AND CLOSE PASS\n");stage++;
    }
    if (!view) goto again;
    int width=view->toplevel->base->geometry.width;
    int x=view->scene_tree->node.x,y=view->scene_tree->node.y;
    if (++delay<4) goto again;
    delay=0;
    if(stage==0) {
        assert(server->config.eau && view->frame_title_height==22);
        assert(view->shadow_tree->node.enabled && view->shadows[0] != NULL);
        double sx=0,sy=0;
        assert(!view->shadows[0]->point_accepts_input(view->shadows[0],&sx,&sy));
        assert(!view->borders[0]->node.enabled);
        assert(view->title_buffer->buffer);
        void *data;uint32_t format;size_t stride;
        assert(wlr_buffer_begin_data_ptr_access(view->title_buffer->buffer,WLR_BUFFER_DATA_PTR_ACCESS_READ,&data,&format,&stride));
        uint32_t corner=*(uint32_t *)data;
        uint32_t top=*(uint32_t *)((char *)data+2*stride+width/2*4);
        uint32_t bottom=*(uint32_t *)((char *)data+19*stride+width/2*4);
        assert((corner>>24)==0 && (top>>24)==255 && (top&255)>(bottom&255));
        wlr_buffer_end_data_ptr_access(view->title_buffer->buffer);
        motion(x+11,y+11);stage++;
    } else if(stage==1) {
        assert(view->frame_hover==MADWAY_FRAME_CLOSE);
        motion(x+width-32,y+11);click();stage++;
    } else if(stage==2) {
        assert(view->minimized && !view->scene_tree->node.enabled && server->focused_view!=view);
        key(KEY_LEFTALT,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_TAB,WL_KEYBOARD_KEY_STATE_PRESSED);
        key(KEY_TAB,WL_KEYBOARD_KEY_STATE_RELEASED);key(KEY_LEFTALT,WL_KEYBOARD_KEY_STATE_RELEASED);stage++;
    } else if(stage==3) {
        assert(!view->minimized && view->scene_tree->node.enabled && server->focused_view==view);
        motion(x+width-10,y+11);click();stage++;
    } else if(stage==4) {
        assert(view->maximized && !view->shadow_tree->node.enabled);motion(x+width-10,y+11);click();stage++;
    } else if(stage==5) {
        assert(!view->maximized && view->shadow_tree->node.enabled);motion(x+11,y+11);click();stage++;
    }
again:
    wl_event_source_timer_update(timer,80);return 0;
}
static void finish(struct wl_listener *listener,void *data)
{
    (void)data;wl_list_remove(&listener->link);wl_event_source_remove(timer);
    wlr_pointer_finish(&pointer);wlr_keyboard_finish(&keyboard);
}
bool wlr_backend_start(struct wlr_backend *backend)
{
    typedef bool(*start_fn)(struct wlr_backend *);
    start_fn real=(start_fn)dlsym(RTLD_NEXT,"wlr_backend_start");
    if(server || wl_list_empty(&backend->events.new_input.listener_list))return real(backend);
    struct wl_listener *listener=wl_container_of(backend->events.new_input.listener_list.next,listener,link);
    server=wl_container_of(listener,server,new_input);
    if(!real(backend))return false;
    wlr_pointer_init(&pointer,&pointer_impl,"eau-test-pointer");
    wlr_keyboard_init(&keyboard,&keyboard_impl,"eau-test-keyboard");
    wl_signal_emit_mutable(&backend->events.new_input,&pointer.base);
    wl_signal_emit_mutable(&backend->events.new_input,&keyboard.base);
    destroy.notify=finish;wl_signal_add(&backend->events.destroy,&destroy);
    timer=wl_event_loop_add_timer(wl_display_get_event_loop(server->display),tick,NULL);
    wl_event_source_timer_update(timer,80);return true;
}
