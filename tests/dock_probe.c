/* Instrument only the private headless compositor used by dock_smoke.py. */
#define _GNU_SOURCE
#include "main.h"
#include "view.h"
#include "layer.h"
#include "decoration.h"
#include <assert.h>
#include <dlfcn.h>
#include <linux/input-event-codes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <spawn.h>
#include <unistd.h>
#include <time.h>
#include <wlr/interfaces/wlr_keyboard.h>
#include <wlr/interfaces/wlr_pointer.h>

static struct madway_server *server;
static struct wlr_keyboard keyboard;
static struct wlr_pointer pointer;
static struct wl_listener destroy;
static struct wl_event_source *timer;
static int last_command;
static int tooltip_count,tooltip_fits;
static const struct wlr_keyboard_impl keyboard_impl={.name="dock-test-keyboard"};
static const struct wlr_pointer_impl pointer_impl={.name="dock-test-pointer"};

bool wlr_scene_output_commit(struct wlr_scene_output *output,const struct wlr_scene_output_state_options *options)
{
    typedef bool (*fn)(struct wlr_scene_output *,const struct wlr_scene_output_state_options *);
    fn real=(fn)dlsym(RTLD_NEXT,"wlr_scene_output_commit");
    const char *path=getenv("MADWAY_FRAME_TEST");
    if (path && server && (server->window_motion || server->workspace_transition)) {
        struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);
        FILE *trace=fopen(path,"a");
        if (trace) {
            fprintf(trace,"{\"time\":%.9f,\"output\":\"%s\",\"motion\":%s,\"transition\":%s,\"refresh\":%d}\n",
                    now.tv_sec+now.tv_nsec/1e9,output->output->name,server->window_motion?"true":"false",
                    server->workspace_transition?"true":"false",output->output->refresh);
            fclose(trace);
        }
    }
    return real(output,options);
}

void wlr_xdg_popup_unconstrain_from_box(struct wlr_xdg_popup *popup,const struct wlr_box *box)
{
    typedef void (*fn)(struct wlr_xdg_popup *,const struct wlr_box *);
    fn real=(fn)dlsym(RTLD_NEXT,"wlr_xdg_popup_unconstrain_from_box");real(popup,box);
    if (!server || !popup->parent) return;
    struct madway_layer *layer;
    wl_list_for_each(layer,&server->layers,link) {
        if (layer->surface->surface!=popup->parent || strcmp(layer->surface->namespace,"madway-dock")) continue;
        struct wlr_box g=popup->scheduled.geometry;
        ++tooltip_count;
        if (g.x>=box->x && g.y>=box->y && g.x+g.width<=box->x+box->width && g.y+g.height<=box->y+box->height)++tooltip_fits;
    }
}

int posix_spawnp(pid_t *pid,const char *file,const posix_spawn_file_actions_t *actions,
        const posix_spawnattr_t *attributes,char *const arguments[],char *const environment[])
{
    typedef int (*fn)(pid_t *,const char *,const posix_spawn_file_actions_t *,const posix_spawnattr_t *,char *const [],char *const []);
    fn real=(fn)dlsym(RTLD_NEXT,"posix_spawnp");
    size_t count=0;while(environment[count])++count;
    char **clean=calloc(count+1,sizeof(*clean));assert(clean);
    size_t n=0;for(size_t i=0;i<count;++i)if(strncmp(environment[i],"LD_PRELOAD=",11))clean[n++]=environment[i];
    int result=real(pid,file,actions,attributes,arguments,clean);free(clean);return result;
}

