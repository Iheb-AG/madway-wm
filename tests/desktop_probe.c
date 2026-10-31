/* Test-only virtual input devices. Never injects input into the host desktop. */
#define _GNU_SOURCE
#include "main.h"
#include "view.h"
#include "layer.h"
#include "workspace.h"
#include "decoration.h"
#include "input.h"
#include <unistd.h>
#include <assert.h>
#include <dlfcn.h>
#include <linux/input-event-codes.h>
#include <stdio.h>
#include <spawn.h>
#include <stdlib.h>
#include <string.h>
#include <wlr/interfaces/wlr_keyboard.h>
#include <wlr/interfaces/wlr_pointer.h>
#include <wlr/backend/multi.h>
#include <wlr/backend/headless.h>

static struct madway_server *server;
static struct wlr_keyboard keyboard;
static struct wlr_pointer pointer;
static bool keyboard_live, pointer_live;
static struct wl_listener backend_destroy;
static struct wl_event_source *timer;
static int stage, ticks;
static struct wlr_backend *headless;
static struct wlr_output *hotplug_output;
static struct madway_view *previous_view;
static pid_t previous_menu_pid;
static struct madway_view *feature_views[3];
static unsigned feature_origin;
static unsigned panel_edges_seen;
static int resize_width, resize_height;
static void find_headless(struct wlr_backend *backend, void *data)
{
    (void)data;
    if (wlr_backend_is_headless(backend)) headless = backend;
}
static uint32_t timestamp = 100;
static const struct wlr_keyboard_impl keyboard_impl = {.name = "madway-test-keyboard"};
static const struct wlr_pointer_impl pointer_impl = {.name = "madway-test-pointer"};

/* Keep test instrumentation (including libasan) out of external desktop apps. */
int posix_spawnp(pid_t *pid, const char *file,
        const posix_spawn_file_actions_t *actions, const posix_spawnattr_t *attributes,
        char *const arguments[], char *const environment[])
{
    typedef int (*spawn_fn)(pid_t *, const char *, const posix_spawn_file_actions_t *,
            const posix_spawnattr_t *, char *const [], char *const []);
    spawn_fn spawn = (spawn_fn)dlsym(RTLD_NEXT, "posix_spawnp");
    size_t count = 0;
    while (environment[count] != NULL) ++count;
    char **clean = calloc(count + 1, sizeof(*clean));
    assert(clean != NULL);
    size_t index = 0;
    for (size_t i = 0; i < count; ++i)
        if (strncmp(environment[i], "LD_PRELOAD=", 11) != 0) clean[index++] = environment[i];
    int result = spawn(pid, file, actions, attributes, arguments, clean);
    free(clean);
    return result;
}

static void key(uint32_t code, enum wl_keyboard_key_state state)
{
    struct wlr_keyboard_key_event event = {
        .time_msec = timestamp++, .keycode = code, .state = state, .update_state = true,
    };
    wlr_keyboard_notify_key(&keyboard, &event);
}

