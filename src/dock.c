#include "dock.h"
#include "main.h"
#include "layer.h"
#include "view.h"
#include "workspace.h"
#include "input.h"
#include "animation.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

struct madway_dock {
    struct madway_layer *layer;
    struct wl_event_source *timer;
    double position, from, target, duration, started;
    uint64_t left_at;
    bool moving, revealed;
};

static uint64_t now_ms(void)
{
    struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);
    return (uint64_t)now.tv_sec*1000+(uint64_t)now.tv_nsec/1000000;
}

/* Share one motion curve across the desktop. */
double madway_dock_ease(double progress)
{
    return madway_animation_ease(progress);
}

bool madway_dock_autohidden(struct madway_server *server,struct wlr_output *output)
{
    struct madway_view *view;
    wl_list_for_each(view,&server->views,link)
        if (view->output && view->output->output==output && madway_view_visible(view) &&
                (view->fullscreen || (server->config.dock_autohide && view->maximized))) return true;
    return false;
}

static bool fullscreen(struct madway_layer *layer)
{
    struct madway_view *view;
    wl_list_for_each(view,&layer->server->views,link)
        if (view->output && view->output->output==layer->surface->output &&
                madway_view_visible(view) && view->fullscreen) return true;
    return false;
}

static bool bounds(struct madway_layer *layer,struct wlr_box *output,struct wlr_box *dock)
{
    struct wlr_output *screen=layer->surface->output;
    if (!screen || !screen->enabled) return false;
    wlr_output_layout_get_box(layer->server->output_layout,screen,output);
    *dock=(struct wlr_box){layer->scene_layer->tree->node.x,layer->scene_layer->tree->node.y,
        layer->surface->surface->current.width,layer->surface->surface->current.height};
    return dock->width>0 && dock->height>0 && output->width>0 && output->height>0;
}

static uint32_t edge(struct madway_layer *layer)
{
    uint32_t anchor=layer->surface->current.anchor;
    if ((anchor&ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM) && !(anchor&ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP)) return ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM;
    if ((anchor&ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP) && !(anchor&ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM)) return ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP;
    if (anchor&ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT) return ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT;
    return ZWLR_LAYER_SURFACE_V1_ANCHOR_RIGHT;
}

static void draw(struct madway_dock *dock)
{
    struct madway_layer *layer=dock->layer;
    struct wlr_box output,area;
    bool visible=layer->mapped && !layer->server->locked && !layer->server->sleeping &&
        bounds(layer,&output,&area) && !fullscreen(layer);
    if (!visible || dock->position>=1) {
        wlr_scene_node_set_enabled(&layer->tree->node,false);
        return;
    }
    int dx=0,dy=0;
    switch (edge(layer)) {
    case ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM:dy=(int)lround((output.y+output.height-area.y+2)*dock->position);break;
    case ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP:dy=-(int)lround((area.y+area.height-output.y+2)*dock->position);break;
    case ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT:dx=-(int)lround((area.x+area.width-output.x+2)*dock->position);break;
    default:dx=(int)lround((output.x+output.width-area.x+2)*dock->position);break;
    }
    wlr_scene_node_set_position(&layer->tree->node,dx,dy);
    // Never slide onto an adjacent output, even in vertical monitor layouts.
    struct wlr_box clip={output.x-area.x-dx,output.y-area.y-dy,output.width,output.height};
    wlr_scene_subsurface_tree_set_clip(&layer->scene_layer->tree->node,(dx||dy)?&clip:NULL);
    wlr_scene_node_set_enabled(&layer->tree->node,true);
}

static void advance(struct madway_dock *dock)
{
    if (!dock->moving) return;
    double progress=(madway_animation_now()-dock->started)/dock->duration;
    dock->position=dock->from+(dock->target-dock->from)*madway_animation_ease(progress);
    if (progress>=1) {dock->position=dock->target;dock->moving=false;}
}

static void target(struct madway_dock *dock,double value,bool immediate)
{
    advance(dock);
    if (immediate) {dock->position=value;dock->target=value;dock->moving=false;return;}
    if (dock->target==value) return;
    dock->from=dock->position;dock->target=value;dock->started=madway_animation_now();
    dock->duration=fmax(40,dock->layer->server->config.dock_animation_ms*fabs(value-dock->position));
    dock->moving=true;
}

