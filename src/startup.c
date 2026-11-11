#include "startup.h"
#include "main.h"
#include "layer.h"
#include <string.h>
#include <glib.h>
#include <wlr/util/log.h>

/* Cover exists before the first backend frame. It is separate from desktop_tree
 * so offscreen desktop captures never contain it. Session lock remains above it. */
static int timeout(void *data)
{
    struct madway_server *server=data;
    wlr_log(WLR_ERROR,"Opening handoff timed out; revealing desktop");
    madway_startup_release(server);
    return 0;
}

bool madway_startup_init(struct madway_server *server)
{
    if (g_strcmp0(g_getenv("MADWAY_SESSION"),"1")!=0) return true;
    server->startup_tree=wlr_scene_tree_create(&server->scene->tree);
    if (!server->startup_tree) return false;
    server->startup_pending=true;
    server->startup_timeout=wl_event_loop_add_timer(wl_display_get_event_loop(server->display),timeout,server);
    if (!server->startup_timeout) return false;
    wl_event_source_timer_update(server->startup_timeout,10000);
    return true;
}

void madway_startup_arrange(struct madway_server *server)
{
    if (!server->startup_tree || !server->startup_pending) return;
    struct madway_output *output;
    const float black[4]={0,0,0,1};
    wl_list_for_each(output,&server->outputs,link) {
        if (!output->startup_cover) output->startup_cover=wlr_scene_rect_create(server->startup_tree,0,0,black);
        if (!output->startup_cover) {madway_startup_release(server);return;}
        int width,height;wlr_output_effective_resolution(output->output,&width,&height);
        wlr_scene_rect_set_size(output->startup_cover,width,height);
        wlr_scene_node_set_position(&output->startup_cover->node,output->layout_x,output->layout_y);
        wlr_scene_node_set_enabled(&output->startup_cover->node,output->output->enabled);
    }
}

void madway_startup_release(struct madway_server *server)
{
    if (!server->startup_pending) return;
    server->startup_pending=false;
    wlr_scene_node_set_enabled(&server->startup_tree->node,false);
    if (server->startup_timeout) {wl_event_source_remove(server->startup_timeout);server->startup_timeout=NULL;}
    wlr_log(WLR_INFO,"Opening cover handed off");
}

void madway_startup_finish(struct madway_server *server)
{
    if (server->startup_timeout) wl_event_source_remove(server->startup_timeout);
    server->startup_timeout=NULL;
}

void madway_startup_check(struct madway_server *server)
{
    if (!server->startup_pending || !server->startup_handoff_requested) return;
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link) {
        if (!output->output->enabled) continue;
        bool covered=false;struct madway_layer *layer;
        wl_list_for_each(layer,&server->layers,link)
            if (layer->mapped && layer->surface->output==output->output && !strcmp(layer->surface->namespace,"madway-session-exit")) {covered=true;break;}
        if (!covered) return;
    }
    madway_startup_release(server);
}

void madway_startup_request(struct madway_server *server)
{
    server->startup_handoff_requested=true;madway_startup_check(server);
}
