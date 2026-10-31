#include "lock.h"
#include "preview.h"
#include "transition.h"
#include "main.h"
#include "input.h"
#include "workspace.h"
#include "view.h"
#include <stdlib.h>
#include <unistd.h>
#include <poll.h>
#include <sys/pidfd.h>
#include <cairo.h>
#include <drm_fourcc.h>
#include <pango/pangocairo.h>
#include <wlr/interfaces/wlr_buffer.h>
#include <wlr/types/wlr_damage_ring.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_session_lock_v1.h>
#include <wlr/util/log.h>

struct lock_owner;
struct lock_message {struct wlr_buffer base;cairo_surface_t *image;};
static void message_destroy(struct wlr_buffer *base)
{
    struct lock_message *message=wl_container_of(base,message,base);
    cairo_surface_destroy(message->image);free(message);
}
static bool message_read(struct wlr_buffer *base,uint32_t flags,void **data,uint32_t *format,size_t *stride)
{
    if(flags&WLR_BUFFER_DATA_PTR_ACCESS_WRITE)return false;
    struct lock_message *message=wl_container_of(base,message,base);
    *data=cairo_image_surface_get_data(message->image);*format=DRM_FORMAT_ARGB8888;
    *stride=(size_t)cairo_image_surface_get_stride(message->image);return true;
}
static void message_end(struct wlr_buffer *base){(void)base;}
static const struct wlr_buffer_impl message_impl={.destroy=message_destroy,.begin_data_ptr_access=message_read,.end_data_ptr_access=message_end};
static struct wlr_buffer *create_message(void)
{
    struct lock_message *message=calloc(1,sizeof(*message));if(!message)return NULL;
    message->image=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,560,80);
    if(cairo_surface_status(message->image)!=CAIRO_STATUS_SUCCESS){cairo_surface_destroy(message->image);free(message);return NULL;}
    cairo_t *cr=cairo_create(message->image);cairo_set_source_rgb(cr,.8,.8,.8);
    PangoLayout *layout=pango_cairo_create_layout(cr);
    PangoFontDescription *font=pango_font_description_from_string("sans");pango_font_description_set_absolute_size(font,13*PANGO_SCALE);
    pango_layout_set_font_description(layout,font);pango_layout_set_width(layout,560*PANGO_SCALE);pango_layout_set_alignment(layout,PANGO_ALIGN_CENTER);
    pango_layout_set_text(layout,"Session locked\nLocker is starting or recovering.\nUse your lock shortcut to retry; Ctrl+Alt+F3 opens a console.",-1);
    pango_cairo_show_layout(cr,layout);pango_font_description_free(font);g_object_unref(layout);cairo_destroy(cr);cairo_surface_flush(message->image);
    wlr_buffer_init(&message->base,&message_impl,560,80);return &message->base;
}
struct lock_surface {
    struct lock_owner *owner;
    struct wlr_session_lock_surface_v1 *surface;
    struct wlr_scene_tree *tree;
    struct wl_list link;
    struct wl_listener map,unmap,destroy;
};
struct lock_owner {
    struct madway_lock *manager;
    struct wlr_session_lock_v1 *lock;
    struct wlr_scene_tree *tree;
    struct wl_list surfaces;
    struct wl_listener new_surface,unlock,destroy;
    struct wl_event_source *authorize_timer;
    pid_t pid;
    bool authorized,acknowledged;
};
struct madway_lock {
    struct madway_server *server;
    struct wlr_session_lock_manager_v1 *protocol;
    struct wlr_scene_tree *tree;
    struct wl_listener new_lock;
    struct lock_owner *owner;
    pid_t expected_pid;
    int expected_fd;
    bool ready;
    unsigned request_serial;
    struct wlr_buffer *message;
};
struct madway_lock_output {
    struct madway_output *output;
    struct wlr_scene_rect *black;
    struct wlr_scene_buffer *message;
    struct wl_listener precommit,present;
    bool enabled,submitted,presented;
    uint32_t sequence;
};

static void check_ready(struct madway_lock *manager)
{
    struct madway_server *server=manager->server;
    bool ready=server->locked;
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link)
        if(output->output->enabled && (output->lock_data==NULL || !output->lock_data->presented))ready=false;
    bool changed=manager->ready!=ready;manager->ready=ready;
    struct lock_owner *owner=manager->owner;
    if(ready && owner && owner->authorized && !owner->acknowledged) {
        owner->acknowledged=true;
        wlr_session_lock_v1_send_locked(owner->lock);
        wlr_log(WLR_INFO,"Session lock confirmed after safe presentation on every enabled output");
        changed=true;
    }
    if(changed)madway_session_publish_state(server);
}

