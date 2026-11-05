#ifndef MADWAY_ARGENT_H
#define MADWAY_ARGENT_H
#include <cairo.h>
#include <stdbool.h>
struct madway_view;
int madway_argent_button_width(int width, int height);
void madway_argent_title(cairo_t *cr, struct madway_view *view, int width, int height);
void madway_argent_shadow(struct madway_view *view, int width, int height, bool enabled);
#endif
