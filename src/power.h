#ifndef MADWAY_POWER_H
#define MADWAY_POWER_H
#include <stdbool.h>
struct madway_server;
struct wlr_input_device;
void madway_power_init(struct madway_server *server);
void madway_power_finish(struct madway_server *server);
void madway_power_add_switch(struct madway_server *server, struct wlr_input_device *device);
void madway_power_lid_outputs(struct madway_server *server);
void madway_power_prepare_sleep(struct madway_server *server);
void madway_power_resume(struct madway_server *server);
#endif
