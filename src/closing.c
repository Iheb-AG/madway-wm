#include "closing.h"
#include "main.h"
#include "view.h"
#include "workspace.h"
#include "decoration.h"
#include "preview.h"
#include "motion.h"
#include "transition.h"
#include "animation.h"
#include <stdlib.h>
#include <math.h>
#include <wlr/backend/session.h>
#include <wlr/types/wlr_buffer.h>

/* Owns pixels and an output only: the application/view may already be freed. */
struct closing_window {
    struct wl_list link;
    struct madway_output *output;
    struct wlr_scene_tree *tree;
    struct wlr_scene_buffer *image;
    struct wlr_box from,bounds;
    double started;
    size_t bytes;
};

static void remove_window(struct closing_window *window)
{
    wl_list_remove(&window->link);wlr_scene_node_destroy(&window->tree->node);free(window);
}

void madway_close_cancel(struct madway_server *server,struct madway_output *output)
{
    struct closing_window *window,*next;
    wl_list_for_each_safe(window,next,&server->window_closes,link)
        if(!output || window->output==output)remove_window(window);
}

static bool accepts_input(struct wlr_scene_buffer *buffer,double *sx,double *sy)
{
    (void)buffer;(void)sx;(void)sy;return false;
}

void madway_close_begin(struct madway_view *view)
{
    struct madway_server *server=view->server;
    madway_motion_finish(server);
    if(!server->config.close_animate || !madway_view_visible(view) || view->desktop_overlay ||
            !view->scene_tree->node.enabled || server->shutting_down || server->locked || server->sleeping ||
            (server->session && !server->session->active) || madway_transition_active(view->output))return;
    int border,title;madway_frame_extents(view,&border,&title);
    int width=view->toplevel->base->geometry.width+2*border;
    int height=view->toplevel->base->geometry.height+2*border+title;
    double scale=view->output->output->scale;
    const size_t budget=64u*1024u*1024u;
    double needed=ceil(width*scale)*ceil(height*scale)*4;
    if(width<=0 || height<=0 || needed>budget)return;
    size_t bytes=(size_t)needed,total=0;unsigned count=0;
    struct closing_window *old;
    wl_list_for_each(old,&server->window_closes,link){total+=old->bytes;++count;}
    while(!wl_list_empty(&server->window_closes) && (total+bytes>budget || count>=4)) {
        old=wl_container_of(server->window_closes.next,old,link);total-=old->bytes;--count;remove_window(old);
    }
    struct wlr_buffer *buffer=madway_window_snapshot_alpha(view);
    if(!buffer)return;
    struct closing_window *window=calloc(1,sizeof(*window));
    if(window) {
        window->tree=wlr_scene_tree_create(server->desktop_tree);
        if(window->tree)window->image=wlr_scene_buffer_create(window->tree,buffer);
    }
    wlr_buffer_drop(buffer);
    if(!window)return;
    if(!window->image){if(window->tree)wlr_scene_node_destroy(&window->tree->node);free(window);return;}
    window->output=view->output;window->bytes=bytes;window->started=madway_animation_now();
    window->from=(struct wlr_box){view->scene_tree->node.x,view->scene_tree->node.y,width,height};
    wlr_output_layout_get_box(server->output_layout,view->output->output,&window->bounds);
    window->image->point_accepts_input=accepts_input;
    wlr_scene_buffer_set_dest_size(window->image,width,height);
    wlr_scene_node_set_position(&window->image->node,window->from.x,window->from.y);
    // Focus fallback raises the surviving window inside its window tree. Keep
    // the outgoing image above that tree, below keep-above windows and panels.
    wlr_scene_node_place_above(&window->tree->node,view->keep_above?&server->above_windows->node:&server->windows->node);
    wl_list_insert(server->window_closes.prev,&window->link);
    wlr_output_schedule_frame(view->output->output);
}

bool madway_close_active(struct madway_output *output)
{
    struct closing_window *window;
    wl_list_for_each(window,&output->server->window_closes,link)if(window->output==output)return true;
    return false;
}

void madway_close_frame(struct madway_output *output,double now)
{
    struct madway_server *server=output->server;
    struct closing_window *window,*next;
    wl_list_for_each_safe(window,next,&server->window_closes,link) {
        if(window->output!=output)continue;
        double progress=(now-window->started)/server->config.close_animation_ms;
        if(progress>=1 || !server->config.close_animate || server->locked || server->sleeping ||
                !output->output->enabled || server->shutting_down || (server->session && !server->session->active)) {
            remove_window(window);continue;
        }
        double eased=madway_animation_ease(progress),scale=1-.06*eased;
        int width=(int)lround(window->from.width*scale),height=(int)lround(window->from.height*scale);
        struct wlr_box box={window->from.x+(window->from.width-width)/2,window->from.y+(window->from.height-height)/2,width,height},visible;
        if(!wlr_box_intersection(&visible,&box,&window->bounds)){remove_window(window);continue;}
        struct wlr_buffer *buffer=window->image->buffer;
        struct wlr_fbox crop={(double)(visible.x-box.x)*buffer->width/width,(double)(visible.y-box.y)*buffer->height/height,
            (double)visible.width*buffer->width/width,(double)visible.height*buffer->height/height};
        wlr_scene_buffer_set_source_box(window->image,&crop);
        wlr_scene_buffer_set_dest_size(window->image,visible.width,visible.height);
        wlr_scene_node_set_position(&window->image->node,visible.x,visible.y);
        wlr_scene_buffer_set_opacity(window->image,(float)(1-eased));
    }
}