static void motion(double x,double y)
{
    struct wlr_box full;wlr_output_layout_get_box(server->output_layout,NULL,&full);
    struct wlr_pointer_motion_absolute_event event={.pointer=&pointer,.time_msec=123,
        .x=(x-full.x)/full.width,.y=(y-full.y)/full.height};
    wl_signal_emit_mutable(&pointer.events.motion_absolute,&event);
    wl_signal_emit_mutable(&pointer.events.frame,NULL);
}
static void key(uint32_t code,bool pressed)
{
    struct wlr_keyboard_key_event event={.time_msec=125,.keycode=code,
        .state=pressed?WL_KEYBOARD_KEY_STATE_PRESSED:WL_KEYBOARD_KEY_STATE_RELEASED,.update_state=true};
    wlr_keyboard_notify_key(&keyboard,&event);
}
static void button(bool pressed)
{
    struct wlr_pointer_button_event event={.pointer=&pointer,.time_msec=126,.button=BTN_LEFT,
        .state=pressed?WL_POINTER_BUTTON_STATE_PRESSED:WL_POINTER_BUTTON_STATE_RELEASED};
    wlr_pointer_notify_button(&pointer,&event);wl_signal_emit_mutable(&pointer.events.frame,NULL);
}
static int glyphs(struct madway_view *view)
{
    if(!view || !view->title_buffer->buffer)return 0;
    void *pixels;uint32_t format;size_t stride;
    if(!wlr_buffer_begin_data_ptr_access(view->title_buffer->buffer,WLR_BUFFER_DATA_PTR_ACCESS_READ,&pixels,&format,&stride))return 0;
    int width=view->frame_width,height=view->frame_title_height,result=0;
    int centers[]={height/2,width-3*height/2,width-height/2};
    for(int i=0;i<3;++i) {
        int white=0;
        for(int y=height/2-4;y<=height/2+4;++y)for(int x=centers[i]-4;x<=centers[i]+4;++x) {
            if(x<0 || x>=width || y<0 || y>=height)continue;
            uint32_t value=*(uint32_t *)((char *)pixels+y*stride+x*4);
            if((value&255)>180 && ((value>>8)&255)>180 && ((value>>16)&255)>180)++white;
        }
        if(white>4)result|=1<<i;
    }
    wlr_buffer_end_data_ptr_access(view->title_buffer->buffer);return result;
}
static int tick(void *unused)
{
    (void)unused;
    const char *root=getenv("MADWAY_DOCK_TEST");char path[1024];
    snprintf(path,sizeof(path),"%s/command",root);FILE *file=fopen(path,"r");int command=0;
    if(file){if(fscanf(file,"%d",&command)!=1)command=0;fclose(file);}
    struct madway_layer *dock=NULL,*layer,*menu=NULL;
    struct madway_view *view=NULL,*entry;
    wl_list_for_each(entry,&server->views,link)
        if(entry->mapped && entry->toplevel->title && !strcmp(entry->toplevel->title,"dock-fixture"))view=entry;
    int other_enabled=0;
    wl_list_for_each(layer,&server->layers,link) {
        if(!strcmp(layer->surface->namespace,"madway-dock")) {
            if(!strcmp(layer->surface->output->name,"HEADLESS-1"))dock=layer;
            else if(layer->tree->node.enabled)++other_enabled;
        }
        if(layer->mapped && !strcmp(layer->surface->namespace,"madway-menu"))menu=layer;
    }
    if(command && command!=last_command && dock) {
        last_command=command;
        struct wlr_box box;wlr_output_layout_get_box(server->output_layout,dock->surface->output,&box);
        if(command==1 || command==7) {
            uint32_t anchor=dock->surface->current.anchor;
            double x=dock->scene_layer->tree->node.x+dock->surface->surface->current.width/2.0;
            double y=dock->scene_layer->tree->node.y+dock->surface->surface->current.height/2.0;
            if(command==7) {motion(x,y);}
            else if(anchor&ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM)motion(x,box.y+box.height-1);
            else if(anchor&ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP)motion(x,box.y+1);
            else if(anchor&ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT)motion(box.x+1,y);
            else motion(box.x+box.width-1,y);
        } else if(command==2 || command==8)motion(box.x+box.width/2.0,box.y+box.height/2.0);
        else if(command==3 && view)motion(view->scene_tree->node.x+11,view->scene_tree->node.y+11);
        else if(command==4) {key(KEY_SYSRQ,true);key(KEY_SYSRQ,false);}
        else if(command==5) {key(KEY_LEFTCTRL,true);key(KEY_SYSRQ,true);key(KEY_SYSRQ,false);key(KEY_LEFTCTRL,false);}
        else if(command==6) {key(KEY_LEFTSHIFT,true);key(KEY_SYSRQ,true);key(KEY_SYSRQ,false);key(KEY_LEFTSHIFT,false);}
        else if(command==9) {motion(20,22);button(true);}
        else if(command==10) {motion(220,300);button(false);}
        else if(command==11) {key(KEY_LEFTALT,true);key(KEY_TAB,true);key(KEY_TAB,false);}
        else if(command==12) {key(KEY_TAB,true);key(KEY_TAB,false);}
        else if(command==13)key(KEY_LEFTALT,false);
        else if(command==14) {key(KEY_ESC,true);key(KEY_ESC,false);key(KEY_LEFTALT,false);}
        else if(command==15) {motion(box.x+box.width/2.0,box.y+box.height/2.0);button(true);button(false);}
        else if(command==20 || command==25) {
            char point[1024];snprintf(point,sizeof(point),"%s/point",root);FILE *position=fopen(point,"r");
            double x=0,y=0;if(position){if(fscanf(position,"%lf %lf",&x,&y)==2)motion(x,y);fclose(position);}
        }
        else if(command==21)button(true);
        else if(command==22)button(false);
        else if(command==23) {key(KEY_ESC,true);key(KEY_ESC,false);}
        else if(command==24 && server->focused_view) {
            struct madway_view *target=server->focused_view;
            wlr_scene_node_set_position(&target->scene_tree->node,500,180);
            target->floating_geometry.x=500;target->floating_geometry.y=180;
        }
        else if(command==26) {
            struct wlr_pointer_button_event event={.pointer=&pointer,.time_msec=127,.button=BTN_RIGHT,.state=WL_POINTER_BUTTON_STATE_PRESSED};
            wlr_pointer_notify_button(&pointer,&event);event.state=WL_POINTER_BUTTON_STATE_RELEASED;wlr_pointer_notify_button(&pointer,&event);
            wl_signal_emit_mutable(&pointer.events.frame,NULL);
        }
        else if(command==27 || command==29 || command==30) {
            key(KEY_HOME,true);key(KEY_HOME,false);
            int down=command==29?1:command==30?3:0;
            for(int i=0;i<down;++i){key(KEY_DOWN,true);key(KEY_DOWN,false);}
            key(KEY_ENTER,true);key(KEY_ENTER,false);
        }
        else if(command==28){key(KEY_ENTER,true);key(KEY_ENTER,false);}
        else if(command==31 || command==32) {
            key(KEY_LEFTCTRL,true);key(command==31?KEY_C:KEY_V,true);key(command==31?KEY_C:KEY_V,false);key(KEY_LEFTCTRL,false);
        }
        else if(command==34 || command==35) {
            uint32_t code=command==34?KEY_END:KEY_UP;
            key(code,true);key(code,false);key(KEY_ENTER,true);key(KEY_ENTER,false);
        }
    }
    snprintf(path,sizeof(path),"%s/probe.tmp",root);file=fopen(path,"w");
    if(file) {
        int motion_width=0,motion_height=0,motion_pixels=0,incoming=0;
        if (server->window_motion) {
            struct wlr_scene_node *node=wl_container_of(server->above_windows->node.link.next,node,link);
            if (node->type==WLR_SCENE_NODE_TREE) {
                struct wlr_scene_tree *tree=wlr_scene_tree_from_node(node);
                if (!wl_list_empty(&tree->children)) {
                    struct wlr_scene_node *child=wl_container_of(tree->children.next,child,link);
                    if (child->type==WLR_SCENE_NODE_BUFFER) {
                        struct wlr_scene_buffer *image=wlr_scene_buffer_from_node(child);
                        motion_width=image->dst_width;motion_height=image->dst_height;
                        motion_pixels=image->buffer?image->buffer->width:0;
                        incoming=wl_list_length(&tree->children)>1;
                    }
                }
            }
        }
        const xkb_keysym_t *symbols=NULL;
        int syms=keyboard.keymap?xkb_keymap_key_get_syms_by_level(keyboard.keymap,KEY_Q+8,0,0,&symbols):0;
        int usable=0;struct madway_output *output;
        wl_list_for_each(output,&server->outputs,link)if(!strcmp(output->output->name,"HEADLESS-1"))usable=output->usable_area.height;
        fprintf(file,"{\"command\":%d,\"enabled\":%s,\"dx\":%d,\"dy\":%d,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d,\"usable\":%d,\"other\":%d,\"glyphs\":%d,\"menu\":%s,\"menu_x\":%d,\"menu_y\":%d,\"transition\":%s,\"key_q\":%u,\"tooltip_count\":%d,\"tooltip_fits\":%d,",
            last_command,dock && dock->tree->node.enabled?"true":"false",dock?dock->tree->node.x:0,dock?dock->tree->node.y:0,
            dock?dock->scene_layer->tree->node.x:0,dock?dock->scene_layer->tree->node.y:0,
            dock?dock->surface->surface->current.width:0,dock?dock->surface->surface->current.height:0,
            usable,other_enabled,glyphs(view),menu?"true":"false",menu?menu->scene_layer->tree->node.x:0,menu?menu->scene_layer->tree->node.y:0,
            server->workspace_transition?"true":"false",syms>0?symbols[0]:0,tooltip_count,tooltip_fits);
        bool desktop_menu_above=false;int desktop_layers=0;
        wl_list_for_each(layer,&server->layers,link)
            if (layer->mapped && !strcmp(layer->surface->namespace,"madway-desktop")) ++desktop_layers;
        double sx,sy;struct wlr_scene_node *hit=wlr_scene_node_at(&server->layer_trees[3]->node,600,220,&sx,&sy);
        if (hit && hit->type==WLR_SCENE_NODE_BUFFER) {
            struct wlr_scene_surface *surface=wlr_scene_surface_try_from_buffer(wlr_scene_buffer_from_node(hit));
            if (surface) wl_list_for_each(layer,&server->layers,link)
                if (!strcmp(layer->surface->namespace,"madway-desktop") &&
                    wl_resource_get_client(surface->surface->resource)==wl_resource_get_client(layer->surface->resource)) desktop_menu_above=true;
        }
        fprintf(file,"\"motion\":%s,\"motion_width\":%d,\"motion_height\":%d,\"motion_pixels\":%d,\"incoming\":%d,\"view_enabled\":%s,\"drag\":%s,\"desktop_menu_above\":%s,\"desktop_layers\":%d}\n",
                server->window_motion?"true":"false",motion_width,motion_height,motion_pixels,incoming,view && view->scene_tree->node.enabled?"true":"false",server->seat->drag?"true":"false",desktop_menu_above?"true":"false",desktop_layers);
        fclose(file);char final[1024];snprintf(final,sizeof(final),"%s/probe.json",root);rename(path,final);
    }
    wl_event_source_timer_update(timer,10);return 0;
}
static void finish(struct wl_listener *listener,void *data)
{
    (void)data;wl_list_remove(&listener->link);wl_event_source_remove(timer);
    wlr_keyboard_finish(&keyboard);wlr_pointer_finish(&pointer);
}
bool wlr_backend_start(struct wlr_backend *backend)
{
    typedef bool (*fn)(struct wlr_backend *);fn real=(fn)dlsym(RTLD_NEXT,"wlr_backend_start");
    if(server || wl_list_empty(&backend->events.new_input.listener_list))return real(backend);
    struct wl_listener *listener=wl_container_of(backend->events.new_input.listener_list.next,listener,link);
    server=wl_container_of(listener,server,new_input);
    if(!real(backend))return false;
    wlr_keyboard_init(&keyboard,&keyboard_impl,"private-dock-keyboard");wlr_pointer_init(&pointer,&pointer_impl,"private-dock-pointer");
    wl_signal_emit_mutable(&backend->events.new_input,&keyboard.base);wl_signal_emit_mutable(&backend->events.new_input,&pointer.base);
    destroy.notify=finish;wl_signal_add(&backend->events.destroy,&destroy);
    timer=wl_event_loop_add_timer(wl_display_get_event_loop(server->display),tick,NULL);
    wl_event_source_timer_update(timer,10);return true;
}
