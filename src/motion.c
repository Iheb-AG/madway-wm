#include "motion.h"
#include "main.h"
#include "view.h"
#include "preview.h"
#include "transition.h"
#include "dock.h"
#include "layer.h"
#include "decoration.h"
#include "workspace.h"
#include "input.h"
#include "animation.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wlr/backend/session.h>
#include <wlr/types/wlr_buffer.h>

struct madway_motion {
    struct madway_view *view;
    struct wlr_scene_tree *tree;
    struct wlr_scene_buffer *image,*incoming;
    struct wlr_box from,to,bounds,visual;
    double started,progress;
    double opacity_from,opacity;
    bool running,reveal,minimizing,restoring,continuing;
};

void madway_motion_finish(struct madway_server *server)
{
    struct madway_motion *motion=server->window_motion;
    if (!motion) return;
    server->window_motion=NULL;
    if (motion->running && motion->view->mapped)
        wlr_scene_node_set_enabled(&motion->view->scene_tree->node,motion->reveal && madway_view_visible(motion->view));
    wlr_scene_node_destroy(&motion->tree->node);
    free(motion);
}

void madway_motion_cancel_running(struct madway_server *server)
{
    if (server->window_motion && server->window_motion->running) madway_motion_finish(server);
}

void madway_motion_focus(struct madway_server *server,struct madway_view *view)
{
    if (server->window_motion && server->window_motion->view!=view) madway_motion_cancel_running(server);
}

static struct wlr_box window_box(struct madway_view *view,bool configured)
{
    int border,title;madway_frame_extents(view,&border,&title);
    int width=view->toplevel->base->geometry.width,height=view->toplevel->base->geometry.height;
    if (configured && view->toplevel->scheduled.width>0 && view->toplevel->scheduled.height>0) {
        width=view->toplevel->scheduled.width;height=view->toplevel->scheduled.height;
    }
    return (struct wlr_box){view->scene_tree->node.x,view->scene_tree->node.y,width+2*border,height+2*border+title};
}

static struct wlr_box minimize_target(struct madway_motion *motion)
{
    struct wlr_box bounds=motion->bounds;
    double ratio=(double)motion->from.width/fmax(1,motion->from.height);
    int width=ratio>=1?48:(int)lround(40*ratio),height=ratio>=1?(int)lround(48/ratio):40;
    if (width<8) width=8;
    if (height<8) height=8;
    struct wlr_box target={bounds.x+bounds.width/2-width/2,bounds.y+bounds.height-height-4,width,height};
    struct madway_layer *layer;
    wl_list_for_each(layer,&motion->view->server->layers,link) {
        if (!layer->mapped || layer->surface->output!=motion->view->output->output ||
            strcmp(layer->surface->namespace,"madway-dock")) continue;
        uint32_t anchors=layer->surface->current.anchor;
        bool vertical=(anchors&ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP) && (anchors&ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM);
        if (vertical) {
            target.x=anchors&ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT?bounds.x+4:bounds.x+bounds.width-width-4;
            target.y=bounds.y+bounds.height/2-height/2;
        } else if (anchors&ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP) target.y=bounds.y+4;
        break;
    }
    return target;
}

static void place_image(struct madway_motion *motion,struct wlr_scene_buffer *image,struct wlr_box box,float opacity)
{
    struct wlr_box visible;
    if (!wlr_box_intersection(&visible,&box,&motion->bounds) || box.width<=0 || box.height<=0) {
        wlr_scene_node_set_enabled(&image->node,false);return;
    }
    struct wlr_buffer *buffer=image->buffer;
    struct wlr_fbox crop={(double)(visible.x-box.x)*buffer->width/box.width,
        (double)(visible.y-box.y)*buffer->height/box.height,
        (double)visible.width*buffer->width/box.width,(double)visible.height*buffer->height/box.height};
    wlr_scene_buffer_set_source_box(image,&crop);
    wlr_scene_buffer_set_dest_size(image,visible.width,visible.height);
    wlr_scene_buffer_set_opacity(image,opacity);
    wlr_scene_node_set_position(&image->node,visible.x,visible.y);
    wlr_scene_node_set_enabled(&image->node,true);
}

static void position(struct madway_motion *motion,double progress)
{
    double eased=madway_animation_ease(progress);
    struct wlr_box box={
        motion->from.x+(int)lround((motion->to.x-motion->from.x)*eased),
        motion->from.y+(int)lround((motion->to.y-motion->from.y)*eased),
        motion->from.width+(int)lround((motion->to.width-motion->from.width)*eased),
        motion->from.height+(int)lround((motion->to.height-motion->from.height)*eased)};
    motion->visual=box;
    // Keep the window solid through most of the journey, then gently disappear.
    double opacity=motion->minimizing?motion->opacity_from*(1-madway_animation_ease(fmax(0,(progress-.72)/.28))):
        motion->opacity_from+(1-motion->opacity_from)*madway_animation_ease(fmin(1,progress/.24));
    motion->opacity=opacity;
    place_image(motion,motion->image,box,(float)opacity);
    if (motion->incoming) place_image(motion,motion->incoming,box,(float)madway_animation_ease(fmax(0,(progress-.25)/.65)));
}

