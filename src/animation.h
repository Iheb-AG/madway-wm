#ifndef MADWAY_ANIMATION_H
#define MADWAY_ANIMATION_H
#include <stdbool.h>
struct madway_output;
double madway_animation_now(void);
double madway_animation_ease(double progress);
void madway_animation_frame(struct madway_output *output);
bool madway_animation_active(struct madway_output *output);
#endif
