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
#include "motion_profile.h"
#include <math.h>
#include <glib.h>
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
    double started,progress,duration_ms;
    double opacity_from,opacity;
    bool running,reveal,minimizing,restoring,continuing;
    bool opening,fade_only,dissolve,incoming_ready;
    enum madway_motion_curve curve;
};

enum motion_kind {MOTION_NORMAL,MOTION_OPENING,MOTION_MAXIMIZE};

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

static struct wlr_buffer *snapshot(struct madway_view *view,uint64_t budget)
{
    struct wlr_box box=window_box(view,false);
    double scale=view->output->output->scale;
    double bytes=ceil(box.width*scale)*ceil(box.height*scale)*4;
    if(box.width<=0 || box.height<=0 || !isfinite(bytes) || bytes>budget)return NULL;
    return madway_window_snapshot_alpha(view);
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
    struct wlr_box box=madway_motion_interpolate(motion->from,motion->to,motion->curve,progress);
    if(motion->dissolve) {
        double blend=CLAMP(madway_motion_curve_value(motion->curve,progress),0,1);
        motion->visual=blend>.5?motion->to:motion->from;
        motion->opacity=blend>.5?blend:motion->opacity_from*(1-blend);
        place_image(motion,motion->image,motion->from,(float)(motion->opacity_from*(1-blend)));
        if(motion->incoming)place_image(motion,motion->incoming,motion->to,(float)blend);
        return;
    }
    motion->visual=box;
    // Keep the window solid through most of the journey, then gently disappear.
    enum madway_motion_curve fade_curve=motion->curve==MADWAY_CURVE_SPRING?MADWAY_CURVE_RESPONSIVE:motion->curve;
    double fade=motion->opening?CLAMP(madway_motion_curve_value(fade_curve,fmin(1,progress/(motion->fade_only?1:.65))),0,1):
        madway_animation_ease(fmin(1,progress/.24));
    double opacity=motion->minimizing?motion->opacity_from*(1-madway_animation_ease(fmax(0,(progress-.72)/.28))):
        motion->opacity_from+(1-motion->opacity_from)*fade;
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
    double progress=(now-motion->started)/motion->duration_ms;
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
    if (!motion || motion->view!=view || !motion->running || motion->minimizing || motion->restoring || motion->incoming_ready) return;
    struct wlr_box box=window_box(view,false);
    if (box.width!=motion->to.width || box.height!=motion->to.height) return;
    uint64_t used=(uint64_t)motion->image->buffer->width*motion->image->buffer->height*4;
    uint64_t budget=64*1024*1024;
    if(!motion->opening)budget=used<budget?budget-used:0;
    struct wlr_buffer *buffer=snapshot(view,budget);
    if (!buffer) return;
    if(motion->opening) {
        wlr_scene_buffer_set_buffer(motion->image,buffer);motion->incoming_ready=true;
    } else if(motion->incoming) {
        wlr_scene_buffer_set_buffer(motion->incoming,buffer);motion->incoming_ready=true;
    } else {
        motion->incoming=wlr_scene_buffer_create(motion->tree,buffer);motion->incoming_ready=motion->incoming!=NULL;
    }
    wlr_buffer_drop(buffer);position(motion,motion->progress);
}

