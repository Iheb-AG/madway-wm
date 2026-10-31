/* Private headless instrumentation: presentation barrier, virtual input, hotplug. */
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
#include <spawn.h>
#include <wlr/backend/headless.h>
#include <wlr/backend/multi.h>
#include <wlr/interfaces/wlr_keyboard.h>
#include <wlr/interfaces/wlr_pointer.h>
#include <wlr/interfaces/wlr_output.h>
#include <wlr/types/wlr_session_lock_v1.h>
static struct madway_server *server;
static struct wlr_keyboard keyboard;
static struct wlr_pointer pointer;
static struct wlr_backend *headless;
static struct wl_listener destroy;
static struct wl_event_source *timer;
static struct wlr_output *held_output,*hotplug;
static struct wlr_output_event_present held_event;
static int last_command;
static bool held_password_key;
static const struct wlr_keyboard_impl keyboard_impl={.name="private-lock-keyboard"};
static const struct wlr_pointer_impl pointer_impl={.name="private-lock-pointer"};
void wlr_seat_keyboard_notify_enter(struct wlr_seat *seat,struct wlr_surface *surface,const uint32_t keys[],size_t count,const struct wlr_keyboard_modifiers *mods)
{
    typedef void(*enter_fn)(struct wlr_seat *,struct wlr_surface *,const uint32_t [],size_t,const struct wlr_keyboard_modifiers *);
    enter_fn real=(enter_fn)dlsym(RTLD_NEXT,"wlr_seat_keyboard_notify_enter");
    if(server && held_password_key && !server->locked) {
        for(size_t i=0;i<count;++i)assert(keys[i]!=KEY_B);
        fprintf(stderr,"LOCK HELD PASSWORD KEY OMITTED ON DESKTOP ENTER\n");
    }
    real(seat,surface,keys,count,mods);
}
void wlr_seat_keyboard_notify_key(struct wlr_seat *seat,uint32_t time,uint32_t code,uint32_t state)
{
    typedef void(*key_fn)(struct wlr_seat *,uint32_t,uint32_t,uint32_t);
    key_fn real=(key_fn)dlsym(RTLD_NEXT,"wlr_seat_keyboard_notify_key");
    assert(!(server && held_password_key && !server->locked && code==KEY_B));
    real(seat,time,code,state);
}
int posix_spawnp(pid_t *pid,const char *file,const posix_spawn_file_actions_t *actions,
    const posix_spawnattr_t *attributes,char *const arguments[],char *const environment[])
{
    typedef int(*spawn_fn)(pid_t *,const char *,const posix_spawn_file_actions_t *,const posix_spawnattr_t *,char *const [],char *const []);
    spawn_fn real=(spawn_fn)dlsym(RTLD_NEXT,"posix_spawnp");
    size_t count=0;while(environment[count])++count;
    char **clean=calloc(count+1,sizeof(*clean));assert(clean);
    size_t at=0;for(size_t i=0;i<count;++i)if(strncmp(environment[i],"LD_PRELOAD=",11))clean[at++]=environment[i];
    int result=real(pid,file,actions,attributes,arguments,clean);free(clean);return result;
}
static void find_headless(struct wlr_backend *backend,void *data)
{(void)data;if(wlr_backend_is_headless(backend))headless=backend;}
void wlr_output_send_present(struct wlr_output *output,struct wlr_output_event_present *event)
{
    typedef void(*present_fn)(struct wlr_output *,struct wlr_output_event_present *);
    present_fn real=(present_fn)dlsym(RTLD_NEXT,"wlr_output_send_present");
    const char *path=getenv("MADWAY_LOCK_RELEASE_PRESENT");
    if(server && server->locked && path && access(path,F_OK)!=0 && !strcmp(output->name,"HEADLESS-2")) {
        held_output=output;held_event=*event;return;
    }
    real(output,event);
}
static void key(uint32_t code,bool pressed)
{
    struct wlr_keyboard_key_event event={.time_msec=100,.keycode=code,.state=pressed?WL_KEYBOARD_KEY_STATE_PRESSED:WL_KEYBOARD_KEY_STATE_RELEASED,.update_state=true};
    wlr_keyboard_notify_key(&keyboard,&event);
}
static int tick(void *unused)
{
    (void)unused;
    const char *release=getenv("MADWAY_LOCK_RELEASE_PRESENT");
    if(held_output && release && access(release,F_OK)==0) {
        typedef void(*present_fn)(struct wlr_output *,struct wlr_output_event_present *);
        present_fn real=(present_fn)dlsym(RTLD_NEXT,"wlr_output_send_present");
        real(held_output,&held_event);held_output=NULL;
        fprintf(stderr,"LOCK SECOND OUTPUT PRESENTATION RELEASED\n");
    }
    const char *path=getenv("MADWAY_LOCK_TEST_COMMAND");FILE *file=path?fopen(path,"r"):NULL;
    int command=0;if(file){if(fscanf(file,"%d",&command)!=1)command=0;fclose(file);}
    if(!command || command==last_command)goto again;
    last_command=command;
    if(command==1) {
        assert(server->locked && !server->desktop_tree->node.enabled);
        struct madway_view *view;
        wl_list_for_each(view,&server->views,link)assert(view->task==NULL);
        assert(wlr_session_lock_surface_v1_try_from_wlr_surface(server->seat->keyboard_state.focused_surface));
        unsigned workspace=server->active_workspace;int views=wl_list_length(&server->views);
        key(KEY_LEFTALT,true);
        key(KEY_ENTER,true);key(KEY_ENTER,false);key(KEY_ESC,true);key(KEY_ESC,false);
        key(KEY_2,true);key(KEY_2,false);key(KEY_D,true);key(KEY_D,false);key(KEY_LEFTALT,false);
        key(KEY_A,true);key(KEY_A,false);
        assert(server->active_workspace==workspace && wl_list_length(&server->views)==views);
        struct wlr_pointer_motion_absolute_event motion={.pointer=&pointer,.time_msec=120,.x=.3,.y=.4};
        wl_signal_emit_mutable(&pointer.events.motion_absolute,&motion);
        for(int i=1;i>=0;--i) {
            struct wlr_pointer_button_event button={.pointer=&pointer,.time_msec=121,.button=BTN_RIGHT,.state=i?WL_POINTER_BUTTON_STATE_PRESSED:WL_POINTER_BUTTON_STATE_RELEASED};
            wlr_pointer_notify_button(&pointer,&button);
        }
        fprintf(stderr,"LOCK SHORTCUTS INPUT FOCUS AND RIGHT CLICK ISOLATION PASS\n");
    } else if(command==2) {
        hotplug=wlr_headless_add_output(headless,800,600);assert(hotplug);
        fprintf(stderr,"LOCK OUTPUT HOTPLUG ADDED\n");
    } else if(command==3) {
        assert(hotplug);wlr_output_destroy(hotplug);hotplug=NULL;
        fprintf(stderr,"LOCK OUTPUT HOTPLUG REMOVED\n");
    } else if(command==4) {
        assert(server->locked);key(KEY_B,true);held_password_key=true;
        fprintf(stderr,"LOCK PASSWORD KEY HELD\n");
    } else if(command==5) {
        assert(!server->locked && held_password_key);key(KEY_B,false);held_password_key=false;
        fprintf(stderr,"LOCK PASSWORD KEY RELEASE CONSUMED PASS\n");
    }
again:wl_event_source_timer_update(timer,35);return 0;
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
    wlr_keyboard_init(&keyboard,&keyboard_impl,"private-lock-keyboard");
    wlr_pointer_init(&pointer,&pointer_impl,"private-lock-pointer");
    wl_signal_emit_mutable(&backend->events.new_input,&keyboard.base);wl_signal_emit_mutable(&backend->events.new_input,&pointer.base);
    wlr_multi_for_each_backend(backend,find_headless,NULL);assert(headless);
    destroy.notify=finish;wl_signal_add(&backend->events.destroy,&destroy);
    timer=wl_event_loop_add_timer(wl_display_get_event_loop(server->display),tick,NULL);wl_event_source_timer_update(timer,35);return true;
}