static bool pointer_inside(struct madway_dock *dock,bool hidden)
{
    struct madway_layer *layer=dock->layer;
    struct wlr_box output,area;
    if (!bounds(layer,&output,&area)) return false;
    double x=layer->server->cursor->x,y=layer->server->cursor->y;
    if (!wlr_box_contains_point(&output,x,y)) return false;
    if (!hidden && x>=area.x-4 && x<area.x+area.width+4 && y>=area.y-4 && y<area.y+area.height+4) return true;
    switch (edge(layer)) {
    case ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM:return y>=output.y+output.height-3 && x>=area.x && x<area.x+area.width;
    case ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP:return y<output.y+3 && x>=area.x && x<area.x+area.width;
    case ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT:return x<output.x+3 && y>=area.y && y<area.y+area.height;
    default:return x>=output.x+output.width-3 && y>=area.y && y<area.y+area.height;
    }
}

static int tick(void *data)
{
    struct madway_dock *dock=data;
    madway_dock_update(dock->layer);
    if (!dock->layer->server->locked && !dock->layer->server->interactive_view)
        madway_rebase_cursor(dock->layer->server);
    return 0;
}

void madway_dock_update(struct madway_layer *layer)
{
    if (strcmp(layer->surface->namespace,"madway-dock")!=0) return;
    if (!layer->mapped && !layer->dock) return;
    if (!layer->dock) {
        layer->dock=calloc(1,sizeof(*layer->dock));
        if (!layer->dock) return;
        layer->dock->layer=layer;
        layer->dock->timer=wl_event_loop_add_timer(wl_display_get_event_loop(layer->server->display),tick,layer->dock);
        if (!layer->dock->timer) {free(layer->dock);layer->dock=NULL;return;}
    }
    struct madway_dock *dock=layer->dock;
    bool unavailable=layer->server->locked || layer->server->sleeping || !layer->mapped ||
        !layer->surface->output || !layer->surface->output->enabled || fullscreen(layer);
    bool hide=unavailable || madway_dock_autohidden(layer->server,layer->surface->output);
    if (!hide || unavailable) {dock->revealed=false;dock->left_at=0;}
    else {
        bool inside=pointer_inside(dock,!dock->revealed);
        struct wlr_surface *focused=layer->server->seat->pointer_state.focused_surface;
        if (dock->revealed && focused && wlr_seat_pointer_has_grab(layer->server->seat) &&
                wl_resource_get_client(focused->resource)==wl_resource_get_client(layer->surface->surface->resource)) inside=true;
        if (inside) {dock->revealed=true;dock->left_at=0;}
        else if (dock->revealed) {
            if (!dock->left_at) dock->left_at=now_ms();
            if (now_ms()-dock->left_at>=350) {dock->revealed=false;dock->left_at=0;}
        }
    }
    target(dock,hide && !dock->revealed?1:0,unavailable || !layer->server->config.dock_animate);
    draw(dock);
    // The timer is only for the pointer-leave delay; motion uses output frames.
    wl_event_source_timer_update(dock->timer,dock->left_at?40:0);
    if (dock->moving) wlr_output_schedule_frame(layer->surface->output);
}

void madway_dock_frame(struct madway_output *output)
{
    struct madway_layer *layer;
    wl_list_for_each(layer,&output->server->layers,link) {
        if (!layer->dock || layer->surface->output!=output->output) continue;
        if (layer->dock->moving) {advance(layer->dock);draw(layer->dock);}
    }
}

bool madway_dock_active(struct madway_output *output)
{
    struct madway_layer *layer;
    wl_list_for_each(layer,&output->server->layers,link)
        if (layer->dock && layer->surface->output==output->output && layer->dock->moving) return true;
    return false;
}

void madway_dock_pointer(struct madway_server *server)
{
    struct madway_layer *layer;
    wl_list_for_each(layer,&server->layers,link)
        if (layer->dock) madway_dock_update(layer);
}

void madway_dock_finish(struct madway_layer *layer)
{
    if (!layer->dock) return;
    wl_event_source_remove(layer->dock->timer);
    free(layer->dock);layer->dock=NULL;
}
