// Adapted from GPUImage2 Crosshatch (Brad Larson, BSD-3-Clause).
// Copyright (c) 2015, Brad Larson. All rights reserved.
// License: ../licenses/GPUImage2-BSD-3-Clause.txt; source revision: 3a2275e48716a6ebdab0d4098bd7d90321ef4143
precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
const vec3 W = vec3(0.2125, 0.7154, 0.0721);

void filter_main()
{
    float luminance = dot(texture2D(u_scene, v_uv).rgb, W);

    vec4 colorToDisplay = vec4(1.0, 1.0, 1.0, 1.0);
    if (luminance < 1.00)
    {
        if (mod(v_uv.x + v_uv.y, 0.018) <= 0.0015)
        {
            colorToDisplay = vec4(0.0, 0.0, 0.0, 1.0);
        }
    }
    if (luminance < 0.75)
    {
        if (mod(v_uv.x - v_uv.y, 0.018) <= 0.0015)
        {
            colorToDisplay = vec4(0.0, 0.0, 0.0, 1.0);
        }
    }
    if (luminance < 0.50)
    {
        if (mod(v_uv.x + v_uv.y - (0.018 / 2.0), 0.018) <= 0.0015)
        {
            colorToDisplay = vec4(0.0, 0.0, 0.0, 1.0);
        }
    }
    if (luminance < 0.3)
    {
        if (mod(v_uv.x - v_uv.y - (0.018 / 2.0), 0.018) <= 0.0015)
        {
            colorToDisplay = vec4(0.0, 0.0, 0.0, 1.0);
        }
    }

    gl_FragColor = colorToDisplay;
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
