// Adapted from GPUImage2 ZoomBlur (Brad Larson, BSD-3-Clause).
// Copyright (c) 2015, Brad Larson. All rights reserved.
// License: ../licenses/GPUImage2-BSD-3-Clause.txt; source revision: 3a2275e48716a6ebdab0d4098bd7d90321ef4143
precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
void filter_main()
{
    // TODO: Do a more intelligent scaling based on resolution here
    vec2 samplingOffset = 1.0/100.0 * (vec2(0.5) - v_uv) * (u_progress*24.0);

    vec4 fragmentColor = texture2D(u_scene, v_uv) * 0.18;
    fragmentColor += texture2D(u_scene, v_uv + samplingOffset) * 0.15;
    fragmentColor += texture2D(u_scene, v_uv + (2.0 * samplingOffset)) *  0.12;
    fragmentColor += texture2D(u_scene, v_uv + (3.0 * samplingOffset)) * 0.09;
    fragmentColor += texture2D(u_scene, v_uv + (4.0 * samplingOffset)) * 0.05;
    fragmentColor += texture2D(u_scene, v_uv - samplingOffset) * 0.15;
    fragmentColor += texture2D(u_scene, v_uv - (2.0 * samplingOffset)) *  0.12;
    fragmentColor += texture2D(u_scene, v_uv - (3.0 * samplingOffset)) * 0.09;
    fragmentColor += texture2D(u_scene, v_uv - (4.0 * samplingOffset)) * 0.05;

    gl_FragColor = fragmentColor;
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