bool madway_lock_ready(struct madway_server *server)
{
    return server->screen_lock && server->screen_lock->ready;
}
unsigned madway_lock_request_serial(struct madway_server *server)
{
    return server->screen_lock?server->screen_lock->request_serial:0;
}
void madway_lock_request(struct madway_server *server,unsigned serial)
{
    if(!server->screen_lock)return;
    server->screen_lock->request_serial=serial;madway_lock_blank(server);madway_session_publish_state(server);
}
pid_t madway_lock_client_pid(struct madway_server *server)
{
    struct lock_owner *owner=server->screen_lock?server->screen_lock->owner:NULL;
    return owner && owner->authorized && owner->acknowledged?owner->pid:0;
}

void madway_lock_focus(struct madway_server *server,struct wlr_surface *surface)
{
    if(!server->locked || !server->screen_lock || !server->seat)return;
    if(wlr_seat_keyboard_has_grab(server->seat))wlr_seat_keyboard_end_grab(server->seat);
    struct lock_owner *owner=server->screen_lock->owner;
    struct wlr_surface *target=NULL;
    if(owner && owner->authorized) {
        struct lock_surface *entry;
        wl_list_for_each(entry,&owner->surfaces,link)
            if(entry->surface->surface->mapped && entry->surface->output->enabled) {
                if(!target)target=entry->surface->surface;
                if(entry->surface->surface==surface ||
                    (surface==NULL && entry->surface->surface==server->seat->keyboard_state.focused_surface)) {
                    target=entry->surface->surface;break;
                }
            }
    }
    if(!target){wlr_seat_keyboard_notify_clear_focus(server->seat);return;}
    if(server->seat->keyboard_state.focused_surface==target)return;
    struct wlr_keyboard *keyboard=wlr_seat_get_keyboard(server->seat);
    struct wlr_keyboard_modifiers modifiers={0};
    /* Never carry keys held before locking into the password input. */
    wlr_seat_keyboard_notify_enter(server->seat,target,NULL,0,keyboard?&keyboard->modifiers:&modifiers);
}

struct wlr_surface *madway_lock_at(struct madway_server *server,double x,double y,double *sx,double *sy)
{
    struct madway_lock *manager=server->screen_lock;
    if(!manager || !manager->owner || !manager->owner->authorized)return NULL;
    struct wlr_scene_node *node=wlr_scene_node_at(&manager->owner->tree->node,x,y,sx,sy);
    if(!node || node->type!=WLR_SCENE_NODE_BUFFER)return NULL;
    struct wlr_scene_surface *scene=wlr_scene_surface_try_from_buffer(wlr_scene_buffer_from_node(node));
    return scene?scene->surface:NULL;
}

void madway_lock_blank(struct madway_server *server)
{
    struct madway_lock *manager=server->screen_lock;
    if(!manager || server->locked)return;
    server->locked=true;
    madway_transition_finish(server);
    madway_preview_clear(server);
    if(server->interactive_view && !server->interactive_forward_button)server->consumed_button=server->interactive_button;
    madway_end_interactive(server);madway_cancel_pointer_grab(server);
    madway_switcher_finish(server,false);
    server->keyboard_layer=NULL;
    wlr_seat_keyboard_notify_clear_focus(server->seat);
    if(wlr_seat_keyboard_has_grab(server->seat))wlr_seat_keyboard_end_grab(server->seat);
    server->cursor_shape=NULL;
    wlr_cursor_set_xcursor(server->cursor,server->cursor_manager,"left_ptr");
    wlr_scene_node_set_enabled(&server->desktop_tree->node,false);
    wlr_scene_node_set_enabled(&manager->tree->node,true);
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link) {
        if(output->lock_data){output->lock_data->submitted=false;output->lock_data->presented=false;}
        wlr_damage_ring_add_whole(&output->scene_output->damage_ring);
        if(output->output->enabled)wlr_output_schedule_frame(output->output);
    }
    madway_lock_arrange(server);madway_session_publish_state(server);
}

