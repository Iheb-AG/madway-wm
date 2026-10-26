#include "decoration.h"
#include "main.h"
#include "view.h"

#include <cairo.h>
#include <drm_fourcc.h>
#include <pango/pangocairo.h>
#include <stdlib.h>
#include <string.h>
#include <wlr/interfaces/wlr_buffer.h>
#include <wlr/util/edges.h>
#include <wlr/util/log.h>

struct title_pixels
{
    struct wlr_buffer base;
    cairo_surface_t *surface;
};

static void destroy_title_pixels(struct wlr_buffer *buffer)
{
    struct title_pixels *pixels = wl_container_of(buffer, pixels, base);
    cairo_surface_destroy(pixels->surface);
    free(pixels);
}

static bool read_title_pixels(struct wlr_buffer *buffer, uint32_t flags,
        void **data, uint32_t *format, size_t *stride)
{
    struct title_pixels *pixels = wl_container_of(buffer, pixels, base);
    if (flags & WLR_BUFFER_DATA_PTR_ACCESS_WRITE) return false;
    *data = cairo_image_surface_get_data(pixels->surface);
    *format = DRM_FORMAT_ARGB8888;
    *stride = (size_t)cairo_image_surface_get_stride(pixels->surface);
    return true;
}

static void finish_title_read(struct wlr_buffer *buffer) { (void)buffer; }

static const struct wlr_buffer_impl title_impl = {
    .destroy = destroy_title_pixels,
    .begin_data_ptr_access = read_title_pixels,
    .end_data_ptr_access = finish_title_read,
};

static struct wlr_buffer *draw_title(struct madway_view *view, int width)
{
    int title_height = view->server->config.title_height;
    struct title_pixels *pixels = calloc(1, sizeof(*pixels));
    if (pixels == NULL) return NULL;
    pixels->surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, width, title_height);
    if (cairo_surface_status(pixels->surface) != CAIRO_STATUS_SUCCESS)
    {
        cairo_surface_destroy(pixels->surface);
        free(pixels);
        return NULL;
    }
    bool active = view->server->focused_view == view;
    cairo_t *cr = cairo_create(pixels->surface);
    if (active) cairo_set_source_rgb(cr, 0xd9 / 255., 0x77 / 255., 0x06 / 255.);
    else cairo_set_source_rgb(cr, 0x1c / 255., 0x1f / 255., 0x24 / 255.);
    cairo_paint(cr);
    cairo_set_source_rgb(cr, active ? .04 : .77, active ? .05 : .80, active ? .06 : .85);

    PangoLayout *layout = pango_cairo_create_layout(cr);
    PangoFontDescription *font = pango_font_description_from_string("monospace");
    pango_font_description_set_absolute_size(font, 10 * PANGO_SCALE);
    pango_layout_set_font_description(layout, font);
    pango_layout_set_single_paragraph_mode(layout, true);
    pango_layout_set_ellipsize(layout, PANGO_ELLIPSIZE_END);
    pango_layout_set_width(layout, (width > 40 ? width - 40 : 1) * PANGO_SCALE);
    pango_layout_set_text(layout, view->toplevel->title != NULL ? view->toplevel->title : "madway", -1);
    int text_height;
    pango_layout_get_pixel_size(layout, NULL, &text_height);
    cairo_move_to(cr, 4, (title_height - text_height) / 2);
    pango_cairo_show_layout(cr, layout);
    pango_font_description_free(font);
    g_object_unref(layout);

    // Square, pixel-aligned maximize/restore and close controls; no animation.
    cairo_translate(cr, 0, (title_height - 18) / 2);
    cairo_set_antialias(cr, CAIRO_ANTIALIAS_NONE);
    cairo_set_line_width(cr, 1);
    cairo_move_to(cr, width - 32, 1);
    cairo_line_to(cr, width - 32, 17);
    cairo_move_to(cr, width - 16, 1);
    cairo_line_to(cr, width - 16, 17);
    cairo_stroke(cr);
    cairo_rectangle(cr, width - 28, 5, 8, 8);
    if (view->maximized) cairo_rectangle(cr, width - 26, 3, 8, 8);
    cairo_move_to(cr, width - 12, 5);
    cairo_line_to(cr, width - 5, 12);
    cairo_move_to(cr, width - 5, 5);
    cairo_line_to(cr, width - 12, 12);
    cairo_stroke(cr);
    cairo_destroy(cr);
    cairo_surface_flush(pixels->surface);
    wlr_buffer_init(&pixels->base, &title_impl, width, title_height);
    return &pixels->base;
}

bool madway_frame_create(struct madway_view *view)
{
    const float highlight[4] = {0x3a / 255.f, 0x3f / 255.f, 0x4b / 255.f, 1};
    const float shadow[4] = {0x0b / 255.f, 0x0d / 255.f, 0x10 / 255.f, 1};
    for (int i = 0; i < 4; ++i)
    {
        view->borders[i] = wlr_scene_rect_create(view->scene_tree, 0, 0, i < 2 ? highlight : shadow);
        if (view->borders[i] == NULL) return false;
        wlr_scene_node_set_enabled(&view->borders[i]->node, false);
    }
    view->title_buffer = wlr_scene_buffer_create(view->scene_tree, NULL);
    return view->title_buffer != NULL;
}

