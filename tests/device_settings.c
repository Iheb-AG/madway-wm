/* Capability-driven libinput configuration: fake devices, no /dev/input access. */
#include "main.h"
#include "devices.h"
#include <assert.h>
#include <string.h>
#include <wlr/backend/libinput.h>
static bool native=true,available=true;
static int fingers=3,calls,tap,drag,lock_drag,dwt,natural,left,middle,profile,click,tap_calls;
static double speed;
bool wlr_input_device_is_libinput(struct wlr_input_device *d){(void)d;return native;}
struct libinput_device *wlr_libinput_get_device_handle(struct wlr_input_device *d){(void)d;return (struct libinput_device *)1;}
const char *libinput_device_get_name(struct libinput_device *d){(void)d;return "private fake touchpad";}
int libinput_device_has_capability(struct libinput_device *d,enum libinput_device_capability cap){(void)d;(void)cap;return available && fingers>0;}
#define GET(name,type,value) type name(struct libinput_device *d){(void)d;return (value);}
#define SET(name,type,result) enum libinput_config_status name(struct libinput_device *d,type value){(void)d;++calls;result=value;return LIBINPUT_CONFIG_STATUS_SUCCESS;}
GET(libinput_device_config_tap_get_finger_count,int,available?fingers:0)
enum libinput_config_status libinput_device_config_tap_set_enabled(struct libinput_device *d,enum libinput_config_tap_state value){(void)d;++calls;++tap_calls;tap=value;return LIBINPUT_CONFIG_STATUS_SUCCESS;}
SET(libinput_device_config_tap_set_drag_enabled,enum libinput_config_drag_state,drag)
SET(libinput_device_config_tap_set_drag_lock_enabled,enum libinput_config_drag_lock_state,lock_drag)
GET(libinput_device_config_dwt_is_available,int,available && fingers>0)
SET(libinput_device_config_dwt_set_enabled,enum libinput_config_dwt_state,dwt)
GET(libinput_device_config_scroll_has_natural_scroll,int,available)
SET(libinput_device_config_scroll_set_natural_scroll_enabled,int,natural)
GET(libinput_device_config_left_handed_is_available,int,available)
SET(libinput_device_config_left_handed_set,int,left)
GET(libinput_device_config_accel_is_available,int,available)
SET(libinput_device_config_accel_set_speed,double,speed)
GET(libinput_device_config_accel_get_default_profile,enum libinput_config_accel_profile,LIBINPUT_CONFIG_ACCEL_PROFILE_ADAPTIVE)
GET(libinput_device_config_accel_get_profiles,uint32_t,LIBINPUT_CONFIG_ACCEL_PROFILE_ADAPTIVE|LIBINPUT_CONFIG_ACCEL_PROFILE_FLAT)
SET(libinput_device_config_accel_set_profile,enum libinput_config_accel_profile,profile)
GET(libinput_device_config_middle_emulation_is_available,int,available)
SET(libinput_device_config_middle_emulation_set_enabled,enum libinput_config_middle_emulation_state,middle)
GET(libinput_device_config_click_get_default_method,enum libinput_config_click_method,LIBINPUT_CONFIG_CLICK_METHOD_BUTTON_AREAS)
GET(libinput_device_config_click_get_methods,uint32_t,LIBINPUT_CONFIG_CLICK_METHOD_BUTTON_AREAS|LIBINPUT_CONFIG_CLICK_METHOD_CLICKFINGER)
SET(libinput_device_config_click_set_method,enum libinput_config_click_method,click)
int main(void)
{
    struct madway_server server={0};struct wlr_input_device input={0};
    server.config.tap=true;server.config.tap_drag=true;server.config.dwt=true;
    server.config.touchpad_natural=true;server.config.touchpad_speed=.35;server.config.left_handed=true;
    strcpy(server.config.accel_profile,"adaptive");strcpy(server.config.click_method,"clickfinger");
    native=false;madway_configure_pointer(&server,&input);assert(calls==0);
    native=true;madway_configure_pointer(&server,&input);
    assert(tap==LIBINPUT_CONFIG_TAP_ENABLED && drag==LIBINPUT_CONFIG_DRAG_ENABLED && !lock_drag);
    assert(dwt==LIBINPUT_CONFIG_DWT_ENABLED && natural && left && speed==.35);
    assert(profile==LIBINPUT_CONFIG_ACCEL_PROFILE_ADAPTIVE && click==LIBINPUT_CONFIG_CLICK_METHOD_CLICKFINGER);
    server.config.tap=false;server.config.dwt=false;server.config.touchpad_natural=false;
    server.config.touchpad_speed=-.25;madway_configure_pointer(&server,&input);
    assert(tap==LIBINPUT_CONFIG_TAP_DISABLED && dwt==LIBINPUT_CONFIG_DWT_DISABLED && !natural && speed==-.25);
    int previous_taps=tap_calls;fingers=0;server.config.mouse_speed=-.4;server.config.mouse_natural=true;
    server.config.middle_emulation=true;server.config.left_handed=false;strcpy(server.config.accel_profile,"flat");
    madway_configure_pointer(&server,&input);
    assert(tap_calls==previous_taps && speed==-.4 && natural && !left && middle==LIBINPUT_CONFIG_MIDDLE_EMULATION_ENABLED);
    assert(profile==LIBINPUT_CONFIG_ACCEL_PROFILE_FLAT);
    int before=calls;available=false;madway_configure_pointer(&server,&input);assert(calls==before);
    return 0;
}