static void destroy_surface(struct lock_surface *entry)
{
    wl_list_remove(&entry->map.link);wl_list_remove(&entry->unmap.link);wl_list_remove(&entry->destroy.link);
    wl_list_remove(&entry->link);wlr_scene_node_destroy(&entry->tree->node);free(entry);
}
static void surface_destroyed(struct wl_listener *listener,void *data)
{
    (void)data;
    struct lock_surface *entry=wl_container_of(listener,entry,destroy);
    struct madway_server *server=entry->owner->manager->server;
    destroy_surface(entry);madway_lock_focus(server,NULL);
}
static void surface_mapped(struct wl_listener *listener,void *data)
{
    (void)data;
    struct lock_surface *entry=wl_container_of(listener,entry,map);
    wlr_scene_node_set_enabled(&entry->tree->node,true);
    madway_lock_focus(entry->owner->manager->server,NULL);
}
static void surface_unmapped(struct wl_listener *listener,void *data)
{
    (void)data;
    struct lock_surface *entry=wl_container_of(listener,entry,unmap);
    wlr_scene_node_set_enabled(&entry->tree->node,false);
    madway_lock_focus(entry->owner->manager->server,NULL);
}
static void configure_surface(struct lock_surface *entry)
{
    struct madway_server *server=entry->owner->manager->server;
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link)if(output->output==entry->surface->output) {
        int width,height;wlr_output_effective_resolution(output->output,&width,&height);
        wlr_scene_node_set_position(&entry->tree->node,output->layout_x,output->layout_y);
        if(!entry->surface->configured || entry->surface->pending.width!=(uint32_t)width || entry->surface->pending.height!=(uint32_t)height)
            wlr_session_lock_surface_v1_configure(entry->surface,width>0?width:1,height>0?height:1);
        break;
    }
}
static void new_surface(struct wl_listener *listener,void *data)
{
    struct lock_owner *owner=wl_container_of(listener,owner,new_surface);
    struct wlr_session_lock_surface_v1 *surface=data;
    struct lock_surface *entry=calloc(1,sizeof(*entry));
    if(!entry){wl_client_post_no_memory(wl_resource_get_client(surface->resource));return;}
    entry->owner=owner;entry->surface=surface;entry->tree=wlr_scene_tree_create(owner->tree);
    if(!entry->tree || !wlr_scene_subsurface_tree_create(entry->tree,surface->surface)) {
        if(entry->tree)wlr_scene_node_destroy(&entry->tree->node);
        free(entry);wl_client_post_no_memory(wl_resource_get_client(surface->resource));return;
    }
    wlr_scene_node_set_enabled(&entry->tree->node,false);
    entry->map.notify=surface_mapped;wl_signal_add(&surface->surface->events.map,&entry->map);
    entry->unmap.notify=surface_unmapped;wl_signal_add(&surface->surface->events.unmap,&entry->unmap);
    entry->destroy.notify=surface_destroyed;wl_signal_add(&surface->events.destroy,&entry->destroy);
    wl_list_insert(owner->surfaces.prev,&entry->link);configure_surface(entry);
}
static void owner_destroyed(struct wl_listener *listener,void *data)
{
    (void)data;
    struct lock_owner *owner=wl_container_of(listener,owner,destroy);
    struct madway_lock *manager=owner->manager;
    if(manager->expected_pid==owner->pid) {
        manager->expected_pid=0;
        if(manager->expected_fd>=0){close(manager->expected_fd);manager->expected_fd=-1;}
    }
    if(owner->authorize_timer)wl_event_source_remove(owner->authorize_timer);
    wl_list_remove(&owner->new_surface.link);wl_list_remove(&owner->unlock.link);wl_list_remove(&owner->destroy.link);
    struct lock_surface *entry,*tmp;
    wl_list_for_each_safe(entry,tmp,&owner->surfaces,link)destroy_surface(entry);
    wlr_scene_node_destroy(&owner->tree->node);manager->owner=NULL;free(owner);
    if(manager->server->locked && !manager->server->shutting_down) {
        wlr_log(WLR_ERROR,"Locker disconnected: keeping the session locked with opaque backgrounds");
        madway_lock_focus(manager->server,NULL);madway_session_publish_state(manager->server);
    }
}
static void unlock(struct wl_listener *listener,void *data)
{
    (void)data;
    struct lock_owner *owner=wl_container_of(listener,owner,unlock);
    if(!owner->authorized || !owner->acknowledged)return;
    struct madway_server *server=owner->manager->server;
    server->locked=false;owner->manager->ready=false;owner->manager->expected_pid=0;
    if(owner->manager->expected_fd>=0){close(owner->manager->expected_fd);owner->manager->expected_fd=-1;}
    wlr_seat_keyboard_notify_clear_focus(server->seat);wlr_seat_pointer_notify_clear_focus(server->seat);
    wlr_scene_node_set_enabled(&owner->manager->tree->node,false);
    wlr_scene_node_set_enabled(&server->desktop_tree->node,true);
    madway_discard_held_keys(server);
    madway_workspace_arrange(server);
    if(server->focused_view)madway_focus_view(server,server->focused_view);else madway_workspace_focus(server);
    madway_rebase_cursor(server);madway_session_publish_state(server);
    wlr_log(WLR_INFO,"Session unlocked by the authenticated locker");
}
static void authorize_owner(struct lock_owner *owner)
{
    if(owner->authorized)return;
    owner->authorized=true;
    if(owner->authorize_timer){wl_event_source_remove(owner->authorize_timer);owner->authorize_timer=NULL;}
    wlr_scene_node_set_enabled(&owner->tree->node,true);
    madway_lock_blank(owner->manager->server);check_ready(owner->manager);
    madway_lock_focus(owner->manager->server,NULL);
}
static int authorize_expired(void *data)
{
    struct lock_owner *owner=data;
    wl_event_source_remove(owner->authorize_timer);owner->authorize_timer=NULL;
    wlr_session_lock_v1_destroy(owner->lock);return 0;
}
void madway_lock_authorize(struct madway_server *server,pid_t pid)
{
    struct madway_lock *manager=server->screen_lock;
    if(!manager || pid<=0)return;
    int fd=pidfd_open(pid,0);
    if(fd<0){wlr_log(WLR_ERROR,"Could not pin locker process identity");return;}
    if(manager->expected_fd>=0)close(manager->expected_fd);
    manager->expected_fd=fd;
    manager->expected_pid=pid;
    struct pollfd identity={.fd=manager->expected_fd,.events=POLLIN};
    if(manager->owner && !manager->owner->authorized && manager->owner->pid==pid && poll(&identity,1,0)==0)authorize_owner(manager->owner);
}
static void new_lock(struct wl_listener *listener,void *data)
{
    struct madway_lock *manager=wl_container_of(listener,manager,new_lock);
    struct wlr_session_lock_v1 *lock=data;
    if(manager->owner){wlr_session_lock_v1_destroy(lock);return;}
    struct lock_owner *owner=calloc(1,sizeof(*owner));
    if(!owner){wl_client_post_no_memory(wl_resource_get_client(lock->resource));return;}
    owner->manager=manager;owner->lock=lock;wl_list_init(&owner->surfaces);
    wl_client_get_credentials(wl_resource_get_client(lock->resource),&owner->pid,NULL,NULL);
    owner->tree=wlr_scene_tree_create(manager->tree);
    if(!owner->tree){free(owner);wl_client_post_no_memory(wl_resource_get_client(lock->resource));return;}
    manager->owner=owner;wlr_scene_node_set_enabled(&owner->tree->node,false);
    owner->new_surface.notify=new_surface;wl_signal_add(&lock->events.new_surface,&owner->new_surface);
    owner->unlock.notify=unlock;wl_signal_add(&lock->events.unlock,&owner->unlock);
    owner->destroy.notify=owner_destroyed;wl_signal_add(&lock->events.destroy,&owner->destroy);
    struct pollfd identity={.fd=manager->expected_fd,.events=POLLIN};
    if(manager->expected_pid==owner->pid && manager->expected_fd>=0 && poll(&identity,1,0)==0)authorize_owner(owner);
    else {
        owner->authorize_timer=wl_event_loop_add_timer(wl_display_get_event_loop(manager->server->display),authorize_expired,owner);
        if(!owner->authorize_timer){wlr_session_lock_v1_destroy(lock);return;}
        wl_event_source_timer_update(owner->authorize_timer,1500);
    }
}
static void output_precommit(struct wl_listener *listener,void *data)
{
    struct madway_lock_output *state=wl_container_of(listener,state,precommit);
    struct wlr_output_event_precommit *event=data;
    if(state->output->server->locked && !state->submitted && (event->state->committed&WLR_OUTPUT_STATE_BUFFER)) {
        state->submitted=true;state->sequence=event->output->commit_seq+1;
    }
}
static void output_present(struct wl_listener *listener,void *data)
{
    struct madway_lock_output *state=wl_container_of(listener,state,present);
    struct wlr_output_event_present *event=data;
    if(state->output->server->locked && state->submitted && event->presented &&
            (int32_t)(event->commit_seq-state->sequence)>=0) {
        state->presented=true;check_ready(state->output->server->screen_lock);
    }
}
bool madway_lock_add_output(struct madway_output *output)
{
    struct madway_lock *manager=output->server->screen_lock;
    struct madway_lock_output *state=calloc(1,sizeof(*state));
    if(!manager || !state){free(state);return false;}
    state->output=output;
    const float black[4]={0,0,0,1};state->black=wlr_scene_rect_create(manager->tree,0,0,black);
    if(!state->black){free(state);return false;}
    output->lock_data=state;
    if(manager->message)state->message=wlr_scene_buffer_create(manager->tree,manager->message);
    state->precommit.notify=output_precommit;wl_signal_add(&output->output->events.precommit,&state->precommit);
    state->present.notify=output_present;wl_signal_add(&output->output->events.present,&state->present);
    return true;
}
void madway_lock_remove_output(struct madway_output *output)
{
    struct madway_lock_output *state=output->lock_data;if(!state)return;
    wl_list_remove(&state->precommit.link);wl_list_remove(&state->present.link);
    if(state->message)wlr_scene_node_destroy(&state->message->node);
    wlr_scene_node_destroy(&state->black->node);free(state);output->lock_data=NULL;
}
void madway_lock_arrange(struct madway_server *server)
{
    struct madway_lock *manager=server->screen_lock;if(!manager)return;
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link) {
        struct madway_lock_output *state=output->lock_data;if(!state)continue;
        int width,height;wlr_output_effective_resolution(output->output,&width,&height);
        wlr_scene_rect_set_size(state->black,width>0?width:1,height>0?height:1);
        wlr_scene_node_set_position(&state->black->node,output->layout_x,output->layout_y);
        wlr_scene_node_set_enabled(&state->black->node,output->output->enabled);
        if(state->message) {
            int message_width=width<560?width:560;
            if(message_width<1)message_width=1;
            wlr_scene_buffer_set_dest_size(state->message,message_width,80);
            wlr_scene_node_set_position(&state->message->node,output->layout_x+(width-message_width)/2,output->layout_y+height/2-40);
            wlr_scene_node_set_enabled(&state->message->node,output->output->enabled);
        }
        if(state->enabled!=output->output->enabled) {
            state->submitted=false;state->presented=false;state->enabled=output->output->enabled;
            if(server->locked && state->enabled) {
                wlr_damage_ring_add_whole(&output->scene_output->damage_ring);wlr_output_schedule_frame(output->output);
            }
        }
    }
    if(manager->owner) {
        struct lock_surface *entry;
        wl_list_for_each(entry,&manager->owner->surfaces,link)configure_surface(entry);
        wlr_scene_node_raise_to_top(&manager->owner->tree->node);
    }
    check_ready(manager);if(server->locked)madway_lock_focus(server,NULL);
}
bool madway_lock_secure_output(struct madway_output *output,struct wlr_output_state *state)
{
    if(!output->server->locked || !(state->committed&WLR_OUTPUT_STATE_ENABLED) || !state->enabled)return true;
    /* Never re-enable a screen using a framebuffer retained from the desktop. */
    wlr_damage_ring_add_whole(&output->scene_output->damage_ring);
    return wlr_scene_output_build_state(output->scene_output,state,NULL);
}
bool madway_lock_init(struct madway_server *server)
{
    struct madway_lock *manager=calloc(1,sizeof(*manager));if(!manager)return false;
    manager->server=server;manager->expected_fd=-1;manager->tree=wlr_scene_tree_create(&server->scene->tree);
    manager->protocol=wlr_session_lock_manager_v1_create(server->display);
    if(!manager->tree || !manager->protocol){if(manager->tree)wlr_scene_node_destroy(&manager->tree->node);free(manager);return false;}
    server->screen_lock=manager;wlr_scene_node_set_enabled(&manager->tree->node,false);
    manager->message=create_message();
    manager->new_lock.notify=new_lock;wl_signal_add(&manager->protocol->events.new_lock,&manager->new_lock);
    return true;
}
void madway_lock_finish(struct madway_server *server)
{
    struct madway_lock *manager=server->screen_lock;if(!manager)return;
    if(manager->owner)wlr_session_lock_v1_destroy(manager->owner->lock);
    wl_list_remove(&manager->new_lock.link);
    struct madway_output *output;wl_list_for_each(output,&server->outputs,link)madway_lock_remove_output(output);
    if(manager->message)wlr_buffer_drop(manager->message);
    if(manager->expected_fd>=0)close(manager->expected_fd);
    free(manager);server->screen_lock=NULL;
}
