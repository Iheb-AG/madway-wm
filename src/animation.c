#include "animation.h"
#include "main.h"
#include "motion.h"
#include "transition.h"
#include "dock.h"
#include <time.h>

double madway_animation_now(void)
{
    struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);
    return now.tv_sec*1000.0+now.tv_nsec/1000000.0;
}

/* Gentle acceleration and a long, controlled settle: cubic-bezier(.32,0,.18,1). */
double madway_animation_ease(double progress)
{
    if (progress<=0) return 0;
    if (progress>=1) return 1;
    double low=0,high=1;
    for (int i=0;i<24;++i) {
        double t=(low+high)*.5,u=1-t;
        double x=3*u*u*t*.32+3*u*t*t*.18+t*t*t;
        if (x<progress) low=t;else high=t;
    }
    double t=(low+high)*.5;
    return t*t*(3-2*t);
}

void madway_animation_frame(struct madway_output *output)
{
    double now=madway_animation_now();
    madway_transition_frame(output,now);
    madway_motion_frame(output,now);
    madway_dock_frame(output);
}

bool madway_animation_active(struct madway_output *output)
{
    return madway_transition_active(output) || madway_motion_active(output) || madway_dock_active(output);
}
