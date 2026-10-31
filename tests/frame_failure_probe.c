/* Simulate transient backend commit failures on a private headless output. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_output.h>

static unsigned attempts,failures;
bool wlr_scene_output_commit(struct wlr_scene_output *output,const struct wlr_scene_output_state_options *options)
{
    typedef bool (*fn)(struct wlr_scene_output *,const struct wlr_scene_output_state_options *);
    fn real=(fn)dlsym(RTLD_NEXT,"wlr_scene_output_commit");
    ++attempts;
    unsigned limit=(unsigned)atoi(getenv("MADWAY_TEST_FRAME_FAILURES"));
    bool fail=attempts>=12 && failures<limit && access(getenv("MADWAY_TEST_FRAME_RELEASE"),F_OK)!=0;
    if(fail) {
        ++failures;
        // A failed build/submit may already have consumed its damage region.
        pixman_region32_clear(&output->damage_ring.current);
    }
    bool result=fail?false:real(output,options);
    struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);
    FILE *trace=fopen(getenv("MADWAY_TEST_FRAME_TRACE"),"a");
    if(trace) {
        fprintf(trace,"{\"attempt\":%u,\"failure\":%s,\"success\":%s,\"time\":%.6f}\n",attempts,fail?"true":"false",result?"true":"false",now.tv_sec+now.tv_nsec/1e9);
        fclose(trace);
    }
    if(fail)errno=EBUSY;
    return result;
}
