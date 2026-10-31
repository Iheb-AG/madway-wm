#include "preview.h"
#include "main.h"
#include "view.h"
#include "decoration.h"
#include <cairo.h>
#include <drm_fourcc.h>
#include <glib.h>
#include <glib/gstdio.h>
#include <math.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <wlr/render/swapchain.h>
#include <wlr/types/wlr_buffer.h>
#include <wlr/types/wlr_linux_drm_syncobj_v1.h>

enum { WIDTH=240, HEIGHT=160 };
struct capture {
    struct madway_view *view;
    struct madway_server *server;
    struct wlr_render_pass *pass;
    GPtrArray *textures;
    double scale;
    int x,y;
    pixman_region32_t clip;
    bool content;
};

static char *directory(struct madway_server *server)
{
    if (!server->socket_name) return NULL;
    return g_strdup_printf("%s/madway-%s/previews",g_get_user_runtime_dir(),server->socket_name);
}

static char *filename(struct madway_view *view)
{
    char *dir=directory(view->server);
    char *path=dir?g_strdup_printf("%s/%u.png",dir,view->id):NULL;
    g_free(dir);return path;
}

void madway_preview_remove(struct madway_view *view)
{
    char *path=filename(view);
    if (path) {g_unlink(path);g_free(path);}
    view->preview_serial=0;
}

void madway_preview_clear(struct madway_server *server)
{
    struct madway_view *view;
    wl_list_for_each(view,&server->views,link) madway_preview_remove(view);
    char *dir=directory(server);
    if (dir) {
        GDir *files=g_dir_open(dir,0,NULL);const char *name;
        while (files && (name=g_dir_read_name(files))) {
            char *path=g_build_filename(dir,name,NULL);g_unlink(path);g_free(path);
        }
        if (files) g_dir_close(files);
        g_rmdir(dir);g_free(dir);
    }
}

static struct wlr_box scaled(struct capture *capture,int x,int y,int width,int height)
{
    int left=(int)lround(x*capture->scale),top=(int)lround(y*capture->scale);
    return (struct wlr_box){capture->x+left,capture->y+top,
        (int)lround((x+width)*capture->scale)-left,(int)lround((y+height)*capture->scale)-top};
}

static void render_node(struct capture *capture,struct wlr_scene_node *node,int x,int y)
{
    if (!node->enabled || (capture->view && node==&capture->view->shadow_tree->node)) return;
    x+=node->x;y+=node->y;
    if (node->type==WLR_SCENE_NODE_TREE) {
        struct wlr_scene_node *child;
        wl_list_for_each(child,&wlr_scene_tree_from_node(node)->children,link) render_node(capture,child,x,y);
    } else if (node->type==WLR_SCENE_NODE_RECT) {
        struct wlr_scene_rect *rect=wlr_scene_rect_from_node(node);
        struct wlr_box box=scaled(capture,x,y,rect->width,rect->height);
        if (box.width<=0 || box.height<=0) return;
        wlr_render_pass_add_rect(capture->pass,&(struct wlr_render_rect_options){.box=box,.clip=&capture->clip,
            .color={rect->color[0],rect->color[1],rect->color[2],rect->color[3]}});
    } else if (node->type==WLR_SCENE_NODE_BUFFER) {
        struct wlr_scene_buffer *buffer=wlr_scene_buffer_from_node(node);
        if (!buffer->buffer) return;
        struct wlr_client_buffer *client=wlr_client_buffer_get(buffer->buffer);
        bool owned=!client || !client->texture;
        struct wlr_buffer *source=client?client->source:buffer->buffer;
        if (owned && !source) return;
        struct wlr_texture *texture=!owned?client->texture:wlr_texture_from_buffer(capture->server->renderer,source);
        if (!texture) return;
        if (owned) g_ptr_array_add(capture->textures,texture);
        int width=buffer->dst_width,height=buffer->dst_height;
        if (!width || !height) {
            width=(int)texture->width;height=(int)texture->height;
            if (buffer->transform&1) {int temporary=width;width=height;height=temporary;}
        }
        struct wlr_box box=scaled(capture,x,y,width,height);
        if (box.width<=0 || box.height<=0) return;
        struct wlr_scene_surface *surface=wlr_scene_surface_try_from_buffer(buffer);
        struct wlr_linux_drm_syncobj_surface_v1_state *sync=surface?wlr_linux_drm_syncobj_v1_get_surface_state(surface->surface):NULL;
        struct wlr_color_primaries primaries;
        if (buffer->primaries) wlr_color_primaries_from_named(&primaries,buffer->primaries);
        wlr_render_pass_add_texture(capture->pass,&(struct wlr_render_texture_options){.texture=texture,
            .src_box=buffer->src_box,.dst_box=box,.alpha=&buffer->opacity,.clip=&capture->clip,
            .transform=buffer->transform,.filter_mode=WLR_SCALE_FILTER_BILINEAR,
            .transfer_function=buffer->transfer_function,.primaries=buffer->primaries?&primaries:NULL,
            .color_encoding=buffer->color_encoding,.color_range=buffer->color_range,
            .wait_timeline=sync?sync->acquire_timeline:NULL,.wait_point=sync?sync->acquire_point:0});
        if (surface) capture->content=true;
    }
}

