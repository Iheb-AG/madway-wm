#include "motion_profile.h"
#include "session.h"
#include <assert.h>
#include <glib.h>
#include <math.h>
#include <stdio.h>

int main(int argc,char **argv)
{
    GKeyFile *file=g_key_file_new();struct madway_config config={.window_animate=true,.window_animation_ms=360};
    if(argc>1){
        assert(g_key_file_load_from_file(file,argv[1],G_KEY_FILE_NONE,NULL));madway_motion_profile_load(&config,file);
        printf("{\"open_animate\":%s,\"open_style\":%d,\"open_curve\":%d,\"open_ms\":%d,\"open_scale\":%d,\"open_distance\":%d,\"open_fade\":%s,\"maximize_style\":%d,\"maximize_curve\":%d,\"maximize_ms\":%d}\n",
            config.open_animate?"true":"false",config.open_style,config.open_curve,config.open_animation_ms,config.open_scale,config.open_distance,config.open_fade?"true":"false",config.maximize_style,config.maximize_curve,config.maximize_animation_ms);
        g_key_file_unref(file);return 0;
    }
    config.window_animate=false;config.window_animation_ms=420;madway_motion_profile_load(&config,file);
    assert(!config.open_animate && config.open_animation_ms==320 && config.maximize_animation_ms==420);
    g_key_file_set_string(file,"windows","open_preset","spring");g_key_file_set_integer(file,"windows","open_scale",1000);
    g_key_file_set_integer(file,"windows","open_ms",2000);g_key_file_set_string(file,"windows","maximize_preset","dissolve");
    madway_motion_profile_load(&config,file);
    assert(config.open_curve==MADWAY_CURVE_SPRING && config.open_scale==100 && config.open_animation_ms==1000);
    assert(config.maximize_style==MADWAY_MAXIMIZE_DISSOLVE && config.maximize_animation_ms==260);
    g_key_file_set_string(file,"windows","open_ms","invalid");madway_motion_profile_load(&config,file);assert(config.open_animation_ms==440);
    struct wlr_box target={100,200,640,480};
    struct wlr_box box=madway_motion_open_geometry(target,MADWAY_OPEN_ZOOM,90,10);
    assert(box.x==132 && box.y==234 && box.width==576 && box.height==432);
    box=madway_motion_open_geometry(target,MADWAY_OPEN_FADE,50,128);assert(wlr_box_equal(&target,&box));
    box=madway_motion_open_geometry(target,MADWAY_OPEN_RISE,50,28);assert(box.y==228 && box.width==640);
    box=madway_motion_open_geometry(target,MADWAY_OPEN_SLIDE,50,32);assert(box.x==68 && box.height==480);
    double peak=1;
    for(int curve=MADWAY_CURVE_GENTLE;curve<=MADWAY_CURVE_LINEAR;++curve){
        assert(madway_motion_curve_value(curve,0)==0 && madway_motion_curve_value(curve,1)==1);
        double previous=0;
        for(int i=0;i<=1000;++i){
            double value=madway_motion_curve_value(curve,i/1000.);
            assert(isfinite(value) && value>=0 && value<1.04);
            if(curve!=MADWAY_CURVE_SPRING)assert(value>=previous && value<=1);
            else if(value>peak)peak=value;
            previous=value;
            box=madway_motion_interpolate((struct wlr_box){0,0,1,1},target,curve,i/1000.);
            assert(box.width>0 && box.height>0);
        }
        box=madway_motion_interpolate((struct wlr_box){0,0,1,1},target,curve,1);assert(wlr_box_equal(&target,&box));
    }
    assert(peak>1.01 && peak<1.04);assert(madway_motion_curve_value(MADWAY_CURVE_RESPONSIVE,.1)>.3);
    assert(madway_motion_curve_value(MADWAY_CURVE_LINEAR,.3)==.3);
    g_key_file_unref(file);puts("PASS: native profile defaults, limits, invalid values, distinct geometry, bounded spring, monotonic easing and exact endpoints.");
}