static void prepare(struct madway_view *view,enum motion_kind kind)
{
    struct madway_server *server=view->server;
    struct wlr_buffer *retained=NULL;
    struct wlr_box visual={0};double opacity=1;
    struct madway_motion *previous=server->window_motion;
    if (previous && previous->running && previous->view==view) {
        struct wlr_scene_buffer *image=previous->incoming && previous->progress>.55?previous->incoming:previous->image;
        retained=wlr_buffer_lock(image->buffer);visual=previous->visual;opacity=previous->opacity;
    }
    madway_motion_finish(server);
    if(view->output)madway_transition_finish_output(view->output);
    bool enabled=kind==MOTION_OPENING?server->config.open_animate:
        server->config.window_animate && (kind!=MOTION_MAXIMIZE || server->config.maximize_style!=MADWAY_MAXIMIZE_NONE);
    if (!enabled || !view->mapped || view->desktop_overlay || (view->fullscreen && kind!=MOTION_OPENING) ||
            !view->output || !view->output->output->enabled || view->workspace!=view->output->workspace ||
            server->locked || server->sleeping || server->shutting_down || (server->session && !server->session->active) ||
            (!view->scene_tree->node.enabled && !view->minimized)) {
        if (retained) wlr_buffer_unlock(retained);
        return;
    }
    struct wlr_buffer *buffer=retained?retained:snapshot(view,64*1024*1024);
    if (!buffer) return;
    struct madway_motion *motion=calloc(1,sizeof(*motion));
    if (motion) {
        motion->duration_ms=server->config.window_animation_ms;
        motion->curve=MADWAY_CURVE_GENTLE;motion->opening=kind==MOTION_OPENING;
        if(kind==MOTION_OPENING){motion->duration_ms=server->config.open_animation_ms;motion->curve=server->config.open_curve;}
        if(kind==MOTION_MAXIMIZE){motion->duration_ms=server->config.maximize_animation_ms;motion->curve=server->config.maximize_curve;
            motion->dissolve=server->config.maximize_style==MADWAY_MAXIMIZE_DISSOLVE;}
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

void madway_motion_prepare(struct madway_view *view){prepare(view,MOTION_NORMAL);}
void madway_motion_prepare_maximize(struct madway_view *view){prepare(view,MOTION_MAXIMIZE);}

void madway_motion_start(struct madway_view *view,bool minimizing,bool restoring)
{
    struct madway_server *server=view->server;
    struct madway_motion *motion=server->window_motion;
    if (!motion || motion->view!=view) return;
    if (!minimizing && !view->scene_tree->node.enabled) {madway_motion_finish(server);return;}
    motion->minimizing=minimizing;motion->restoring=restoring;
    motion->to=minimizing?minimize_target(motion):window_box(view,true);
    if(motion->dissolve) {
        motion->incoming=wlr_scene_buffer_create(motion->tree,motion->image->buffer);
        if(!motion->incoming){madway_motion_finish(server);return;}
    }
    if (restoring && !motion->continuing) {motion->from=minimize_target(motion);motion->opacity_from=0;}
    motion->reveal=view->scene_tree->node.enabled;
    motion->running=true;motion->started=madway_animation_now();position(motion,0);
    wlr_scene_node_set_enabled(&view->scene_tree->node,false);
    wlr_scene_node_set_enabled(&motion->tree->node,true);
    wlr_output_schedule_frame(view->output->output);
}

void madway_motion_open(struct madway_view *view)
{
    // New toplevels may come from the launcher, terminal, dock, or another app.
    // There is no app-id filter; the first valid client buffer starts the reveal.
    if(!view->server->config.open_animate || view->desktop_overlay)return;
    struct madway_config *config=&view->server->config;
    struct wlr_box target=window_box(view,true);
    struct wlr_box origin=madway_motion_open_geometry(target,view->fullscreen?MADWAY_OPEN_FADE:config->open_style,
        config->open_scale,config->open_distance);
    if(!config->open_fade && wlr_box_equal(&origin,&target))return;
    prepare(view,MOTION_OPENING);
    struct madway_motion *motion=view->server->window_motion;
    if (!motion || motion->view!=view) return;
    motion->from=origin;motion->fade_only=wlr_box_equal(&origin,&target);
    motion->opacity_from=config->open_fade?0:1;
    madway_motion_start(view,false,false);
}

void madway_motion_activate(struct madway_view *view)
{
    if (!view->server->config.effects_animate) return;
    madway_motion_prepare(view);
    struct madway_motion *motion=view->server->window_motion;
    if (!motion || motion->view!=view) return;
    int dx=(int)lround(motion->from.width*.008),dy=(int)lround(motion->from.height*.008);
    motion->from.x+=dx;motion->from.y+=dy+2;
    motion->from.width-=2*dx;motion->from.height-=2*dy;
    motion->duration_ms=200;motion->opacity_from=.92;
    madway_motion_start(view,false,false);
    if (view->server->window_motion) view->server->window_motion->restoring=true;
}