static void capture_view(struct madway_view *view,const struct wlr_drm_format *format)
{
    int border,title;madway_frame_extents(view,&border,&title);
    int width=view->toplevel->base->geometry.width+2*border;
    int height=view->toplevel->base->geometry.height+2*border+title;
    if (width<=0 || height<=0) return;
    struct wlr_buffer *buffer=wlr_allocator_create_buffer(view->server->allocator,WIDTH,HEIGHT,format);
    if (!buffer) return;
    struct wlr_render_pass *pass=wlr_renderer_begin_buffer_pass(view->server->renderer,buffer,NULL);
    if (!pass) {wlr_buffer_drop(buffer);return;}
    struct capture capture={.view=view,.server=view->server,.pass=pass,.scale=fmin((double)WIDTH/width,(double)HEIGHT/height),
        .textures=g_ptr_array_new_with_free_func((GDestroyNotify)wlr_texture_destroy)};
    capture.x=(WIDTH-(int)lround(width*capture.scale))/2;
    capture.y=(HEIGHT-(int)lround(height*capture.scale))/2;
    pixman_region32_init_rect(&capture.clip,capture.x,capture.y,(int)lround(width*capture.scale),(int)lround(height*capture.scale));
    wlr_render_pass_add_rect(pass,&(struct wlr_render_rect_options){.box={0,0,WIDTH,HEIGHT},.color={.06,.07,.08,1},.blend_mode=WLR_RENDER_BLEND_MODE_NONE});
    // Traverse the window itself, including minimized/covered content, without
    // enabling any node on the actual desktop or including another window.
    struct wlr_scene_node *child;
    wl_list_for_each(child,&view->scene_tree->children,link) render_node(&capture,child,0,0);
    bool rendered=wlr_render_pass_submit(pass);
    pixman_region32_fini(&capture.clip);g_ptr_array_unref(capture.textures);
    struct wlr_texture *texture=rendered && capture.content?wlr_texture_from_buffer(view->server->renderer,buffer):NULL;
    if (texture) {
        cairo_surface_t *image=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,WIDTH,HEIGHT);
        if (cairo_surface_status(image)==CAIRO_STATUS_SUCCESS && wlr_texture_read_pixels(texture,&(struct wlr_texture_read_pixels_options){
                    .data=cairo_image_surface_get_data(image),.format=DRM_FORMAT_ARGB8888,
                    .stride=(uint32_t)cairo_image_surface_get_stride(image)})) {
            cairo_surface_mark_dirty(image);
            char *path=filename(view),*temporary=path?g_strconcat(path,".tmp",NULL):NULL;
            if (temporary) {
                int fd=g_open(temporary,O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC,0600);
                if (fd>=0) {
                    close(fd);
                    if (cairo_surface_write_to_png(image,temporary)==CAIRO_STATUS_SUCCESS && g_rename(temporary,path)==0) {
                        if (++view->preview_serial==0) ++view->preview_serial;
                    }
                    g_unlink(temporary);
                }
                g_free(temporary);g_free(path);
            }
        }
        cairo_surface_destroy(image);wlr_texture_destroy(texture);
    }
    wlr_buffer_drop(buffer);
}

