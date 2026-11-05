#include "transition.h"
#include "main.h"
#include "preview.h"
#include "dock.h"
#include "input.h"
#include "motion.h"
#include "animation.h"
#include "workspace.h"
#include <math.h>
#include <stdlib.h>
#include <time.h>
#include <wlr/backend/session.h>
#include <wlr/types/wlr_buffer.h>

struct madway_transition {
    struct madway_output *output;
    struct wlr_scene_tree *tree;
    struct wlr_scene_buffer *old_image,*new_image;
    int x,y,width,height;
    bool direction,running;
    double started;
};

void madway_transition_finish_output(struct madway_output *output)
{
    struct madway_transition *transition=output->transition;
    if(!transition)return;
    output->transition=NULL;
    struct madway_server *server=output->server;
    if(server->workspace_transition==transition) {
        server->workspace_transition=NULL;
        struct madway_output *other;
        wl_list_for_each(other,&server->outputs,link)
            if(other!=output && other->transition){server->workspace_transition=other->transition;break;}
    }
    wlr_scene_node_destroy(&transition->tree->node);free(transition);
}

void madway_transition_finish(struct madway_server *server)
{
    madway_motion_finish(server);
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link)madway_transition_finish_output(output);
}

void madway_transition_cancel_running(struct madway_server *server)
{
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link)
        if(output->transition && output->transition->running)madway_transition_finish_output(output);
}

// Crop both sliding images in buffer coordinates so they never cross outputs.
static void position(struct madway_transition *entry,struct wlr_scene_buffer *image,int offset)
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
    return output->transition && output->transition->running;
}

void madway_transition_frame(struct madway_output *output,double now)
{
    struct madway_transition *transition=output->transition;
    if(!transition || !transition->running)return;
    struct madway_server *server=output->server;
    double progress=(now-transition->started)/server->config.workspace_animation_ms;
    if(progress>=1 || !server->config.workspace_animate || server->locked || server->sleeping ||
        !output->output->enabled || (server->session && !server->session->active)) {
        madway_transition_finish_output(output);
        if(!server->shutting_down && !server->locked)madway_rebase_cursor(server);
        return;
    }
    int distance=(int)lround(madway_animation_ease(progress)*transition->width);
    position(transition,transition->old_image,transition->direction?-distance:distance);
    position(transition,transition->new_image,transition->direction?transition->width-distance:distance-transition->width);
}

void madway_transition_prepare(struct madway_server *server,unsigned target)
{
    struct madway_output *output=madway_workspace_output(server);
    if(!output)return;
    madway_motion_finish(server);madway_transition_finish_output(output);
    if(!server->config.workspace_animate || server->locked || server->sleeping || server->shutting_down ||
        (server->session && !server->session->active))return;
    struct madway_transition *transition=calloc(1,sizeof(*transition));
    if(!transition)return;
    transition->output=output;transition->direction=target>output->workspace;
    transition->tree=wlr_scene_tree_create(server->desktop_tree);
    if(!transition->tree){free(transition);return;}
    output->transition=transition;server->workspace_transition=transition;
    wlr_scene_node_place_above(&transition->tree->node,&server->above_windows->node);
    wlr_scene_node_set_enabled(&transition->tree->node,false);
    transition->x=output->layout_x;transition->y=output->layout_y;
    wlr_output_effective_resolution(output->output,&transition->width,&transition->height);
    struct wlr_buffer *buffer=madway_scene_snapshot(server,output);
    if(!buffer){madway_transition_finish_output(output);return;}
    transition->old_image=wlr_scene_buffer_create(transition->tree,buffer);wlr_buffer_drop(buffer);
    if(!transition->old_image){madway_transition_finish_output(output);return;}
    position(transition,transition->old_image,0);
}

void madway_transition_start(struct madway_server *server)
{
    struct madway_output *output=madway_workspace_output(server);
    struct madway_transition *transition=output?output->transition:NULL;
    if(!transition || transition->running)return;
    struct wlr_buffer *buffer=madway_scene_snapshot(server,output);
    if(!buffer){madway_transition_finish_output(output);return;}
    transition->new_image=wlr_scene_buffer_create(transition->tree,buffer);wlr_buffer_drop(buffer);
    if(!transition->new_image){madway_transition_finish_output(output);return;}
    wlr_scene_node_set_enabled(&transition->new_image->node,false);
    transition->running=true;transition->started=madway_animation_now();
    wlr_scene_node_set_enabled(&transition->tree->node,true);
    wlr_output_schedule_frame(output->output);
}
