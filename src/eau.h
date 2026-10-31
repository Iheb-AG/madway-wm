#ifndef MADWAY_EAU_H
#define MADWAY_EAU_H
#include <cairo.h>
#include <stdbool.h>
struct madway_view;
int madway_eau_button_width(int width, int height);
void madway_eau_title(cairo_t *cr, struct madway_view *view, int width, int height);
void madway_eau_shadow(struct madway_view *view, int width, int height, bool enabled);
#endif