void madway_preview_capture(struct madway_server *server)
{
    if (server->locked || server->sleeping) return;
    const struct wlr_drm_format *format=NULL;
    struct madway_output *output;
    wl_list_for_each(output,&server->outputs,link)
        if (output->output->enabled && output->output->swapchain) {format=&output->output->swapchain->format;break;}
    if (!format) return;
    char *dir=directory(server);
    if (!dir || g_mkdir_with_parents(dir,0700)!=0) {g_free(dir);return;}
    g_free(dir);
    struct madway_view *view;
    wl_list_for_each(view,&server->layout_views,layout_link)
        if (view->mapped && !view->desktop_overlay && view->workspace==server->active_workspace) capture_view(view,format);
}

struct wlr_buffer *madway_window_snapshot(struct madway_view *view)
{
    struct madway_server *server=view->server;
    if (server->locked || server->sleeping || !view->mapped || !view->output || !view->output->output->swapchain) return NULL;
    int border,title;madway_frame_extents(view,&border,&title);
    int width=view->toplevel->base->geometry.width+2*border;
    int height=view->toplevel->base->geometry.height+2*border+title;
    if (width<=0 || height<=0) return NULL;
    double scale=view->output->output->scale;
    int pixels_w=(int)ceil(width*scale),pixels_h=(int)ceil(height*scale);
    struct wlr_buffer *buffer=wlr_allocator_create_buffer(server->allocator,pixels_w,pixels_h,&view->output->output->swapchain->format);
    if (!buffer) return NULL;
    struct wlr_render_pass *pass=wlr_renderer_begin_buffer_pass(server->renderer,buffer,NULL);
    if (!pass) {wlr_buffer_drop(buffer);return NULL;}
    struct capture capture={.server=server,.view=view,.pass=pass,.scale=scale,
        .textures=g_ptr_array_new_with_free_func((GDestroyNotify)wlr_texture_destroy)};
    pixman_region32_init_rect(&capture.clip,0,0,pixels_w,pixels_h);
    wlr_render_pass_add_rect(pass,&(struct wlr_render_rect_options){.box={0,0,pixels_w,pixels_h},.color={0,0,0,0},.blend_mode=WLR_RENDER_BLEND_MODE_NONE});
    struct wlr_scene_node *child;
    wl_list_for_each(child,&view->scene_tree->children,link) render_node(&capture,child,0,0);
    bool rendered=wlr_render_pass_submit(pass);
    pixman_region32_fini(&capture.clip);g_ptr_array_unref(capture.textures);
    if (!rendered || !capture.content) {wlr_buffer_drop(buffer);return NULL;}
    return buffer;
}

struct wlr_buffer *madway_scene_snapshot(struct madway_server *server,struct madway_output *output)
{
    if (server->locked || server->sleeping || !output->output->enabled || !output->output->swapchain) return NULL;
    int width,height;wlr_output_effective_resolution(output->output,&width,&height);
    if (width<=0 || height<=0) return NULL;
    double scale=output->output->scale;
    int pixels_w=(int)ceil(width*scale),pixels_h=(int)ceil(height*scale);
    struct wlr_buffer *buffer=wlr_allocator_create_buffer(server->allocator,pixels_w,pixels_h,&output->output->swapchain->format);
    if (!buffer) return NULL;
    struct wlr_render_pass *pass=wlr_renderer_begin_buffer_pass(server->renderer,buffer,NULL);
    if (!pass) {wlr_buffer_drop(buffer);return NULL;}
    struct capture capture={.server=server,.pass=pass,.scale=scale,.x=-(int)lround(output->layout_x*scale),.y=-(int)lround(output->layout_y*scale),
        .textures=g_ptr_array_new_with_free_func((GDestroyNotify)wlr_texture_destroy)};
    pixman_region32_init_rect(&capture.clip,0,0,pixels_w,pixels_h);
    wlr_render_pass_add_rect(pass,&(struct wlr_render_rect_options){.box={0,0,pixels_w,pixels_h},.color={0,0,0,1},.blend_mode=WLR_RENDER_BLEND_MODE_NONE});
    struct wlr_scene_tree *roots[]={server->backgrounds,server->layer_trees[0],server->layer_trees[1],server->windows,server->above_windows};
    for (size_t i=0;i<G_N_ELEMENTS(roots);++i) if (roots[i]) render_node(&capture,&roots[i]->node,0,0);
    bool rendered=wlr_render_pass_submit(pass);
    pixman_region32_fini(&capture.clip);g_ptr_array_unref(capture.textures);
    if (!rendered) {wlr_buffer_drop(buffer);return NULL;}
    return buffer;
}
