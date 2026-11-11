// Adapted from GPUImage2 PinchDistortion (Brad Larson, BSD-3-Clause).
// Copyright (c) 2015, Brad Larson. All rights reserved.
// License: ../licenses/GPUImage2-BSD-3-Clause.txt; source revision: 3a2275e48716a6ebdab0d4098bd7d90321ef4143
precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
void filter_main()
{
    vec2 v_uvToUse = vec2(v_uv.x, (v_uv.y * (u_resolution.y/max(1.0,u_resolution.x)) + 0.5 - 0.5 * (u_resolution.y/max(1.0,u_resolution.x))));
    float dist = distance(vec2(0.5), v_uvToUse);
    v_uvToUse = v_uv;

    if (dist < 0.85)
    {
        v_uvToUse -= vec2(0.5);
        float percent = 1.0 + ((0.5 - dist) / 0.5) * (u_progress*0.9);
        v_uvToUse = v_uvToUse * percent;
        v_uvToUse += vec2(0.5);

        gl_FragColor = texture2D(u_scene, v_uvToUse );
    }
    else
    {
        gl_FragColor = texture2D(u_scene, v_uv );
    }
}
void main() {
    vec4 original=texture2D(u_scene,v_uv);
    vec3 dark=vec3(0.018,0.024,0.033);
    if(u_progress<=0.0){gl_FragColor=vec4(original.rgb,1.0);return;}
    if(u_progress>=1.0){gl_FragColor=vec4(dark,1.0);return;}
    filter_main();
    vec3 filtered=mix(original.rgb,gl_FragColor.rgb,smoothstep(0.0,0.3,u_progress));
    gl_FragColor=vec4(mix(filtered,dark,smoothstep(0.15,1.0,u_progress)),1.0);
}
