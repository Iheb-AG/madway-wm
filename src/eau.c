#include "eau.h"
#include "decoration.h"
#include "main.h"
#include "view.h"
#include <pango/pangocairo.h>
#include <drm_fourcc.h>
#include <math.h>
#include <stdlib.h>
#include <wlr/interfaces/wlr_buffer.h>

enum { SHADOW_SIZE = 100, SHADOW_KERNEL = 36, SHADOW_CENTER = 18 };
struct shadow_pixels {
    struct wlr_buffer base;
    uint32_t data[SHADOW_SIZE * SHADOW_SIZE];
};
static void shadow_destroy(struct wlr_buffer *base) {free(base);}
static bool shadow_read(struct wlr_buffer *base, uint32_t flags, void **data, uint32_t *format, size_t *stride)
{
    if (flags & WLR_BUFFER_DATA_PTR_ACCESS_WRITE) return false;
    struct shadow_pixels *pixels = wl_container_of(base, pixels, base);
    *data = pixels->data;*format = DRM_FORMAT_ARGB8888;*stride = SHADOW_SIZE * 4;
    return true;
}
static void shadow_end(struct wlr_buffer *base) {(void)base;}
static const struct wlr_buffer_impl shadow_impl = {
    .destroy=shadow_destroy,.begin_data_ptr_access=shadow_read,.end_data_ptr_access=shadow_end,
};

static double footprint(double x, double y, double left, double top)
{
    double dx = fabs(x + .5 - left - 32) - 25, dy = fabs(y + .5 - top - 32) - 25;
    double distance = hypot(fmax(dx, 0), fmax(dy, 0)) + fmin(fmax(dx,dy), 0) - 7;
    return fmax(0, fmin(1, .5 - distance));
}

static struct wlr_buffer *make_shadow(void)
{
    struct shadow_pixels *pixels = calloc(1, sizeof(*pixels));
    double *shape = calloc(SHADOW_SIZE * SHADOW_SIZE, sizeof(double));
    double *row = calloc(SHADOW_SIZE * SHADOW_SIZE, sizeof(double));
    if (pixels == NULL || shape == NULL || row == NULL) {free(pixels);free(shape);free(row);return NULL;}
    double kernel[SHADOW_KERNEL], sum = 0;
    for (int k = 0; k < SHADOW_KERNEL; ++k) {
        double x = k - SHADOW_CENTER;
        sum += kernel[k] = exp(-x * x / (2 * 12.0 * 12.0));
    }
    for (int k = 0; k < SHADOW_KERNEL; ++k) kernel[k] /= sum;
    for (int y = 0; y < SHADOW_SIZE; ++y)
        for (int x = 0; x < SHADOW_SIZE; ++x)
            shape[y * SHADOW_SIZE + x] = footprint(x, y, 18, 18);
    for (int y = 0; y < SHADOW_SIZE; ++y)
        for (int x = 0; x < SHADOW_SIZE; ++x)
            for (int k = 0; k < SHADOW_KERNEL; ++k) {
                int sx = x + k - SHADOW_CENTER;
                if (sx >= 0 && sx < SHADOW_SIZE) row[y * SHADOW_SIZE + x] += shape[y * SHADOW_SIZE + sx] * kernel[k];
            }
    for (int y = 0; y < SHADOW_SIZE; ++y)
        for (int x = 0; x < SHADOW_SIZE; ++x) {
            double value = 0;
            for (int k = 0; k < SHADOW_KERNEL; ++k) {
                int sy = y + k - SHADOW_CENTER;
                if (sy >= 0 && sy < SHADOW_SIZE) value += row[sy * SHADOW_SIZE + x] * kernel[k];
            }
            /* Shadow origin (-18,-10), footprint shifted down by 8 pixels. */
            value *= 1 - footprint(x, y, 18, 10);
            pixels->data[y * SHADOW_SIZE + x] = (uint32_t)(fmin(value,1) * .4 * 255) << 24;
        }
    free(shape);free(row);
    wlr_buffer_init(&pixels->base, &shadow_impl, SHADOW_SIZE, SHADOW_SIZE);
    return &pixels->base;
}

