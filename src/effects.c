#include "effects.h"
#include "main.h"
#include "layer.h"
#include "preview.h"
#include "animation.h"
#include "session.h"
#include "closing.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <wlr/types/wlr_buffer.h>
#include <wlr/backend/session.h>

struct closing_effect {
    struct wl_list link;
    struct madway_output *output;
    struct wlr_scene_buffer *image;
    struct wlr_scene_tree *tree;
    int x,y;
    double started;
    float opacity;
};

static bool allowed(struct madway_server *server)
{
    return server->config.effects_animate && !server->locked && !server->sleeping &&
        !server->shutting_down && (!server->session || server->session->active);
}

static bool overlay(struct madway_layer *layer)
{
    return !strcmp(layer->surface->namespace,"wofi") || !strcmp(layer->surface->namespace,"madway-launcher") || !strcmp(layer->surface->namespace,"madway-osd");
}

static void opacity(struct wlr_scene_node *node,float value)
{
    if(node->type==WLR_SCENE_NODE_BUFFER)wlr_scene_buffer_set_opacity(wlr_scene_buffer_from_node(node),value);
    else if(node->type==WLR_SCENE_NODE_TREE) {
        struct wlr_scene_node *child;
        wl_list_for_each(child,&wlr_scene_tree_from_node(node)->children,link)opacity(child,value);
    }
}

static void settle(struct madway_layer *layer)
{
    layer->effect_active=false;layer->effect_opacity=1;
    opacity(&layer->scene_layer->tree->node,1);
    wlr_scene_node_set_position(&layer->tree->node,0,0);
}

void madway_effects_init(struct madway_server *server)
{
    wl_list_init(&server->closing_effects);server->effects_initialized=true;
}

void madway_effects_map(struct madway_layer *layer)
{
    settle(layer);
    // Hardware feedback must be visible on its first frame, not after a fade-in.
    if(!strcmp(layer->surface->namespace,"madway-osd"))return;
    if(!allowed(layer->server) || (!overlay(layer) && strcmp(layer->surface->namespace,"wallpaper")))return;
    layer->effect_active=true;layer->effect_started=madway_animation_now();layer->effect_opacity=0;
    opacity(&layer->scene_layer->tree->node,0);
    if(overlay(layer))wlr_scene_node_set_position(&layer->tree->node,0,8);
    wlr_output_schedule_frame(layer->surface->output);
}

void madway_effects_commit(struct madway_layer *layer)
{
    if(layer->effect_active)opacity(&layer->scene_layer->tree->node,layer->effect_opacity);
    if(!layer->mapped || !allowed(layer->server) || !overlay(layer))return;
    struct wlr_buffer *buffer=madway_layer_snapshot(layer);
    if(!buffer)return;
    if(layer->effect_cache)wlr_buffer_drop(layer->effect_cache);
    layer->effect_cache=buffer;
    layer->effect_width=layer->surface->surface->current.width;
    layer->effect_height=layer->surface->surface->current.height;
}

void madway_effects_drop(struct madway_layer *layer)
{
    if(layer->effect_cache)wlr_buffer_drop(layer->effect_cache);
    layer->effect_cache=NULL;
    settle(layer);
}

static void remove_closing(struct closing_effect *effect)
{
    wl_list_remove(&effect->link);wlr_scene_node_destroy(&effect->tree->node);free(effect);
}

void madway_effects_unmap(struct madway_layer *layer)
{
    struct madway_server *server=layer->server;
    if(layer->effect_cache && allowed(server) && layer->surface->output->enabled) {
        struct madway_output *output;
        wl_list_for_each(output,&server->outputs,link)if(output->output==layer->surface->output) {
            struct closing_effect *effect=calloc(1,sizeof(*effect));
            if(!effect)break;
            effect->tree=wlr_scene_tree_create(server->layer_trees[layer->surface->current.layer]);
            effect->image=effect->tree?wlr_scene_buffer_create(effect->tree,layer->effect_cache):NULL;
            if(!effect->image){if(effect->tree)wlr_scene_node_destroy(&effect->tree->node);free(effect);break;}
            struct wlr_scene_node *node=&layer->scene_layer->tree->node;
            while(node){effect->x+=node->x;effect->y+=node->y;node=node->parent?&node->parent->node:NULL;}
            effect->output=output;effect->started=madway_animation_now();effect->opacity=layer->effect_opacity;
            wlr_scene_buffer_set_dest_size(effect->image,layer->effect_width,layer->effect_height);
            wlr_scene_buffer_set_opacity(effect->image,effect->opacity);
            wlr_scene_node_set_position(&effect->image->node,effect->x,effect->y);
            wl_list_insert(server->closing_effects.prev,&effect->link);wlr_output_schedule_frame(output->output);
            break;
        }
    }
    madway_effects_drop(layer);
}

bool madway_effects_active(struct madway_output *output)
{
    if(!output->server->effects_initialized)return false;
    struct madway_layer *layer;
    wl_list_for_each(layer,&output->server->layers,link)
        if(layer->mapped && layer->surface->output==output->output && layer->effect_active)return true;
    struct closing_effect *effect;
    wl_list_for_each(effect,&output->server->closing_effects,link)if(effect->output==output)return true;
    return false;
}

void madway_effects_frame(struct madway_output *output,double now)
{
    struct madway_server *server=output->server;
    if(!server->effects_initialized)return;
    bool publish=false;
    struct madway_layer *layer;
    wl_list_for_each(layer,&server->layers,link) {
        if(!layer->mapped || layer->surface->output!=output->output || !layer->effect_active)continue;
        bool background=!strcmp(layer->surface->namespace,"wallpaper");
        double duration=background?server->config.wallpaper_fade_ms:server->config.launcher_animation_ms;
        double progress=(now-layer->effect_started)/duration;
        if(progress>=1 || !allowed(server)) {
            settle(layer);if(background)publish=true;
        } else {
            double eased=madway_animation_ease(progress);layer->effect_opacity=(float)eased;
            opacity(&layer->scene_layer->tree->node,(float)eased);
            if(!background)wlr_scene_node_set_position(&layer->tree->node,0,(int)lround(8*(1-eased)));
        }
    }
    struct closing_effect *effect,*temporary;
    wl_list_for_each_safe(effect,temporary,&server->closing_effects,link) {
        if(effect->output!=output)continue;
        double progress=(now-effect->started)/server->config.launcher_animation_ms;
        if(progress>=1 || !allowed(server)){remove_closing(effect);continue;}
        double eased=madway_animation_ease(progress);
        wlr_scene_buffer_set_opacity(effect->image,effect->opacity*(float)(1-eased));
        wlr_scene_node_set_position(&effect->image->node,effect->x,effect->y+(int)lround(8*eased));
    }
    if(publish)madway_session_publish_state(server);
}

void madway_effects_cancel(struct madway_server *server)
{
    madway_close_cancel(server,NULL);
    if(!server->effects_initialized)return;
    struct madway_layer *layer;
    wl_list_for_each(layer,&server->layers,link)madway_effects_drop(layer);
    struct closing_effect *effect,*temporary;
    wl_list_for_each_safe(effect,temporary,&server->closing_effects,link)remove_closing(effect);
}

void madway_effects_output_destroy(struct madway_output *output)
{
    if(!output->server->effects_initialized)return;
    struct closing_effect *effect,*temporary;
    wl_list_for_each_safe(effect,temporary,&output->server->closing_effects,link)
        if(effect->output==output)remove_closing(effect);
}
