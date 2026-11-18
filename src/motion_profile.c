#include "motion_profile.h"
#include "session.h"
#include "animation.h"
#include <glib.h>
#include <math.h>
#include <string.h>

static int integer(GKeyFile *file,const char *key,int fallback,int low,int high)
{
    GError *error=NULL;int value=g_key_file_get_integer(file,"windows",key,&error);
    if(error){g_clear_error(&error);return fallback;}
    return CLAMP(value,low,high);
}

static bool boolean(GKeyFile *file,const char *key,bool fallback)
{
    GError *error=NULL;bool value=g_key_file_get_boolean(file,"windows",key,&error);
    if(error){g_clear_error(&error);return fallback;}return value;
}

static int choice(GKeyFile *file,const char *key,const char *const *names,int count,int fallback)
{
    char *name=g_key_file_get_string(file,"windows",key,NULL);int value=fallback;
    for(int i=0;i<count;++i)if(g_strcmp0(name,names[i])==0){value=i;break;}
    g_free(name);return value;
}

void madway_motion_profile_load(struct madway_config *config,GKeyFile *file)
{
    const char *const open_names[]={"zoom","fade","rise","slide"};
    const char *const max_names[]={"zoom","dissolve","none"};
    const char *const curves[]={"gentle","responsive","spring","linear"};
    char *preset=g_key_file_get_string(file,"windows","open_preset",NULL);
    int style=MADWAY_OPEN_ZOOM,curve=MADWAY_CURVE_GENTLE,ms=320,scale=94,distance=10;
    if(g_strcmp0(preset,"fade")==0){style=MADWAY_OPEN_FADE;curve=MADWAY_CURVE_RESPONSIVE;ms=220;scale=100;distance=0;}
    else if(g_strcmp0(preset,"rise")==0){style=MADWAY_OPEN_RISE;ms=340;scale=100;distance=28;}
    else if(g_strcmp0(preset,"slide")==0){style=MADWAY_OPEN_SLIDE;curve=MADWAY_CURVE_RESPONSIVE;ms=320;scale=100;distance=32;}
    else if(g_strcmp0(preset,"spring")==0){curve=MADWAY_CURVE_SPRING;ms=440;scale=86;distance=0;}
    g_free(preset);
    config->open_animate=boolean(file,"open_animate",config->window_animate);
    config->open_fade=boolean(file,"open_fade",true);
    config->open_style=choice(file,"open_style",open_names,G_N_ELEMENTS(open_names),style);
    config->open_curve=choice(file,"open_curve",curves,G_N_ELEMENTS(curves),curve);
    config->open_animation_ms=integer(file,"open_ms",ms,80,1000);
    config->open_scale=integer(file,"open_scale",scale,50,100);
    config->open_distance=integer(file,"open_distance",distance,0,128);
    preset=g_key_file_get_string(file,"windows","maximize_preset",NULL);
    style=MADWAY_MAXIMIZE_ZOOM;curve=MADWAY_CURVE_GENTLE;ms=preset?360:config->window_animation_ms;
    if(g_strcmp0(preset,"responsive")==0){curve=MADWAY_CURVE_RESPONSIVE;ms=240;}
    else if(g_strcmp0(preset,"spring")==0){curve=MADWAY_CURVE_SPRING;ms=440;}
    else if(g_strcmp0(preset,"dissolve")==0){style=MADWAY_MAXIMIZE_DISSOLVE;curve=MADWAY_CURVE_RESPONSIVE;ms=260;}
    else if(g_strcmp0(preset,"instant")==0){style=MADWAY_MAXIMIZE_NONE;}
    g_free(preset);
    config->maximize_style=choice(file,"maximize_style",max_names,G_N_ELEMENTS(max_names),style);
    config->maximize_curve=choice(file,"maximize_curve",curves,G_N_ELEMENTS(curves),curve);
    config->maximize_animation_ms=integer(file,"maximize_ms",ms,80,1000);
}

double madway_motion_curve_value(enum madway_motion_curve curve,double progress)
{
    if(progress<=0)return 0;
    if(progress>=1)return 1;
    if(curve==MADWAY_CURVE_LINEAR)return progress;
    if(curve==MADWAY_CURVE_SPRING) {
        double value=1-exp(-8*progress)*(cos(7*progress)+(8./7.)*sin(7*progress));
        double end=1-exp(-8)*(cos(7)+(8./7.)*sin(7));
        return value/end;
    }
    if(curve==MADWAY_CURVE_RESPONSIVE) {
        double low=0,high=1;
        for(int i=0;i<24;++i){double t=(low+high)*.5,u=1-t;
            if(3*u*u*t*.2+3*u*t*t*.2+t*t*t<progress)low=t;else high=t;}
        double t=(low+high)*.5,u=1-t;return 3*u*u*t*.8+3*u*t*t+t*t*t;
    }
    return madway_animation_ease(progress);
}

struct wlr_box madway_motion_interpolate(struct wlr_box from,struct wlr_box to,enum madway_motion_curve curve,double progress)
{
    double value=madway_motion_curve_value(curve,progress);
    return (struct wlr_box){from.x+(int)lround((to.x-from.x)*value),from.y+(int)lround((to.y-from.y)*value),
        MAX(1,from.width+(int)lround((to.width-from.width)*value)),MAX(1,from.height+(int)lround((to.height-from.height)*value))};
}

struct wlr_box madway_motion_open_geometry(struct wlr_box target,enum madway_open_style style,int scale,int distance)
{
    struct wlr_box from=target;
    if(style==MADWAY_OPEN_ZOOM){
        from.width=MAX(1,(int)lround(target.width*(CLAMP(scale,50,100)/100.)));
        from.height=MAX(1,(int)lround(target.height*(CLAMP(scale,50,100)/100.)));
        from.x+=(target.width-from.width)/2;from.y+=(target.height-from.height)/2;
    }
    if(style==MADWAY_OPEN_ZOOM || style==MADWAY_OPEN_RISE)from.y+=CLAMP(distance,0,128);
    else if(style==MADWAY_OPEN_SLIDE)from.x-=CLAMP(distance,0,128);
    return from;
}