static bool no_shadow_input(struct wlr_scene_buffer *buffer, double *sx, double *sy)
{
    (void)buffer;(void)sx;(void)sy;return false;
}

void madway_eau_shadow(struct madway_view *view, int width, int height, bool enabled)
{
    wlr_scene_node_set_enabled(&view->shadow_tree->node, enabled);
    if (!enabled) return;
    if (view->shadows[0] == NULL) {
        struct wlr_buffer *pixels = make_shadow();
        if (pixels == NULL) return;
        for (int i = 0; i < 8; ++i) {
            view->shadows[i] = wlr_scene_buffer_create(view->shadow_tree, pixels);
            if (view->shadows[i] == NULL) {
                for (int j = 0; j < i; ++j) {wlr_scene_node_destroy(&view->shadows[j]->node);view->shadows[j] = NULL;}
                wlr_buffer_drop(pixels);return;
            }
            view->shadows[i]->point_accepts_input = no_shadow_input;
        }
        wlr_buffer_drop(pixels);
    }
    /* Eight reusable texture slices: resizing never regenerates a large blur. */
    int total_w = width + 36, total_h = height + 36;
    int side_x = total_w < 100 ? total_w / 2 : 50, side_y = total_h < 100 ? total_h / 2 : 50;
    int dx[] = {0, side_x, total_w - side_x, total_w};
    int dy[] = {0, side_y, total_h - side_y, total_h};
    int source[] = {0, 50, 50};
    int sizes[] = {50, 1, 50};
    int index = 0;
    for (int y = 0; y < 3; ++y)
        for (int x = 0; x < 3; ++x) {
            if (x == 1 && y == 1) continue;
            struct wlr_scene_buffer *slice = view->shadows[index++];
            struct wlr_fbox box = {source[x], source[y], sizes[x], sizes[y]};
            wlr_scene_buffer_set_source_box(slice, &box);
            wlr_scene_node_set_position(&slice->node, dx[x] - 18, dy[y] - 10);
            int w = dx[x+1]-dx[x], h = dy[y+1]-dy[y];
            wlr_scene_node_set_enabled(&slice->node, w > 0 && h > 0);
            if (w > 0 && h > 0) wlr_scene_buffer_set_dest_size(slice, w, h);
        }
}

int madway_eau_button_width(int width, int height)
{
    return width / 3 < height ? width / 3 : height;
}

static void gradient(cairo_t *cr, double top, double bottom, int height)
{
    cairo_pattern_t *paint = cairo_pattern_create_linear(0, 0, 0, height);
    cairo_pattern_add_color_stop_rgb(paint, 0, top, top, top);
    cairo_pattern_add_color_stop_rgb(paint, 1, bottom, bottom, bottom);
    cairo_set_source(cr, paint);
    cairo_paint(cr);
    cairo_pattern_destroy(paint);
}