bool madway_motion_active(struct madway_output *output)
{
    struct madway_motion *motion=output->server->window_motion;
    return motion && motion->running && motion->view->output==output;
}

void madway_motion_frame(struct madway_output *output,double now)
{
    if (!madway_motion_active(output)) return;
    struct madway_server *server=output->server;
    struct madway_motion *motion=server->window_motion;
    double progress=(now-motion->started)/server->config.window_animation_ms;
    if (progress>=1 || server->locked || server->sleeping || (server->session && !server->session->active)) {
        madway_motion_finish(server);
        if (!server->shutting_down && !server->locked) madway_rebase_cursor(server);
        return;
    }
    motion->progress=progress;position(motion,progress);
    // The live surface is hidden behind its snapshot but still needs frame
    // callbacks to render the new configure at the monitor's native scale.
    struct timespec frame={.tv_sec=(time_t)(now/1000),.tv_nsec=(long)(fmod(now,1000)*1000000)};
    wlr_surface_send_frame_done(motion->view->toplevel->base->surface,&frame);
}

void madway_motion_commit(struct madway_view *view)
{
    struct madway_motion *motion=view->server->window_motion;
    if (!motion || motion->view!=view || !motion->running || motion->minimizing || motion->restoring || motion->incoming) return;
    struct wlr_box box=window_box(view,false);
    if (box.width!=motion->to.width || box.height!=motion->to.height) return;
    struct wlr_buffer *buffer=madway_window_snapshot(view);
    if (!buffer) return;
    motion->incoming=wlr_scene_buffer_create(motion->tree,buffer);wlr_buffer_drop(buffer);
    if (motion->incoming) position(motion,motion->progress);
}

void madway_motion_prepare(struct madway_view *view)
{
    struct madway_server *server=view->server;
    struct wlr_buffer *retained=NULL;
    struct wlr_box visual={0};double opacity=1;
    struct madway_motion *previous=server->window_motion;
    if (previous && previous->running && previous->view==view) {
        struct wlr_scene_buffer *image=previous->incoming && previous->progress>.55?previous->incoming:previous->image;
        retained=wlr_buffer_lock(image->buffer);visual=previous->visual;opacity=previous->opacity;
    }
    madway_transition_finish(server); // Also settles a previous window animation.
    if (!server->config.window_animate || !view->mapped || view->desktop_overlay || view->fullscreen ||
            !view->output || !view->output->output->enabled || view->workspace!=server->active_workspace ||
            server->locked || server->sleeping || server->shutting_down || (server->session && !server->session->active) ||
            (!view->scene_tree->node.enabled && !view->minimized)) {
        if (retained) wlr_buffer_unlock(retained);
        return;
    }
    struct wlr_buffer *buffer=retained?retained:madway_window_snapshot(view);
    if (!buffer) return;
    struct madway_motion *motion=calloc(1,sizeof(*motion));
    if (motion) {
        motion->view=view;motion->continuing=retained!=NULL;motion->opacity_from=opacity;
        motion->from=retained?visual:window_box(view,false);madway_view_output_box(view,&motion->bounds);
        motion->tree=wlr_scene_tree_create(server->desktop_tree);
        if (motion->tree) motion->image=wlr_scene_buffer_create(motion->tree,buffer);
    }
    if (retained) wlr_buffer_unlock(buffer);else wlr_buffer_drop(buffer);
    if (!motion) return;
    if (!motion->tree) {free(motion);return;}
    if (!motion->image) {wlr_scene_node_destroy(&motion->tree->node);free(motion);return;}
    server->window_motion=motion;
    wlr_scene_node_place_above(&motion->tree->node,&server->above_windows->node);
    wlr_scene_node_set_enabled(&motion->tree->node,false);
}

void madway_motion_start(struct madway_view *view,bool minimizing,bool restoring)
{
    struct madway_server *server=view->server;
    struct madway_motion *motion=server->window_motion;
    if (!motion || motion->view!=view) return;
    if (!minimizing && !view->scene_tree->node.enabled) {madway_motion_finish(server);return;}
    motion->minimizing=minimizing;motion->restoring=restoring;
    motion->to=minimizing?minimize_target(motion):window_box(view,true);
    if (restoring && !motion->continuing) {motion->from=minimize_target(motion);motion->opacity_from=0;}
    motion->reveal=view->scene_tree->node.enabled;
    motion->running=true;motion->started=madway_animation_now();position(motion,0);
    wlr_scene_node_set_enabled(&view->scene_tree->node,false);
    wlr_scene_node_set_enabled(&motion->tree->node,true);
    wlr_output_schedule_frame(view->output->output);
}
