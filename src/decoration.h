#ifndef MADWAY_DECORATION_H
#define MADWAY_DECORATION_H

#include <stdbool.h>
#include <stdint.h>

#define MADWAY_TITLE_HEIGHT 18
#define MADWAY_BORDER 1

enum madway_frame_part { MADWAY_FRAME_NONE, MADWAY_FRAME_TITLE, MADWAY_FRAME_CLOSE, MADWAY_FRAME_MAXIMIZE };
struct madway_view;

bool madway_frame_create(struct madway_view *view);
void madway_frame_update(struct madway_view *view);
void madway_frame_extents(struct madway_view *view, int *border, int *title);
uint32_t madway_frame_edges(struct madway_view *view, double lx, double ly);
enum madway_frame_part madway_frame_at(struct madway_view *view, double lx, double ly);

#endif