void madway_eau_title(cairo_t *cr, struct madway_view *view, int width, int height)
{
    bool active = view->server->focused_view == view;
    bool dark = view->server->config.eau_dark;
    int button = madway_eau_button_width(width, height);
    double radius = width < 14 ? width / 2.0 : 7;
    /* Clip the actual buffer, leaving its upper corners transparent. */
    cairo_move_to(cr, 0, height);
    cairo_line_to(cr, 0, radius);
    cairo_curve_to(cr, 0, radius * .448, radius * .448, 0, radius, 0);
    cairo_line_to(cr, width - radius, 0);
    cairo_curve_to(cr, width - radius * .448, 0, width, radius * .448, width, radius);
    cairo_line_to(cr, width, height);
    cairo_close_path(cr);
    cairo_clip(cr);
    gradient(cr, dark ? (active ? .24 : .19) : (active ? .83 : .92),
            dark ? (active ? .17 : .14) : (active ? .63 : .83), height);
    cairo_set_source_rgba(cr, 1, 1, 1, .35);
    cairo_rectangle(cr, 0, 0, width, 1);cairo_fill(cr);
    double edge_color = dark ? .08 : active ? .4 : .85;
    cairo_set_source_rgb(cr, edge_color, edge_color, edge_color);
    cairo_rectangle(cr, 0, height - 1, width, 1);cairo_fill(cr);

    const enum madway_frame_part parts[] = {MADWAY_FRAME_CLOSE, MADWAY_FRAME_MINIMIZE, MADWAY_FRAME_MAXIMIZE};
    const double colors[3][3] = {{.95,.45,.42},{.95,.75,.25},{.35,.78,.35}};
    const int positions[] = {0, width - 2 * button, width - button};
    for (int i = 0; i < 3; ++i) {
        double x = positions[i], center = x + button / 2.0, cy = height / 2.0;
        bool hover = view->frame_hover == (int)parts[i];
        if (hover) {
            cairo_save(cr);
            cairo_rectangle(cr, x, 0, button, height);cairo_clip(cr);
            cairo_pattern_t *paint = cairo_pattern_create_linear(0, 0, 0, height);
            cairo_pattern_add_color_stop_rgb(paint, 0, colors[i][0], colors[i][1], colors[i][2]);
            cairo_pattern_add_color_stop_rgb(paint, 1, colors[i][0]-.1, colors[i][1]-.1, colors[i][2]-.1);
            cairo_set_source(cr, paint);cairo_paint(cr);cairo_pattern_destroy(paint);
            cairo_restore(cr);
        }
        cairo_set_source_rgba(cr, active ? .4 : .92, active ? .4 : .92, active ? .4 : .92, active ? .55 : .5);
        cairo_set_line_width(cr, 1);
        double edge = i == 0 ? button - .5 : x + .5;
        cairo_move_to(cr, edge, 1);cairo_line_to(cr, edge, height - 1);cairo_stroke(cr);
        if (!active && !hover && !dark) continue;
        cairo_set_source_rgb(cr, dark ? 1 : .2, dark ? 1 : .2, dark ? 1 : .2);
        cairo_set_line_width(cr, 1.5);
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        double size = height < 18 ? 1.6 : 2.2;
        if (i == 0) {
            cairo_move_to(cr, center-size, cy-size);cairo_line_to(cr, center+size, cy+size);
            cairo_move_to(cr, center+size, cy-size);cairo_line_to(cr, center-size, cy+size);
        } else {
            cairo_move_to(cr, center-size, cy);cairo_line_to(cr, center+size, cy);
            if (i == 2) {cairo_move_to(cr, center, cy-size);cairo_line_to(cr, center, cy+size);}
        }
        cairo_stroke(cr);
    }
    int available = width - 3 * button - 8;
    if (available <= 0) return;
    PangoLayout *layout = pango_cairo_create_layout(cr);
    PangoFontDescription *font = pango_font_description_from_string("Inter Medium");
    pango_font_description_set_absolute_size(font, (height < 18 ? 10 : 13) * PANGO_SCALE);
    pango_layout_set_font_description(layout, font);
    pango_layout_set_single_paragraph_mode(layout, true);
    pango_layout_set_ellipsize(layout, PANGO_ELLIPSIZE_MIDDLE);
    pango_layout_set_width(layout, available * PANGO_SCALE);
    pango_layout_set_text(layout, view->toplevel->title != NULL ? view->toplevel->title : "madway", -1);
    int tw, th;pango_layout_get_pixel_size(layout, &tw, &th);
    double x = (width - tw) / 2.0;
    if (x > width - 2 * button - 4 - tw) x = width - 2 * button - 4 - tw;
    if (x < button + 4) x = button + 4;
    double title_color = dark ? (active ? .94 : .65) : (active ? .05 : .7);
    cairo_set_source_rgb(cr, title_color, title_color, title_color);
    cairo_move_to(cr, x, (height - th) / 2.0);pango_cairo_show_layout(cr, layout);
    pango_font_description_free(font);g_object_unref(layout);
}
