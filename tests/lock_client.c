/* Test-only protocol client: no authentication. Used only on isolated displays. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include "ext-session-lock-v1-client-protocol.h"
#include <assert.h>
#include <fcntl.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

struct output {
    uint32_t name;
    struct wl_output *output;
    struct wl_surface *surface;
    struct ext_session_lock_surface_v1 *lock_surface;
    struct output *next;
};
static struct wl_display *display;
static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct ext_session_lock_manager_v1 *manager;
static struct ext_session_lock_v1 *lock;
static struct output *outputs;
static bool locked,finished;
static int ready_fd=-1;
static void keymap(void *data,struct wl_keyboard *keyboard,uint32_t format,int fd,uint32_t size)
{(void)data;(void)keyboard;(void)format;(void)size;close(fd);}
static void keyboard_enter(void *data,struct wl_keyboard *keyboard,uint32_t serial,struct wl_surface *surface,struct wl_array *keys)
{(void)data;(void)keyboard;(void)serial;(void)surface;(void)keys;}
static void keyboard_leave(void *data,struct wl_keyboard *keyboard,uint32_t serial,struct wl_surface *surface)
{(void)data;(void)keyboard;(void)serial;(void)surface;}
static void keyboard_key(void *data,struct wl_keyboard *keyboard,uint32_t serial,uint32_t time,uint32_t key,uint32_t state)
{(void)data;(void)keyboard;(void)serial;(void)time;fprintf(stderr,"TEST KEY %u %u\n",key,state);fflush(stderr);}
static void modifiers(void *data,struct wl_keyboard *keyboard,uint32_t serial,uint32_t depressed,uint32_t latched,uint32_t locked_mods,uint32_t group)
{(void)data;(void)keyboard;(void)serial;(void)depressed;(void)latched;(void)locked_mods;(void)group;}
static const struct wl_keyboard_listener keyboard_listener={.keymap=keymap,.enter=keyboard_enter,.leave=keyboard_leave,.key=keyboard_key,.modifiers=modifiers};
static void capabilities(void *data,struct wl_seat *seat,uint32_t caps)
{(void)data;if(caps&WL_SEAT_CAPABILITY_KEYBOARD)wl_keyboard_add_listener(wl_seat_get_keyboard(seat),&keyboard_listener,NULL);}
static const struct wl_seat_listener seat_listener={.capabilities=capabilities};
static void released(void *data,struct wl_buffer *buffer){(void)data;wl_buffer_destroy(buffer);}
static const struct wl_buffer_listener buffer_listener={.release=released};
static void configure(void *data,struct ext_session_lock_surface_v1 *surface,uint32_t serial,uint32_t width,uint32_t height)
{
    struct output *output=data;
    size_t size=(size_t)width*height*4;
    int fd=memfd_create("madway-test-lock",MFD_CLOEXEC);assert(fd>=0 && ftruncate(fd,(off_t)size)==0);
    uint32_t *pixels=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);assert(pixels!=MAP_FAILED);
    for(size_t i=0;i<size/4;++i)pixels[i]=0xff163957;
    struct wl_shm_pool *pool=wl_shm_create_pool(shm,fd,(int)size);
    struct wl_buffer *buffer=wl_shm_pool_create_buffer(pool,0,(int)width,(int)height,(int)width*4,WL_SHM_FORMAT_XRGB8888);
    wl_buffer_add_listener(buffer,&buffer_listener,NULL);wl_shm_pool_destroy(pool);munmap(pixels,size);close(fd);
    ext_session_lock_surface_v1_ack_configure(surface,serial);
    wl_surface_attach(output->surface,buffer,0,0);wl_surface_damage(output->surface,0,0,(int)width,(int)height);wl_surface_commit(output->surface);
    fprintf(stderr,"TEST LOCK SURFACE %ux%u\n",width,height);fflush(stderr);
}
static const struct ext_session_lock_surface_v1_listener surface_listener={.configure=configure};
static void add_surface(struct output *output)
{
    output->surface=wl_compositor_create_surface(compositor);
    output->lock_surface=ext_session_lock_v1_get_lock_surface(lock,output->surface,output->output);
    ext_session_lock_surface_v1_add_listener(output->lock_surface,&surface_listener,output);
}
static void global(void *data,struct wl_registry *registry,uint32_t name,const char *interface,uint32_t version)
{
    (void)data;(void)version;
    if(!strcmp(interface,wl_compositor_interface.name))compositor=wl_registry_bind(registry,name,&wl_compositor_interface,4);
    else if(!strcmp(interface,wl_shm_interface.name))shm=wl_registry_bind(registry,name,&wl_shm_interface,1);
    else if(!strcmp(interface,ext_session_lock_manager_v1_interface.name))manager=wl_registry_bind(registry,name,&ext_session_lock_manager_v1_interface,1);
    else if(!strcmp(interface,wl_seat_interface.name))wl_seat_add_listener(wl_registry_bind(registry,name,&wl_seat_interface,1),&seat_listener,NULL);
    else if(!strcmp(interface,wl_output_interface.name)) {
        struct output *output=calloc(1,sizeof(*output));assert(output);output->name=name;
        output->output=wl_registry_bind(registry,name,&wl_output_interface,1);output->next=outputs;outputs=output;
        if(lock)add_surface(output);
    }
}
static void removed(void *data,struct wl_registry *registry,uint32_t name)
{
    (void)data;(void)registry;
    for(struct output **at=&outputs;*at;at=&(*at)->next)if((*at)->name==name) {
        struct output *output=*at;*at=output->next;
        if(output->lock_surface)ext_session_lock_surface_v1_destroy(output->lock_surface);
        if(output->surface)wl_surface_destroy(output->surface);
        wl_output_destroy(output->output);free(output);break;
    }
}
static const struct wl_registry_listener registry_listener={.global=global,.global_remove=removed};
static void on_locked(void *data,struct ext_session_lock_v1 *object)
{
    (void)data;(void)object;locked=true;fprintf(stderr,"TEST LOCKED\n");fflush(stderr);
    if(ready_fd>=0){assert(write(ready_fd,"\n",1)==1);close(ready_fd);ready_fd=-1;}
}
static void on_finished(void *data,struct ext_session_lock_v1 *object)
{
    (void)data;(void)object;finished=true;fprintf(stderr,"TEST FINISHED\n");fflush(stderr);
}
static const struct ext_session_lock_v1_listener lock_listener={.locked=on_locked,.finished=on_finished};
int main(int argc,char **argv)
{
    for(int i=1;i<argc;++i)if(!strcmp(argv[i],"--ready-fd") && i+1<argc)ready_fd=atoi(argv[++i]);
    display=wl_display_connect(NULL);assert(display);
    struct wl_registry *registry=wl_display_get_registry(display);wl_registry_add_listener(registry,&registry_listener,NULL);
    assert(wl_display_roundtrip(display)>=0 && manager && compositor && shm);
    lock=ext_session_lock_manager_v1_lock(manager);ext_session_lock_v1_add_listener(lock,&lock_listener,NULL);
    for(struct output *output=outputs;output;output=output->next)add_surface(output);
    while(!finished) {
        while(wl_display_prepare_read(display)!=0)if(wl_display_dispatch_pending(display)<0)return 2;
        wl_display_flush(display);
        struct pollfd pollfd={.fd=wl_display_get_fd(display),.events=POLLIN};
        int result=poll(&pollfd,1,30);
        if(result>0){if(wl_display_read_events(display)<0)return 2;if(wl_display_dispatch_pending(display)<0)return 2;}
        else wl_display_cancel_read(display);
        const char *path=getenv("MADWAY_TEST_LOCK_UNLOCK");
        if(locked && path && access(path,F_OK)==0) {
            ext_session_lock_v1_unlock_and_destroy(lock);lock=NULL;wl_display_roundtrip(display);
            fprintf(stderr,"TEST UNLOCKED\n");fflush(stderr);break;
        }
    }
    wl_display_disconnect(display);return finished?3:0;
}
