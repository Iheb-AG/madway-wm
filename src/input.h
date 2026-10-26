#ifndef MADWAY_INPUT_H
#define MADWAY_INPUT_H

#include <stdbool.h>
struct madway_server;

bool madway_init_input(struct madway_server *server);
void madway_finish_input(struct madway_server *server);
void madway_rebase_cursor(struct madway_server *server);
void madway_cancel_pointer_grab(struct madway_server *server);

#endif
