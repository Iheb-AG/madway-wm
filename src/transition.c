#include "transition.h"
#include "main.h"
#include "preview.h"
#include "dock.h"
#include "input.h"
#include "motion.h"
#include "animation.h"
#include <math.h>
#include <stdlib.h>
#include <time.h>
#include <wlr/backend/session.h>
#include <wlr/types/wlr_buffer.h>

struct transition_output {
    struct wl_list link;
    struct madway_output *output;
    struct wlr_scene_buffer *old_image,*new_image;
    int x,y,width,height;
};
struct madway_transition {
    struct madway_server *server;
    struct wlr_scene_tree *tree;
    struct wl_list outputs;
    unsigned direction;
    double started;
    bool running;
};
void madway_transition_finish(struct madway_server *server)
{
    madway_motion_finish(server);
    struct madway_transition *transition=server->workspace_transition;
    if (!transition) return;
    server->workspace_transition=NULL;
    struct transition_output *entry,*temporary;
    wl_list_for_each_safe(entry,temporary,&transition->outputs,link) {wl_list_remove(&entry->link);free(entry);}
    wlr_scene_node_destroy(&transition->tree->node);free(transition);
}

void madway_transition_cancel_running(struct madway_server *server)
{
    if (server->workspace_transition && server->workspace_transition->running) madway_transition_finish(server);
}

// Crop both sliding images in buffer coordinates so they never cross outputs.
static void position(struct transition_output *entry,struct wlr_scene_buffer *image,int offset)
{
    int left=offset>0?offset:0,right=offset+entry->width;
    if (right>entry->width) right=entry->width;
    if (right<=left) {wlr_scene_node_set_enabled(&image->node,false);return;}
    double sx=(double)image->buffer->width/entry->width,sy=(double)image->buffer->height/entry->height;
    struct wlr_fbox source={(left-offset)*sx,0,(right-left)*sx,entry->height*sy};
    wlr_scene_buffer_set_source_box(image,&source);
    wlr_scene_buffer_set_dest_size(image,right-left,entry->height);
    wlr_scene_node_set_position(&image->node,entry->x+left,entry->y);
    wlr_scene_node_set_enabled(&image->node,true);
}

bool madway_transition_active(struct madway_output *output)
{
    struct madway_transition *transition=output->server->workspace_transition;
    if (!transition || !transition->running) return false;
    struct transition_output *entry;
    wl_list_for_each(entry,&transition->outputs,link) if (entry->output==output) return true;
    return false;
}

void madway_transition_frame(struct madway_output *output,double now)
{
    if (!madway_transition_active(output)) return;
    struct madway_server *server=output->server;
    struct madway_transition *transition=server->workspace_transition;
    double progress=(now-transition->started)/server->config.workspace_animation_ms;
    if (progress>=1 || server->locked || server->sleeping || (server->session && !server->session->active)) {
        madway_transition_finish(server);
        if (!server->shutting_down && !server->locked) madway_rebase_cursor(server);
        return;
    }
    double eased=madway_animation_ease(progress);
    struct transition_output *entry;
    wl_list_for_each(entry,&transition->outputs,link) {
        if (entry->output!=output) continue;
        int distance=(int)lround(eased*entry->width);
        int old=transition->direction? -distance:distance;
        int incoming=transition->direction?entry->width-distance:distance-entry->width;
        position(entry,entry->old_image,old);position(entry,entry->new_image,incoming);
    }
}

void madway_transition_prepare(struct madway_server *server,unsigned target)
{
    madway_transition_finish(server);
    if (!server->config.workspace_animate || server->locked || server->sleeping || server->shutting_down ||
            (server->session && !server->session->active)) return;
    struct madway_transition *transition=calloc(1,sizeof(*transition));
    if (!transition) return;
    transition->server=server;transition->direction=target>server->active_workspace;
    wl_list_init(&transition->outputs);
    transition->tree=wlr_scene_tree_create(server->desktop_tree);
    if (!transition->tree) {free(transition);return;}
    server->workspace_transition=transition;
    wlr_scene_node_place_above(&transition->tree->node,&server->above_windows->node);
    wlr_scene_node_set_enabled(&transition->tree->node,false);
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link) {
        if (!output->output->enabled) continue;
        struct transition_output *entry=calloc(1,sizeof(*entry));
        if (!entry) {madway_transition_finish(server);return;}
        entry->output=output;entry->x=output->layout_x;entry->y=output->layout_y;
        wlr_output_effective_resolution(output->output,&entry->width,&entry->height);
        wl_list_insert(transition->outputs.prev,&entry->link);
        struct wlr_buffer *buffer=madway_scene_snapshot(server,output);
        if (!buffer) {madway_transition_finish(server);return;}
        entry->old_image=wlr_scene_buffer_create(transition->tree,buffer);wlr_buffer_drop(buffer);
        if (!entry->old_image) {madway_transition_finish(server);return;}
        position(entry,entry->old_image,0);
    }
    if (wl_list_empty(&transition->outputs)) madway_transition_finish(server);
}

void madway_transition_start(struct madway_server *server)
{
    struct madway_transition *transition=server->workspace_transition;
    if (!transition) return;
    struct transition_output *entry;
    wl_list_for_each(entry,&transition->outputs,link) {
        struct wlr_buffer *buffer=madway_scene_snapshot(server,entry->output);
        if (!buffer) {madway_transition_finish(server);return;}
        entry->new_image=wlr_scene_buffer_create(transition->tree,buffer);wlr_buffer_drop(buffer);
        if (!entry->new_image) {madway_transition_finish(server);return;}
        wlr_scene_node_set_enabled(&entry->new_image->node,false);
    }
    transition->running=true;transition->started=madway_animation_now();
    wlr_scene_node_set_enabled(&transition->tree->node,true);
    wl_list_for_each(entry,&transition->outputs,link) wlr_output_schedule_frame(entry->output->output);
}
