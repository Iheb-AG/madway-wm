/* A real pointer-gestures client on the test compositor's private socket. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"
#include "pointer-gestures-client-protocol.h"
static struct wl_display *display;
static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct wl_seat *seat;
static struct xdg_wm_base *shell;
static struct zwp_pointer_gestures_v1 *gestures;
static struct wl_surface *surface;
static int drawn;
static void ping(void *data,struct xdg_wm_base *base,uint32_t serial){(void)data;xdg_wm_base_pong(base,serial);}
static const struct xdg_wm_base_listener shell_listener={.ping=ping};
static void configure(void *data,struct xdg_surface *xdg,uint32_t serial)
{
    (void)data;xdg_surface_ack_configure(xdg,serial);if(drawn++)return;
    int size=400*240*4,fd=memfd_create("gesture-fixture",MFD_CLOEXEC);assert(fd>=0 && !ftruncate(fd,size));
    uint32_t *pixels=mmap(NULL,size,PROT_WRITE,MAP_SHARED,fd,0);assert(pixels!=MAP_FAILED);
    for(int i=0;i<400*240;++i)pixels[i]=0xff304050;
    struct wl_shm_pool *pool=wl_shm_create_pool(shm,fd,size);
    struct wl_buffer *buffer=wl_shm_pool_create_buffer(pool,0,400,240,400*4,WL_SHM_FORMAT_XRGB8888);
    wl_shm_pool_destroy(pool);munmap(pixels,size);close(fd);
    wl_surface_attach(surface,buffer,0,0);wl_surface_damage(surface,0,0,400,240);wl_surface_commit(surface);
}
static const struct xdg_surface_listener surface_listener={.configure=configure};
static void size(void *data,struct xdg_toplevel *top,int32_t w,int32_t h,struct wl_array *states){(void)data;(void)top;(void)w;(void)h;(void)states;}
static void closed(void *data,struct xdg_toplevel *top){(void)data;(void)top;}
static const struct xdg_toplevel_listener top_listener={.configure=size,.close=closed};
static void global(void *data,struct wl_registry *registry,uint32_t id,const char *name,uint32_t version)
{
    (void)data;(void)version;
    if(!strcmp(name,"wl_compositor"))compositor=wl_registry_bind(registry,id,&wl_compositor_interface,1);
    else if(!strcmp(name,"wl_shm"))shm=wl_registry_bind(registry,id,&wl_shm_interface,1);
    else if(!strcmp(name,"wl_seat"))seat=wl_registry_bind(registry,id,&wl_seat_interface,1);
    else if(!strcmp(name,"zwp_pointer_gestures_v1"))gestures=wl_registry_bind(registry,id,&zwp_pointer_gestures_v1_interface,3);
    else if(!strcmp(name,"xdg_wm_base")){shell=wl_registry_bind(registry,id,&xdg_wm_base_interface,1);xdg_wm_base_add_listener(shell,&shell_listener,NULL);}
}
static void removed(void *data,struct wl_registry *registry,uint32_t id){(void)data;(void)registry;(void)id;}
static const struct wl_registry_listener registry_listener={.global=global,.global_remove=removed};
static void enter(void *d,struct wl_pointer *p,uint32_t s,struct wl_surface *w,wl_fixed_t x,wl_fixed_t y){(void)d;(void)p;(void)s;(void)w;(void)x;(void)y;}
static void leave(void *d,struct wl_pointer *p,uint32_t s,struct wl_surface *w){(void)d;(void)p;(void)s;(void)w;}
static void motion(void *d,struct wl_pointer *p,uint32_t t,wl_fixed_t x,wl_fixed_t y){(void)d;(void)p;(void)t;(void)x;(void)y;}
static void button(void *d,struct wl_pointer *p,uint32_t s,uint32_t t,uint32_t b,uint32_t st){(void)d;(void)p;(void)s;(void)t;(void)b;(void)st;}
static void axis(void *d,struct wl_pointer *p,uint32_t t,uint32_t a,wl_fixed_t v){(void)d;(void)p;(void)t;(void)a;(void)v;}
static const struct wl_pointer_listener pointer_listener={.enter=enter,.leave=leave,.motion=motion,.button=button,.axis=axis};
#define BEGIN(name,type) static void name(void *d,struct type *g,uint32_t s,uint32_t t,struct wl_surface *w,uint32_t f) \
    {(void)d;(void)g;(void)s;(void)t;(void)w;printf(#name " %u\n",f);fflush(stdout);}
#define END(name,type) static void name(void *d,struct type *g,uint32_t s,uint32_t t,int32_t c) \
    {(void)d;(void)g;(void)s;(void)t;printf(#name " %d\n",c);fflush(stdout);}
BEGIN(swipe_begin,zwp_pointer_gesture_swipe_v1)
BEGIN(pinch_begin,zwp_pointer_gesture_pinch_v1)
BEGIN(hold_begin,zwp_pointer_gesture_hold_v1)
END(swipe_end,zwp_pointer_gesture_swipe_v1)
END(pinch_end,zwp_pointer_gesture_pinch_v1)
END(hold_end,zwp_pointer_gesture_hold_v1)
static void swipe_update(void *d,struct zwp_pointer_gesture_swipe_v1 *g,uint32_t t,wl_fixed_t x,wl_fixed_t y)
{(void)d;(void)g;(void)t;printf("swipe_update %.2f %.2f\n",wl_fixed_to_double(x),wl_fixed_to_double(y));fflush(stdout);}
static void pinch_update(void *d,struct zwp_pointer_gesture_pinch_v1 *g,uint32_t t,wl_fixed_t x,wl_fixed_t y,wl_fixed_t scale,wl_fixed_t rotation)
{(void)d;(void)g;(void)t;printf("pinch_update %.2f %.2f %.2f %.2f\n",wl_fixed_to_double(x),wl_fixed_to_double(y),wl_fixed_to_double(scale),wl_fixed_to_double(rotation));fflush(stdout);}
static const struct zwp_pointer_gesture_swipe_v1_listener swipe_listener={.begin=swipe_begin,.update=swipe_update,.end=swipe_end};
static const struct zwp_pointer_gesture_pinch_v1_listener pinch_listener={.begin=pinch_begin,.update=pinch_update,.end=pinch_end};
static const struct zwp_pointer_gesture_hold_v1_listener hold_listener={.begin=hold_begin,.end=hold_end};
int main(int argc,char **argv)
{
    display=wl_display_connect(NULL);assert(display);
    wl_registry_add_listener(wl_display_get_registry(display),&registry_listener,NULL);
    assert(wl_display_roundtrip(display)>=0 && compositor && shm && seat && shell && gestures);
    struct wl_pointer *pointer=wl_seat_get_pointer(seat);wl_pointer_add_listener(pointer,&pointer_listener,NULL);
    zwp_pointer_gesture_swipe_v1_add_listener(zwp_pointer_gestures_v1_get_swipe_gesture(gestures,pointer),&swipe_listener,NULL);
    zwp_pointer_gesture_pinch_v1_add_listener(zwp_pointer_gestures_v1_get_pinch_gesture(gestures,pointer),&pinch_listener,NULL);
    zwp_pointer_gesture_hold_v1_add_listener(zwp_pointer_gestures_v1_get_hold_gesture(gestures,pointer),&hold_listener,NULL);
    surface=wl_compositor_create_surface(compositor);struct xdg_surface *xdg=xdg_wm_base_get_xdg_surface(shell,surface);
    xdg_surface_add_listener(xdg,&surface_listener,NULL);struct xdg_toplevel *top=xdg_surface_get_toplevel(xdg);
    xdg_toplevel_add_listener(top,&top_listener,NULL);xdg_toplevel_set_title(top,argc>1?argv[1]:"gesture-fixture");
    wl_surface_commit(surface);while(wl_display_dispatch(display)>=0){}
    wl_display_disconnect(display);return 0;
}
