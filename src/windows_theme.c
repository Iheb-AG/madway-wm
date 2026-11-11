#include "windows_theme.h"
#include "main.h"
#include "view.h"
#include <pango/pangocairo.h>
#include <math.h>

int madway_windows_button_width(int height) { return height<18?14:height+1; }

void madway_windows_title(cairo_t *cr,struct madway_view *view,int width,int height)
{
    struct madway_config *config=&view->server->config;
    bool xp=config->windows_style==1,active=view->server->focused_view==view;
    cairo_pattern_t *paint=cairo_pattern_create_linear(0,0,0,height);
    if (xp) {
        cairo_pattern_add_color_stop_rgb(paint,0,active?.32:.55,active?.59:.65,active?1:.81);
        cairo_pattern_add_color_stop_rgb(paint,.18,active?.08:.42,active?.36:.55,active?.93:.73);
        cairo_pattern_add_color_stop_rgb(paint,.85,active?.03:.42,active?.26:.55,active?.78:.73);
        cairo_pattern_add_color_stop_rgb(paint,1,.06,.20,.61);
    } else {
        cairo_pattern_add_color_stop_rgb(paint,0,.36,.48,.57);
        cairo_pattern_add_color_stop_rgb(paint,.48,.19,.31,.40);
        cairo_pattern_add_color_stop_rgb(paint,.5,.08,.18,.26);
        cairo_pattern_add_color_stop_rgb(paint,1,active?.12:.21,active?.25:.30,active?.34:.37);
    }
    cairo_set_source(cr,paint);cairo_paint(cr);cairo_pattern_destroy(paint);
    int button=madway_windows_button_width(height);
    for (int index=0;index<3;++index) {
        double x=width-(3-index)*button+1,y=2,h=fmax(8,height-4);
        bool close=index==2;
        cairo_pattern_t *fill=cairo_pattern_create_linear(0,y,0,y+h);
        if (close) {cairo_pattern_add_color_stop_rgb(fill,0,.98,.48,.35);cairo_pattern_add_color_stop_rgb(fill,.5,.77,.18,.10);cairo_pattern_add_color_stop_rgb(fill,1,.62,.12,.06);}
        else {cairo_pattern_add_color_stop_rgba(fill,0,.72,.85,1,.65);cairo_pattern_add_color_stop_rgba(fill,1,.15,.38,.74,.65);}
        cairo_set_source(cr,fill);cairo_rectangle(cr,x,y,button-3,h);cairo_fill(cr);cairo_pattern_destroy(fill);
        cairo_set_source_rgba(cr,1,1,1,.4);cairo_set_line_width(cr,1);cairo_rectangle(cr,x+.5,y+.5,button-4,h-1);cairo_stroke(cr);
        double cx=x+(button-3)/2.,cy=y+h/2.,s=fmin(4,h/3.);
        cairo_set_source_rgb(cr,1,1,1);cairo_set_line_width(cr,1.4);
        if (index==0) {cairo_move_to(cr,cx-s,cy+s/2);cairo_line_to(cr,cx+s,cy+s/2);}
        else if (index==1) {cairo_rectangle(cr,cx-s,cy-s,2*s,2*s);}
        else {cairo_move_to(cr,cx-s,cy-s);cairo_line_to(cr,cx+s,cy+s);cairo_move_to(cr,cx+s,cy-s);cairo_line_to(cr,cx-s,cy+s);}
        cairo_stroke(cr);
    }
    PangoLayout *layout=pango_cairo_create_layout(cr);
    PangoFontDescription *font=pango_font_description_from_string(config->font[0]?config->font:xp?"Tahoma Bold":"Sans");
    int size=config->title_font_size?config->title_font_size:11;
    pango_font_description_set_absolute_size(font,fmin(size,height-3)*PANGO_SCALE);
    pango_layout_set_font_description(layout,font);pango_layout_set_single_paragraph_mode(layout,true);
    pango_layout_set_ellipsize(layout,PANGO_ELLIPSIZE_END);pango_layout_set_width(layout,(int)fmax(1,width-3*button-10)*PANGO_SCALE);
    pango_layout_set_text(layout,view->toplevel->title?view->toplevel->title:"madway",-1);
    int th;pango_layout_get_pixel_size(layout,NULL,&th);
    cairo_set_source_rgba(cr,0,0,0,.35);cairo_move_to(cr,6,(height-th)/2.+1);pango_cairo_show_layout(cr,layout);
    cairo_set_source_rgba(cr,1,1,1,active?1:.78);cairo_move_to(cr,5,(height-th)/2.);pango_cairo_show_layout(cr,layout);
    pango_font_description_free(font);g_object_unref(layout);
}
