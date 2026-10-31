/* Frame-callback-paced fullscreen SHM client. No timers, mouse or keyboard input. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"

static struct wl_display *display;
static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct xdg_wm_base *shell;
static struct wl_surface *surface;
static struct xdg_surface *xdg_surface;
static int width=640,height=360,frames;
static bool configured,closed;
static void draw(void);
static void release(void *data,struct wl_buffer *buffer){(void)data;wl_buffer_destroy(buffer);}
static const struct wl_buffer_listener buffer_listener={.release=release};
static void frame(void *data,struct wl_callback *callback,uint32_t time)
{
    (void)data;wl_callback_destroy(callback);++frames;
    printf("FRAME %d %u\n",frames,time);fflush(stdout);
    if (frames<120)draw();
}
static const struct wl_callback_listener frame_listener={.done=frame};
static void draw(void)
{
    size_t size=(size_t)width*height*4;
    int fd=memfd_create("madway-video-test",MFD_CLOEXEC);assert(fd>=0 && ftruncate(fd,(off_t)size)==0);
    uint32_t *pixels=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);assert(pixels!=MAP_FAILED);
    for(int y=0;y<height;++y)for(int x=0;x<width;++x)pixels[y*width+x]=0xff000000u|((uint32_t)(frames*7%256)<<16)|((uint32_t)(x%256)<<8)|(uint32_t)(y%256);
    struct wl_shm_pool *pool=wl_shm_create_pool(shm,fd,(int)size);
    struct wl_buffer *buffer=wl_shm_pool_create_buffer(pool,0,width,height,width*4,WL_SHM_FORMAT_XRGB8888);
    wl_buffer_add_listener(buffer,&buffer_listener,NULL);wl_shm_pool_destroy(pool);munmap(pixels,size);close(fd);
    wl_callback_add_listener(wl_surface_frame(surface),&frame_listener,NULL);
    wl_surface_attach(surface,buffer,0,0);wl_surface_damage_buffer(surface,0,0,width,height);wl_surface_commit(surface);
}
static void ping(void *data,struct xdg_wm_base *base,uint32_t serial){(void)data;xdg_wm_base_pong(base,serial);}
static const struct xdg_wm_base_listener shell_listener={.ping=ping};
static void configure(void *data,struct xdg_surface *xdg,uint32_t serial)
{
    (void)data;xdg_surface_ack_configure(xdg,serial);
    if(!configured){configured=true;draw();}
}
static const struct xdg_surface_listener surface_listener={.configure=configure};
static void size(void *data,struct xdg_toplevel *top,int32_t w,int32_t h,struct wl_array *states)
{(void)data;(void)top;(void)states;if(!configured && w>0 && h>0){width=w;height=h;}}
static void close_window(void *data,struct xdg_toplevel *top){(void)data;(void)top;closed=true;}
static const struct xdg_toplevel_listener top_listener={.configure=size,.close=close_window};
static void global(void *data,struct wl_registry *registry,uint32_t id,const char *name,uint32_t version)
{
    (void)data;
    if(!strcmp(name,"wl_compositor"))compositor=wl_registry_bind(registry,id,&wl_compositor_interface,version<4?version:4);
    else if(!strcmp(name,"wl_shm"))shm=wl_registry_bind(registry,id,&wl_shm_interface,1);
    else if(!strcmp(name,"xdg_wm_base")){shell=wl_registry_bind(registry,id,&xdg_wm_base_interface,1);xdg_wm_base_add_listener(shell,&shell_listener,NULL);}
}
static void removed(void *data,struct wl_registry *registry,uint32_t id){(void)data;(void)registry;(void)id;}
static const struct wl_registry_listener registry_listener={.global=global,.global_remove=removed};
int main(void)
{
    display=wl_display_connect(NULL);assert(display);
    wl_registry_add_listener(wl_display_get_registry(display),&registry_listener,NULL);
    assert(wl_display_roundtrip(display)>=0 && compositor && shm && shell);
    surface=wl_compositor_create_surface(compositor);xdg_surface=xdg_wm_base_get_xdg_surface(shell,surface);
    xdg_surface_add_listener(xdg_surface,&surface_listener,NULL);
    struct xdg_toplevel *top=xdg_surface_get_toplevel(xdg_surface);xdg_toplevel_add_listener(top,&top_listener,NULL);
    xdg_toplevel_set_title(top,"fullscreen-frame-test");xdg_toplevel_set_app_id(top,"org.madway.VideoTest");
    xdg_toplevel_set_fullscreen(top,NULL);wl_surface_commit(surface);
    while(frames<120 && !closed) {
        while(wl_display_prepare_read(display)!=0)assert(wl_display_dispatch_pending(display)>=0);
        wl_display_flush(display);
        struct pollfd pollfd={.fd=wl_display_get_fd(display),.events=POLLIN};
        int result=poll(&pollfd,1,6000);
        if(result<=0){wl_display_cancel_read(display);fprintf(stderr,"FRAME STALL after %d callbacks\n",frames);return 2;}
        if(wl_display_read_events(display)<0)return 3;
        if(wl_display_dispatch_pending(display)<0)return 3;
    }
    wl_display_disconnect(display);return frames>=120?0:4;
}
