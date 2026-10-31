#ifndef MADWAY_DEVICES_H
#define MADWAY_DEVICES_H
struct madway_server;
struct wlr_input_device;
void madway_configure_pointer(struct madway_server *server,struct wlr_input_device *device);
#endif