static void feature_shortcut(uint32_t code) {
    key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);
    key(code,WL_KEYBOARD_KEY_STATE_PRESSED);key(code,WL_KEYBOARD_KEY_STATE_RELEASED);
    key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);
}
static void feature_focus(struct madway_view *target) {
    for(int i=0;i<8 && server->focused_view!=target;++i)feature_shortcut(KEY_TAB);
    assert(server->focused_view==target);
}
static void feature_motion(double x,double y) {
    struct wlr_box bounds;wlr_output_layout_get_box(server->output_layout,NULL,&bounds);
    struct wlr_pointer_motion_absolute_event motion={.pointer=&pointer,.time_msec=timestamp++,
        .x=(x-bounds.x)/bounds.width,.y=(y-bounds.y)/bounds.height};
    wl_signal_emit_mutable(&pointer.events.motion_absolute,&motion);
}
static void feature_button(uint32_t button,bool pressed) {
    struct wlr_pointer_button_event event={.pointer=&pointer,.time_msec=timestamp++,.button=button,
        .state=pressed?WL_POINTER_BUTTON_STATE_PRESSED:WL_POINTER_BUTTON_STATE_RELEASED};
    wlr_pointer_notify_button(&pointer,&event);
}
static const uint32_t letters[26]={KEY_A,KEY_B,KEY_C,KEY_D,KEY_E,KEY_F,KEY_G,KEY_H,KEY_I,KEY_J,KEY_K,KEY_L,KEY_M,KEY_N,KEY_O,KEY_P,KEY_Q,KEY_R,KEY_S,KEY_T,KEY_U,KEY_V,KEY_W,KEY_X,KEY_Y,KEY_Z};
static const char *typing=NULL;
static int typing_index,typing_delay;
static void shortcut(uint32_t code,bool shift) {
    key(KEY_LEFTALT,WL_KEYBOARD_KEY_STATE_PRESSED);
    if(shift)key(KEY_LEFTSHIFT,WL_KEYBOARD_KEY_STATE_PRESSED);
    key(code,WL_KEYBOARD_KEY_STATE_PRESSED);key(code,WL_KEYBOARD_KEY_STATE_RELEASED);
    if(shift)key(KEY_LEFTSHIFT,WL_KEYBOARD_KEY_STATE_RELEASED);
    key(KEY_LEFTALT,WL_KEYBOARD_KEY_STATE_RELEASED);
}
static bool type_step(void) {
    char ch=typing[typing_index];
    if(ch) {
        uint32_t code=(ch>='a'&&ch<='z')?letters[ch-'a']:ch=='-'?KEY_MINUS:KEY_SPACE;
        key(code,WL_KEYBOARD_KEY_STATE_PRESSED);key(code,WL_KEYBOARD_KEY_STATE_RELEASED);++typing_index;return false;
    }
    if(++typing_delay<10)return false;
    key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_RELEASED);return true;
}
static int run_stage(void *data) {
    (void)data;assert(++ticks<1200);
    if(stage==0) {
        const char *ready=getenv("MADWAY_LAUNCH_TEST_READY");
        if(ready&&access(ready,F_OK)==0) {shortcut(KEY_D,true);stage=1;}
    } else if(stage==1 && server->keyboard_layer!=NULL) {
        assert(!strcmp(server->keyboard_layer->surface->namespace,"wofi"));
        assert(server->seat->keyboard_state.focused_surface==server->keyboard_layer->surface->surface);
        typing="madway-fixture";typing_index=typing_delay=0;stage=2;
    } else if(stage==2) {
        if(type_step())stage=3;
    } else if(stage==3 && server->keyboard_layer==NULL) {
        fprintf(stderr,"RUN LAUNCHER PASS\n");shortcut(KEY_D,false);stage=4;
    } else if(stage==4 && server->keyboard_layer!=NULL) {
        typing="madway fixture";typing_index=typing_delay=0;stage=5;
    } else if(stage==5) {
        if(type_step())stage=6;
    } else if(stage==6 && server->keyboard_layer==NULL) {
        fprintf(stderr,"APP LAUNCHER PASS\n");shortcut(KEY_COMMA,false);stage=7;
    } else if(stage==7) {
        struct madway_view *view;
        wl_list_for_each(view,&server->views,link)
            if(view->mapped && view->toplevel->app_id && !strcmp(view->toplevel->app_id,"org.madway.Settings")) {
                assert(view->floating && view->compact_frame && view->decorated);
                assert(view->frame_title_height > 0 && view->frame_title_height <= 16);
                key(KEY_VOLUMEUP,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_VOLUMEUP,WL_KEYBOARD_KEY_STATE_RELEASED);
                key(KEY_BRIGHTNESSUP,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_BRIGHTNESSUP,WL_KEYBOARD_KEY_STATE_RELEASED);
                key(KEY_SYSRQ,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_SYSRQ,WL_KEYBOARD_KEY_STATE_RELEASED);
                fprintf(stderr,"SETTINGS WINDOW AND MEDIA KEYS PASS\n");stage=8;break;
            }
    } else if(stage==8 && server->config.tile_gap==4 && server->config.title_height==16) {
        fprintf(stderr,"LIVE SETTINGS RELOAD PASS\n");
        assert(server->keyboard_layer==NULL);
        assert(server->focused_view!=NULL);
        assert(server->seat->keyboard_state.focused_surface==server->focused_view->toplevel->base->surface);
        shortcut(KEY_D,false);stage=9;
    } else if(stage==9 && server->keyboard_layer!=NULL) {
        assert(server->seat->keyboard_state.focused_surface==server->keyboard_layer->surface->surface);
        key(KEY_ESC,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_ESC,WL_KEYBOARD_KEY_STATE_RELEASED);
        stage=10;
    } else if(stage==10 && server->keyboard_layer==NULL) {
        assert(server->focused_view!=NULL);
        assert(server->seat->keyboard_state.focused_surface==server->focused_view->toplevel->base->surface);
        fprintf(stderr,"OVERLAY FOCUS RESTORED PASS\n");
        shortcut(KEY_ENTER,false);stage=11;
    } else if(stage==11 && server->focused_view!=NULL && server->focused_view->toplevel->title!=NULL &&
            !strcmp(server->focused_view->toplevel->title,"floating-fixture")) {
        assert(server->focused_view->floating);
        shortcut(KEY_T,false);assert(!server->focused_view->floating);
        shortcut(KEY_SPACE,false);assert(server->focused_view->floating);
        shortcut(KEY_M,false);assert(server->focused_view->maximized);
        shortcut(KEY_T,false);assert(server->focused_view->floating && !server->focused_view->maximized);
        shortcut(KEY_F,false);assert(server->focused_view->fullscreen);
        shortcut(KEY_T,false);assert(server->focused_view->floating && !server->focused_view->fullscreen);
        fprintf(stderr,"FLOATING DEFAULT AND SHORTCUTS PASS\n");stage=12;
    } else if(stage==12 && server->config.use_super) {
        assert(keyboard.repeat_info.rate==40 && keyboard.repeat_info.delay==250);
        struct madway_view *view=server->focused_view;
        assert(view!=NULL && view->floating);
        shortcut(KEY_T,false);assert(view->floating); // Old modifier is no longer consumed.
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);
        key(KEY_T,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_T,WL_KEYBOARD_KEY_STATE_RELEASED);
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);
        assert(!view->floating);
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);
        key(KEY_T,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_T,WL_KEYBOARD_KEY_STATE_RELEASED);
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);
        assert(view->floating);
        fprintf(stderr,"LIVE INPUT SETTINGS PASS\n");stage=13;
    } else if(stage==13 && getenv("MADWAY_TEST_HOTPLUG")!=NULL && access(getenv("MADWAY_TEST_HOTPLUG"),F_OK)==0) {
        wlr_multi_for_each_backend(server->backend,find_headless,NULL);
        assert(headless!=NULL);
        hotplug_output=wlr_headless_add_output(headless,800,600);
        assert(hotplug_output!=NULL);
        struct madway_output *output;
        wl_list_for_each(output,&server->outputs,link)
            if(output->output==hotplug_output) {
                server->focused_view->output=output;
                wlr_scene_node_set_position(&server->focused_view->scene_tree->node,output->layout_x+16,output->layout_y+16);
            }
        stage=14;
    } else if(stage==14 && access(getenv("MADWAY_TEST_HOTPLUG"),F_OK)!=0) {
        wlr_output_destroy(hotplug_output);
        assert(server->focused_view!=NULL && server->focused_view->output!=NULL);
        assert(server->focused_view->output->output->enabled);
        assert(wlr_output_layout_output_at(server->output_layout,
                server->focused_view->scene_tree->node.x+16,server->focused_view->scene_tree->node.y+8)!=NULL);
        fprintf(stderr,"OUTPUT HOTPLUG AND WINDOW RECOVERY PASS\n");stage=15;
    } else if(stage==15 && !server->config.default_floating && server->config.master_percent==60 &&
            server->focused_view!=NULL && server->focused_view->toplevel->title!=NULL &&
            !strcmp(server->focused_view->toplevel->title,"floating-fixture")) {
        previous_view=server->focused_view;
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);
        key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_RELEASED);
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);stage=16;
    } else if(stage==16 && server->focused_view!=NULL && server->focused_view!=previous_view) {
        assert(!server->focused_view->floating);
        fprintf(stderr,"NEW WINDOW POLICY SETTINGS PASS\n");
        struct madway_output *output=wl_container_of(server->outputs.prev,output,link);
        struct wlr_box bounds;
        wlr_output_layout_get_box(server->output_layout,NULL,&bounds);
        struct wlr_pointer_motion_absolute_event motion={.pointer=&pointer,.time_msec=100,
            .x=(output->layout_x+output->usable_area.width-10.0-bounds.x)/bounds.width,
            .y=(output->layout_y+output->usable_area.height-10.0-bounds.y)/bounds.height};
        wl_signal_emit_mutable(&pointer.events.motion_absolute,&motion);
        for(int pressed=1;pressed>=0;--pressed) {
            struct wlr_pointer_button_event button={.pointer=&pointer,.time_msec=100,.button=BTN_RIGHT,
                .state=pressed?WL_POINTER_BUTTON_STATE_PRESSED:WL_POINTER_BUTTON_STATE_RELEASED};
            wlr_pointer_notify_button(&pointer,&button);
        }
        stage=17;
    } else if(stage==17 && server->keyboard_layer!=NULL &&
            !strcmp(server->keyboard_layer->surface->namespace,"madway-menu")) {
        assert(server->keyboard_layer->surface->current.exclusive_zone==-1);
        for(int i=0;i<4;++i) {key(KEY_DOWN,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_DOWN,WL_KEYBOARD_KEY_STATE_RELEASED);}
        key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_RELEASED);
        stage=18;
    } else if(stage==18) {
        key(KEY_DOWN,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_DOWN,WL_KEYBOARD_KEY_STATE_RELEASED);
        key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_RELEASED);stage=19;
    } else if(stage==19 && server->keyboard_layer==NULL && server->focused_view!=NULL && server->focused_view->floating) {
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);
        key(KEY_F,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_F,WL_KEYBOARD_KEY_STATE_RELEASED);
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);
        assert(server->focused_view->fullscreen);
        struct madway_layer *layer;
        wl_list_for_each(layer,&server->layers,link)
            if(!strcmp(layer->surface->namespace,"madway-panel") && layer->surface->output==server->focused_view->output->output)
                assert(!layer->tree->node.enabled);
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);
        key(KEY_F,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_F,WL_KEYBOARD_KEY_STATE_RELEASED);
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);
        fprintf(stderr,"DESKTOP MENU ACTION AND FULLSCREEN PANEL PASS\n");stage=20;
    } else if(stage==20) {
        bool panels=false;struct madway_layer *layer;
        wl_list_for_each(layer,&server->layers,link)
            if(layer->mapped && !strcmp(layer->surface->namespace,"madway-panel"))panels=true;
        if(!panels) {
            struct madway_output *output;
            wl_list_for_each(output,&server->outputs,link) {
                int w,h;wlr_output_effective_resolution(output->output,&w,&h);
                assert(output->usable_area.height==h);
            }
            fprintf(stderr,"PANEL TOGGLE OFF PASS\n");stage=21;
        }
    } else if(stage==21) {
        unsigned panels=0;struct madway_layer *layer;
        wl_list_for_each(layer,&server->layers,link)
            if(layer->mapped && !strcmp(layer->surface->namespace,"madway-panel") && layer->surface->current.exclusive_zone==22)++panels;
        if(panels==(unsigned)wl_list_length(&server->outputs)) {
            struct madway_output *output;
            wl_list_for_each(output,&server->outputs,link) {
                int w,h;wlr_output_effective_resolution(output->output,&w,&h);
                assert(output->usable_area.height==h-22);
            }
            fprintf(stderr,"PANEL HEIGHT RELOAD PASS\n");stage=22;
        }
    } else if((stage==22 || stage==23) && getenv("MADWAY_TEST_MENU_READY") != NULL &&
            access(getenv("MADWAY_TEST_MENU_READY"),F_OK)==0 && server->keyboard_layer!=NULL &&
            !strcmp(server->keyboard_layer->surface->namespace,"madway-menu")) {
        pid_t pid;
        wl_client_get_credentials(wl_resource_get_client(server->keyboard_layer->surface->resource),&pid,NULL,NULL);
        if(stage==22 || pid!=previous_menu_pid) {
            previous_menu_pid=pid;
            key(KEY_ESC,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_ESC,WL_KEYBOARD_KEY_STATE_RELEASED);
            fprintf(stderr,stage==22?"AUDIO DROPDOWN IPC PASS\n":"CLOCK DROPDOWN IPC PASS\n");++stage;
        }
    } else if(stage==24 && getenv("MADWAY_TEST_FEATURES_READY") != NULL &&
            access(getenv("MADWAY_TEST_FEATURES_READY"),F_OK)==0) {
        previous_view=server->focused_view;
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);
        key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_ENTER,WL_KEYBOARD_KEY_STATE_RELEASED);
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);stage=25;
    } else if(stage==25 && server->focused_view!=NULL && server->focused_view!=previous_view) {
        unsigned count=0;struct madway_view *entry;
        struct madway_output *output=server->focused_view->output;
        wl_list_for_each(entry,&server->layout_views,layout_link)
            if(entry->mapped && !entry->compact_frame && entry->workspace==server->active_workspace && count<3) {
                entry->floating=false;entry->maximized=false;entry->fullscreen=false;entry->output=output;
                feature_views[count++]=entry;
            }
        wl_list_for_each(entry,&server->layout_views,layout_link)
            if(entry->compact_frame)wlr_scene_node_set_position(&entry->scene_tree->node,-10000,-10000);
        assert(count==3);feature_shortcut(KEY_M);feature_shortcut(KEY_M);
        feature_focus(feature_views[2]);
        key(KEY_LEFTCTRL,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_LEFTSHIFT,WL_KEYBOARD_KEY_STATE_PRESSED);
        key(KEY_LEFT,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_LEFT,WL_KEYBOARD_KEY_STATE_RELEASED);
        assert(server->focused_view==feature_views[2]);
        assert(feature_views[2]->scene_tree->node.x==output->usable_area.x);
        key(KEY_RIGHT,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_RIGHT,WL_KEYBOARD_KEY_STATE_RELEASED);
        assert(feature_views[2]->scene_tree->node.x>output->usable_area.x);
        int top=feature_views[2]->scene_tree->node.y;
        key(KEY_DOWN,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_DOWN,WL_KEYBOARD_KEY_STATE_RELEASED);
        assert(feature_views[2]->scene_tree->node.y>top);
        key(KEY_UP,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_UP,WL_KEYBOARD_KEY_STATE_RELEASED);
        assert(feature_views[2]->scene_tree->node.y==top);
        key(KEY_LEFTSHIFT,WL_KEYBOARD_KEY_STATE_RELEASED);key(KEY_LEFTCTRL,WL_KEYBOARD_KEY_STATE_RELEASED);
        fprintf(stderr,"DIRECTIONAL TILE SHORTCUTS PASS\n");
        for(unsigned i=0;i<3;++i) {
            feature_views[i]->floating=true;
            wlr_scene_node_set_position(&feature_views[i]->scene_tree->node,output->layout_x+20+(int)i*300,output->layout_y+60);
            wlr_xdg_toplevel_set_size(feature_views[i]->toplevel,240,180);
            feature_views[i]->frame_visible=false;
        }
        feature_focus(feature_views[0]);stage=26;
    } else if(stage==26 && feature_views[0]->toplevel->base->geometry.width==240 &&
            feature_views[1]->toplevel->base->geometry.width==240 && feature_views[2]->toplevel->base->geometry.width==240) {
        assert(server->config.focus_follows_mouse);
        struct madway_output *output=feature_views[1]->output;
        struct wlr_box bounds;wlr_output_layout_get_box(server->output_layout,NULL,&bounds);
        struct wlr_pointer_motion_absolute_event motion={.pointer=&pointer,.time_msec=110,
            .x=(output->layout_x+370.0-bounds.x)/bounds.width,.y=(output->layout_y+110.0-bounds.y)/bounds.height};
        wl_signal_emit_mutable(&pointer.events.motion_absolute,&motion);
        assert(server->focused_view==feature_views[1]);
        feature_focus(feature_views[0]);
        assert(server->focused_view==feature_views[0]);
        server->config.focus_follows_mouse=false;
        wl_signal_emit_mutable(&pointer.events.motion_absolute,&motion);
        assert(server->focused_view==feature_views[0]);server->config.focus_follows_mouse=true;
        fprintf(stderr,"OPTIONAL POINTER FOCUS AND REBASE GUARD PASS\n");
        feature_origin=server->focused_view->id;
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);
        key(KEY_TAB,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_TAB,WL_KEYBOARD_KEY_STATE_RELEASED);
        assert(server->switcher_active && server->focused_view->id!=feature_origin);stage=27;
    } else if(stage==27) {
        bool visible=false;struct madway_layer *layer;
        wl_list_for_each(layer,&server->layers,link)
            if(layer->mapped && !strcmp(layer->surface->namespace,"madway-switcher")) {
                assert(layer->surface->current.keyboard_interactive==ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_NONE);
                visible=true;
            }
        if(visible) {
            key(KEY_LEFTSHIFT,WL_KEYBOARD_KEY_STATE_PRESSED);
            key(KEY_TAB,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_TAB,WL_KEYBOARD_KEY_STATE_RELEASED);
            key(KEY_LEFTSHIFT,WL_KEYBOARD_KEY_STATE_RELEASED);
            assert(server->focused_view->id==feature_origin);
            key(KEY_ESC,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_ESC,WL_KEYBOARD_KEY_STATE_RELEASED);
            assert(!server->switcher_active && server->focused_view->id==feature_origin);
            key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);stage=28;
        }
    } else if(stage==28) {
        bool visible=false;struct madway_layer *layer;
        wl_list_for_each(layer,&server->layers,link)
            if(layer->mapped && !strcmp(layer->surface->namespace,"madway-switcher"))visible=true;
        if(!visible) {
            key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);
            key(KEY_TAB,WL_KEYBOARD_KEY_STATE_PRESSED);key(KEY_TAB,WL_KEYBOARD_KEY_STATE_RELEASED);stage=29;
        }
    } else if(stage==29) {
        bool visible=false;struct madway_layer *layer;
        wl_list_for_each(layer,&server->layers,link)
            if(layer->mapped && !strcmp(layer->surface->namespace,"madway-switcher"))visible=true;
        if(visible) {
            unsigned selected=server->focused_view->id;
            key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);
            assert(!server->switcher_active && server->focused_view->id==selected);
            fprintf(stderr,"VISIBLE SWITCHER CYCLE CANCEL AND COMMIT PASS\n");stage=30;
        }
    } else if(stage==30) {
        feature_focus(feature_views[0]);feature_shortcut(KEY_A);
        assert(feature_views[0]->keep_above && feature_views[0]->scene_tree->node.parent==server->above_windows);
        feature_focus(feature_views[1]);
        struct madway_output *output=feature_views[0]->output;
        for(unsigned i=0;i<2;++i)wlr_scene_node_set_position(&feature_views[i]->scene_tree->node,output->layout_x+40,output->layout_y+60);
        server->config.focus_follows_mouse=false;
        feature_motion(output->layout_x+100,output->layout_y+110);
        feature_button(BTN_LEFT,true);feature_button(BTN_LEFT,false);
        assert(server->focused_view==feature_views[0]);
        feature_focus(feature_views[1]);feature_shortcut(KEY_F);
        assert(feature_views[1]->fullscreen && feature_views[0]->scene_tree->node.enabled);
        feature_motion(output->layout_x+100,output->layout_y+110);
        feature_button(BTN_LEFT,true);feature_button(BTN_LEFT,false);
        assert(server->focused_view==feature_views[0] && feature_views[1]->fullscreen);
        feature_focus(feature_views[2]);
        assert(!feature_views[1]->fullscreen && feature_views[2]->scene_tree->node.enabled);
        feature_shortcut(KEY_2);assert(!feature_views[0]->scene_tree->node.enabled);
        feature_shortcut(KEY_1);feature_focus(feature_views[0]);
        assert(feature_views[0]->scene_tree->node.enabled && feature_views[0]->keep_above);
        feature_shortcut(KEY_A);assert(!feature_views[0]->keep_above && feature_views[0]->scene_tree->node.parent==server->windows);
        fprintf(stderr,"KEEP ABOVE STACKING INPUT FULLSCREEN AND WORKSPACE PASS\n");
        struct madway_view *entry;unsigned count=0;
        wl_list_for_each(entry,&server->layout_views,layout_link)
            if(entry->mapped && !entry->compact_frame && entry->workspace==server->active_workspace) {
                entry->floating=false;entry->tile_weight=1;entry->frame_visible=false;
                if(count<3)feature_views[count++]=entry;
            }
        assert(count==3);feature_focus(feature_views[0]);feature_shortcut(KEY_M);feature_shortcut(KEY_M);stage=31;
    } else if(stage==31 && feature_views[0]->toplevel->base->geometry.width+2==feature_views[0]->tile_geometry.width) {
        struct wlr_box box=feature_views[0]->tile_geometry;
        resize_width=box.width;
        feature_motion(box.x+box.width-.5,box.y+box.height/2.0);
        feature_button(BTN_LEFT,true);
        assert(server->interactive_mode==MADWAY_TILE_RESIZE);
        feature_motion(box.x+box.width+59.5,box.y+box.height/2.0);
        assert(feature_views[0]->tile_geometry.width>resize_width);
        assert(feature_views[1]->tile_geometry.x==feature_views[0]->tile_geometry.x+feature_views[0]->tile_geometry.width+server->config.tile_gap);
        feature_button(BTN_LEFT,false);assert(server->interactive_view==NULL);
        assert(!feature_views[0]->floating && !feature_views[1]->floating);stage=32;
    } else if(stage==32 && feature_views[1]->toplevel->base->geometry.height+2==feature_views[1]->tile_geometry.height) {
        struct wlr_box box=feature_views[1]->tile_geometry;
        resize_width=feature_views[0]->tile_geometry.width;resize_height=box.height;
        feature_motion(box.x+box.width/2.0,box.y+box.height-.5);
        feature_button(BTN_LEFT,true);assert(server->interactive_mode==MADWAY_TILE_RESIZE);
        feature_motion(box.x+box.width/2.0,box.y+box.height+39.5);
        assert(feature_views[1]->tile_geometry.height>resize_height);
        assert(feature_views[0]->tile_geometry.width==resize_width);
        assert(feature_views[2]->tile_geometry.y==feature_views[1]->tile_geometry.y+feature_views[1]->tile_geometry.height+server->config.tile_gap);
        assert(feature_views[1]->tile_geometry.height+feature_views[2]->tile_geometry.height+server->config.tile_gap==feature_views[1]->output->usable_area.height);
        feature_button(BTN_LEFT,false);stage=33;
    } else if(stage==33 && feature_views[1]->toplevel->base->geometry.height+2==feature_views[1]->tile_geometry.height) {
        struct wlr_box box=feature_views[1]->tile_geometry;
        feature_motion(box.x+box.width/2.0,box.y+box.height*.75);
        key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_PRESSED);feature_button(BTN_RIGHT,true);
        assert(server->interactive_mode==MADWAY_TILE_RESIZE);
        feature_motion(box.x+box.width/2.0+1000,box.y+box.height*.75+1000);
        assert(feature_views[1]->output->master_percent<=90);
        assert(feature_views[1]->tile_geometry.height>=32 && feature_views[2]->tile_geometry.height>=32);
        feature_button(BTN_RIGHT,false);key(KEY_LEFTMETA,WL_KEYBOARD_KEY_STATE_RELEASED);
        assert(!feature_views[1]->floating && server->interactive_view==NULL);
        fprintf(stderr,"TILED SHARED EDGE AND MODIFIER RESIZE PASS\n");stage=34;
    } else if(stage==34) {
        unsigned count=0, outputs=0;uint32_t anchor=0;int zone=0;
        struct madway_output *output;struct madway_layer *layer;
        wl_list_for_each(output,&server->outputs,link)if(output->output->enabled)++outputs;
        wl_list_for_each(layer,&server->layers,link)
            if(layer->mapped && !strcmp(layer->surface->namespace,"madway-panel")) {
                if(count && anchor!=layer->surface->current.anchor){count=0;break;}
                anchor=layer->surface->current.anchor;zone=layer->surface->current.exclusive_zone;++count;
            }
        if(count==outputs && zone>0) {
            const uint32_t top=ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP,bottom=ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM,
                left=ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT,right=ZWLR_LAYER_SURFACE_V1_ANCHOR_RIGHT;
            unsigned bit=anchor==(top|left|right)?1:anchor==(bottom|left|right)?2:anchor==(left|top|bottom)?4:anchor==(right|top|bottom)?8:0;
            if(bit && !(panel_edges_seen&bit)) {
                bool valid=true;
                wl_list_for_each(output,&server->outputs,link)if(output->output->enabled) {
                    int w,h;wlr_output_effective_resolution(output->output,&w,&h);
                    valid=valid && output->usable_area.width==w-((bit==4||bit==8)?zone:0) && output->usable_area.height==h-((bit==1||bit==2)?zone:0)
                        && output->usable_area.x==output->layout_x+(bit==4?zone:0) && output->usable_area.y==output->layout_y+(bit==1?zone:0);
                }
                if(valid) {
                    panel_edges_seen|=bit;
                    fprintf(stderr,"PANEL EDGE %s RESERVATION PASS\n",bit==1?"top":bit==2?"bottom":bit==4?"left":"right");
                }
            }
        }
    }
    wl_event_source_timer_update(timer,25);return 0;
}

