#ifndef MADWAY_MOTION_PROFILE_H
#define MADWAY_MOTION_PROFILE_H
#include <wlr/util/box.h>
struct _GKeyFile;
struct madway_config;
enum madway_open_style {MADWAY_OPEN_ZOOM, MADWAY_OPEN_FADE, MADWAY_OPEN_RISE, MADWAY_OPEN_SLIDE};
enum madway_maximize_style {MADWAY_MAXIMIZE_ZOOM, MADWAY_MAXIMIZE_DISSOLVE, MADWAY_MAXIMIZE_NONE};
enum madway_motion_curve {MADWAY_CURVE_GENTLE, MADWAY_CURVE_RESPONSIVE, MADWAY_CURVE_SPRING, MADWAY_CURVE_LINEAR};
void madway_motion_profile_load(struct madway_config *config,struct _GKeyFile *file);
double madway_motion_curve_value(enum madway_motion_curve curve,double progress);
struct wlr_box madway_motion_interpolate(struct wlr_box from,struct wlr_box to,enum madway_motion_curve curve,double progress);
struct wlr_box madway_motion_open_geometry(struct wlr_box target,enum madway_open_style style,int scale,int distance);
#endif
