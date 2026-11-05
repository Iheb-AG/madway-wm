#ifndef MADWAY_CLOSING_H
#define MADWAY_CLOSING_H
#include <stdbool.h>
struct madway_server;
struct madway_view;
struct madway_output;
void madway_close_begin(struct madway_view *view);
void madway_close_cancel(struct madway_server *server,struct madway_output *output);
void madway_close_frame(struct madway_output *output,double now);
bool madway_close_active(struct madway_output *output);
#endif