static void destroy_devices(struct wl_listener *listener, void *data)
{
    (void)data;
    wl_list_remove(&listener->link);
    wl_event_source_remove(timer);
    if (keyboard_live) wlr_keyboard_finish(&keyboard);
    if (pointer_live) wlr_pointer_finish(&pointer);
}

bool wlr_backend_start(struct wlr_backend *backend)
{
    typedef bool (*start_fn)(struct wlr_backend *);
    start_fn real_start = (start_fn)dlsym(RTLD_NEXT, "wlr_backend_start");
    // Only instrument the outer multi-backend that has madway's input listener.
    if (server != NULL || wl_list_empty(&backend->events.new_input.listener_list)) return real_start(backend);
    struct wl_listener *listener = wl_container_of(backend->events.new_input.listener_list.next, listener, link);
    server = wl_container_of(listener, server, new_input);
    bool ok = real_start(backend);
    if (!ok) return false;
    wlr_keyboard_init(&keyboard, &keyboard_impl, "test-keyboard");
    keyboard_live = true;
    wlr_pointer_init(&pointer, &pointer_impl, "test-pointer");
    pointer_live = true;
    wl_signal_emit_mutable(&backend->events.new_input, &keyboard.base);
    wl_signal_emit_mutable(&backend->events.new_input, &pointer.base);
    backend_destroy.notify = destroy_devices;
    wl_signal_add(&backend->events.destroy, &backend_destroy);
    timer = wl_event_loop_add_timer(wl_display_get_event_loop(server->display), run_stage, NULL);
    wl_event_source_timer_update(timer, 25);
    return true;
}
