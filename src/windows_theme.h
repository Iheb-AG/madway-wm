#ifndef MADWAY_WINDOWS_THEME_H
#define MADWAY_WINDOWS_THEME_H
#include <cairo.h>
struct madway_view;
int madway_windows_button_width(int height);
void madway_windows_title(cairo_t *cr,struct madway_view *view,int width,int height);
#endif