void madway_frame_extents(struct madway_view *view, int *border, int *title)
{
    *border = view->decorated && !view->fullscreen ? MADWAY_BORDER : 0;
    *title = *border && view->floating ? view->server->config.title_height : 0;
}

void madway_frame_update(struct madway_view *view)
{
    int border, title_height;
    madway_frame_extents(view, &border, &title_height);
    bool visible = border != 0;
    int width = view->toplevel->base->geometry.width;
    int height = view->toplevel->base->geometry.height;
    if (view->content_tree != NULL)
        wlr_scene_node_set_position(&view->content_tree->node, border, title_height + border);
    for (int i = 0; i < 4; ++i)
        wlr_scene_node_set_enabled(&view->borders[i]->node, visible);
    wlr_scene_node_set_enabled(&view->title_buffer->node, title_height > 0);
    bool active = view->server->focused_view == view;
    const char *title = view->toplevel->title != NULL ? view->toplevel->title : "madway";
    if (!visible || width <= 0 || height <= 0)
    {
        view->frame_visible = false;
        return;
    }
    if (view->frame_visible && view->frame_width == width && view->frame_height == height &&
        view->frame_title_height == title_height &&
        view->frame_active == active && view->frame_title != NULL && !strcmp(view->frame_title, title))
        return;

    const float highlight[4] = {0x3a / 255.f, 0x3f / 255.f, 0x4b / 255.f, 1};
    const float shadow[4] = {0x0b / 255.f, 0x0d / 255.f, 0x10 / 255.f, 1};
    const float amber[4] = {0xd9 / 255.f, 0x77 / 255.f, 0x06 / 255.f, 1};
    for (int i = 0; i < 4; ++i)
        wlr_scene_rect_set_color(view->borders[i], title_height == 0 && active ? amber : i < 2 ? highlight : shadow);

    wlr_scene_rect_set_size(view->borders[0], width + 2, 1);
    wlr_scene_rect_set_size(view->borders[1], 1, height + title_height + 1);
    wlr_scene_node_set_position(&view->borders[1]->node, 0, 1);
    wlr_scene_rect_set_size(view->borders[2], 1, height + title_height + 1);
    wlr_scene_node_set_position(&view->borders[2]->node, width + 1, 1);
    wlr_scene_rect_set_size(view->borders[3], width + 2, 1);
    wlr_scene_node_set_position(&view->borders[3]->node, 0, height + title_height + 1);
    wlr_scene_node_set_position(&view->title_buffer->node, 1, 1);
    struct wlr_buffer *buffer = title_height > 0 ? draw_title(view, width) : NULL;
    if (title_height > 0 && buffer == NULL)
    {
        wlr_log(WLR_ERROR, "Could not render window title");
        return;
    }
    wlr_scene_buffer_set_buffer(view->title_buffer, buffer);
    if (buffer != NULL) wlr_buffer_drop(buffer); // The scene keeps its own reference until replaced/destroyed.
    free(view->frame_title);
    view->frame_title = strdup(title);
    view->frame_width = width;
    view->frame_height = height;
    view->frame_title_height = title_height;
    view->frame_active = active;
    view->frame_visible = true;
}

uint32_t madway_frame_edges(struct madway_view *view, double lx, double ly)
{
    if (!view->decorated || !view->floating || view->fullscreen || view->maximized) return 0;
    double x = lx - view->scene_tree->node.x, y = ly - view->scene_tree->node.y;
    int width = view->toplevel->base->geometry.width + 2;
    int height = view->toplevel->base->geometry.height + view->server->config.title_height + 2;
    if (x < 0 || y < 0 || x >= width || y >= height) return 0;
    return (x < 1 ? WLR_EDGE_LEFT : x >= width - 1 ? WLR_EDGE_RIGHT : 0) |
        (y < 1 ? WLR_EDGE_TOP : y >= height - 1 ? WLR_EDGE_BOTTOM : 0);
}

enum madway_frame_part madway_frame_at(struct madway_view *view, double lx, double ly)
{
    if (!view->decorated || !view->floating || view->fullscreen) return MADWAY_FRAME_NONE;
    double x = lx - view->scene_tree->node.x, y = ly - view->scene_tree->node.y;
    int width = view->toplevel->base->geometry.width;
    if (x < 1 || x >= width + 1 || y < 1 || y >= view->server->config.title_height + 1)
        return MADWAY_FRAME_NONE;
    if (x >= width - 15) return MADWAY_FRAME_CLOSE;
    if (x >= width - 31) return MADWAY_FRAME_MAXIMIZE;
    return MADWAY_FRAME_TITLE;
}
