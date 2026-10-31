/* Private-display integration client: commands on stdin, no host interaction. */
#include <assert.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <wayland-client.h>
#include "wlr-foreign-toplevel-management-unstable-v1-client-protocol.h"

struct task {struct zwlr_foreign_toplevel_handle_v1 *handle; char title[256], app[128]; uint32_t state;};
static struct task tasks[128];
static int count;
static struct wl_display *display;
static struct wl_seat *seat;
static struct zwlr_foreign_toplevel_manager_v1 *manager;
static void title(void *data,struct zwlr_foreign_toplevel_handle_v1 *handle,const char *value)
{(void)handle;snprintf(((struct task *)data)->title,256,"%s",value);}
static void app(void *data,struct zwlr_foreign_toplevel_handle_v1 *handle,const char *value)
{(void)handle;snprintf(((struct task *)data)->app,128,"%s",value);}
static void output(void *data,struct zwlr_foreign_toplevel_handle_v1 *handle,struct wl_output *value)
{(void)data;(void)handle;(void)value;}
static void state(void *data,struct zwlr_foreign_toplevel_handle_v1 *handle,struct wl_array *values)
{(void)handle;struct task *task=data;task->state=0;uint32_t *value;wl_array_for_each(value,values)task->state|=1u<<*value;}
static void done(void *data,struct zwlr_foreign_toplevel_handle_v1 *handle)
{(void)handle;struct task *task=data;printf("TASK %s %s %u\n",task->title,task->app,task->state);fflush(stdout);}
static void closed(void *data,struct zwlr_foreign_toplevel_handle_v1 *handle)
{struct task *task=data;printf("CLOSED %s\n",task->title);fflush(stdout);zwlr_foreign_toplevel_handle_v1_destroy(handle);task->handle=NULL;}
static void parent(void *data,struct zwlr_foreign_toplevel_handle_v1 *handle,struct zwlr_foreign_toplevel_handle_v1 *value)
{(void)data;(void)handle;(void)value;}
static const struct zwlr_foreign_toplevel_handle_v1_listener task_listener={
    .title=title,.app_id=app,.output_enter=output,.output_leave=output,.state=state,.done=done,.closed=closed,.parent=parent};
static void toplevel(void *data,struct zwlr_foreign_toplevel_manager_v1 *object,struct zwlr_foreign_toplevel_handle_v1 *handle)
{(void)data;(void)object;assert(count<128);struct task *task=&tasks[count++];task->handle=handle;zwlr_foreign_toplevel_handle_v1_add_listener(handle,&task_listener,task);}
static void finished(void *data,struct zwlr_foreign_toplevel_manager_v1 *object){(void)data;(void)object;}
static const struct zwlr_foreign_toplevel_manager_v1_listener manager_listener={.toplevel=toplevel,.finished=finished};
static void global(void *data,struct wl_registry *registry,uint32_t name,const char *interface,uint32_t version)
{
    (void)data;
    if(!strcmp(interface,zwlr_foreign_toplevel_manager_v1_interface.name)) {
        manager=wl_registry_bind(registry,name,&zwlr_foreign_toplevel_manager_v1_interface,version<3?version:3);
        zwlr_foreign_toplevel_manager_v1_add_listener(manager,&manager_listener,NULL);
    } else if(!strcmp(interface,wl_seat_interface.name))seat=wl_registry_bind(registry,name,&wl_seat_interface,1);
    else if(!strcmp(interface,wl_output_interface.name))wl_registry_bind(registry,name,&wl_output_interface,1);
}
static void removed(void *data,struct wl_registry *registry,uint32_t name){(void)data;(void)registry;(void)name;}
static const struct wl_registry_listener registry_listener={.global=global,.global_remove=removed};
int main(void)
{
    display=wl_display_connect(NULL);assert(display);
    wl_registry_add_listener(wl_display_get_registry(display),&registry_listener,NULL);
    assert(wl_display_roundtrip(display)>=0 && manager && seat);
    assert(wl_display_roundtrip(display)>=0);
    while(1) {
        while(wl_display_prepare_read(display)!=0)assert(wl_display_dispatch_pending(display)>=0);
        wl_display_flush(display);
        struct pollfd fds[2]={{.fd=wl_display_get_fd(display),.events=POLLIN},{.fd=STDIN_FILENO,.events=POLLIN}};
        assert(poll(fds,2,-1)>=0);
        if(fds[0].revents&POLLIN) {if(wl_display_read_events(display)<0)break;}
        else wl_display_cancel_read(display);
        if(wl_display_dispatch_pending(display)<0)break;
        if(fds[1].revents&POLLIN) {
            char command[64];if(!fgets(command,sizeof(command),stdin))break;
            struct task *task=NULL;
            for(int i=0;i<count;++i)if(tasks[i].handle && strstr(tasks[i].title,"dock-fixture")){task=&tasks[i];break;}
            if(!task)continue;
            struct zwlr_foreign_toplevel_handle_v1 *handle=task->handle;
            if(!strncmp(command,"minimize",8))zwlr_foreign_toplevel_handle_v1_set_minimized(handle);
            else if(!strncmp(command,"restore",7)){zwlr_foreign_toplevel_handle_v1_unset_minimized(handle);zwlr_foreign_toplevel_handle_v1_activate(handle,seat);}
            else if(!strncmp(command,"maximize",8))zwlr_foreign_toplevel_handle_v1_set_maximized(handle);
            else if(!strncmp(command,"unmaximize",10))zwlr_foreign_toplevel_handle_v1_unset_maximized(handle);
            else if(!strncmp(command,"fullscreen",10))zwlr_foreign_toplevel_handle_v1_set_fullscreen(handle,NULL);
            else if(!strncmp(command,"unfullscreen",12))zwlr_foreign_toplevel_handle_v1_unset_fullscreen(handle);
            else if(!strncmp(command,"close",5))zwlr_foreign_toplevel_handle_v1_close(handle);
        }
        if(fds[0].revents&(POLLERR|POLLHUP))break;
    }
    wl_display_disconnect(display);return 0;
}
