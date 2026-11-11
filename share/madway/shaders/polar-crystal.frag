// Adapted from GPUImage2 PolarPixellate (Brad Larson, BSD-3-Clause).
// Copyright (c) 2015, Brad Larson. All rights reserved.
// License: ../licenses/GPUImage2-BSD-3-Clause.txt; source revision: 3a2275e48716a6ebdab0d4098bd7d90321ef4143
precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
void filter_main()
{
    vec2 normCoord = 2.0 * v_uv - 1.0;
    vec2 normCenter = 2.0 * vec2(0.5) - 1.0;

    normCoord -= normCenter;

    float r = length(normCoord); // to polar coords
    float phi = atan(normCoord.y, normCoord.x + 0.000001); // to polar coords

    r = r - mod(r, (vec2(1.0,2.7)*max(0.002,u_progress*0.15)).x) + 0.03;
    phi = phi - mod(phi, (vec2(1.0,2.7)*max(0.002,u_progress*0.15)).y);

    normCoord.x = r * cos(phi);
    normCoord.y = r * sin(phi);

    normCoord += normCenter;

    vec2 v_uvToUse = normCoord / 2.0 + 0.5;

    gl_FragColor = texture2D(u_scene, v_uvToUse );

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
