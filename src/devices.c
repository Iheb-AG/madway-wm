#include "devices.h"
#include "main.h"
#include <string.h>
#include <wlr/backend/libinput.h>
#include <wlr/util/log.h>

static void check(enum libinput_config_status status,const char *option,struct libinput_device *device)
{
    if (status!=LIBINPUT_CONFIG_STATUS_SUCCESS)
        wlr_log(WLR_ERROR,"Could not configure %s on %s: %s",option,libinput_device_get_name(device),libinput_config_status_to_str(status));
}

void madway_configure_pointer(struct madway_server *server,struct wlr_input_device *input)
{
    if (!wlr_input_device_is_libinput(input)) return;
    struct libinput_device *device=wlr_libinput_get_device_handle(input);
    if (!device) return;
    const struct madway_config *cfg=&server->config;
    int fingers=libinput_device_config_tap_get_finger_count(device);
    bool touchpad=fingers>0 || libinput_device_has_capability(device,LIBINPUT_DEVICE_CAP_GESTURE);
    if (fingers>0) {
        check(libinput_device_config_tap_set_enabled(device,cfg->tap?LIBINPUT_CONFIG_TAP_ENABLED:LIBINPUT_CONFIG_TAP_DISABLED),"tap-to-click",device);
        check(libinput_device_config_tap_set_drag_enabled(device,cfg->tap_drag?LIBINPUT_CONFIG_DRAG_ENABLED:LIBINPUT_CONFIG_DRAG_DISABLED),"tap dragging",device);
        check(libinput_device_config_tap_set_drag_lock_enabled(device,cfg->drag_lock?LIBINPUT_CONFIG_DRAG_LOCK_ENABLED:LIBINPUT_CONFIG_DRAG_LOCK_DISABLED),"drag lock",device);
    }
    if (libinput_device_config_dwt_is_available(device))
        check(libinput_device_config_dwt_set_enabled(device,cfg->dwt?LIBINPUT_CONFIG_DWT_ENABLED:LIBINPUT_CONFIG_DWT_DISABLED),"disable while typing",device);
    if (libinput_device_config_scroll_has_natural_scroll(device))
        check(libinput_device_config_scroll_set_natural_scroll_enabled(device,touchpad?cfg->touchpad_natural:cfg->mouse_natural),"natural scrolling",device);
    if (libinput_device_config_left_handed_is_available(device))
        check(libinput_device_config_left_handed_set(device,cfg->left_handed),"left-handed buttons",device);
    if (libinput_device_config_accel_is_available(device)) {
        check(libinput_device_config_accel_set_speed(device,touchpad?cfg->touchpad_speed:cfg->mouse_speed),"pointer speed",device);
        enum libinput_config_accel_profile profile=libinput_device_config_accel_get_default_profile(device);
        if (!strcmp(cfg->accel_profile,"flat")) profile=LIBINPUT_CONFIG_ACCEL_PROFILE_FLAT;
        else if (!strcmp(cfg->accel_profile,"adaptive")) profile=LIBINPUT_CONFIG_ACCEL_PROFILE_ADAPTIVE;
        if (libinput_device_config_accel_get_profiles(device)&profile)
            check(libinput_device_config_accel_set_profile(device,profile),"acceleration profile",device);
    }
    if (libinput_device_config_middle_emulation_is_available(device))
        check(libinput_device_config_middle_emulation_set_enabled(device,cfg->middle_emulation?LIBINPUT_CONFIG_MIDDLE_EMULATION_ENABLED:LIBINPUT_CONFIG_MIDDLE_EMULATION_DISABLED),"middle button emulation",device);
    if (touchpad) {
        enum libinput_config_click_method method=libinput_device_config_click_get_default_method(device);
        if (!strcmp(cfg->click_method,"clickfinger")) method=LIBINPUT_CONFIG_CLICK_METHOD_CLICKFINGER;
        else if (!strcmp(cfg->click_method,"buttonareas")) method=LIBINPUT_CONFIG_CLICK_METHOD_BUTTON_AREAS;
        if (libinput_device_config_click_get_methods(device)&method)
            check(libinput_device_config_click_set_method(device,method),"touchpad click method",device);
        wlr_log(WLR_INFO,"Touchpad configured: %s; tap-to-click %s",libinput_device_get_name(device),fingers>0?(cfg->tap?"enabled":"disabled"):"unsupported");
    }
}
