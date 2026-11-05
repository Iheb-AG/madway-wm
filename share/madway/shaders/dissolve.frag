precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
// Bounded arithmetic also works on GLES2 mediump fragment implementations.
float noise(vec2 p) { return fract(52.9829 * fract(dot(p,vec2(0.0671106,0.00583715)))); }
void main() {
    vec2 cells = floor(v_uv * u_resolution / 7.0);
    float threshold = noise(cells)*0.72 + v_uv.y*0.28;
    float mask = 1.0-smoothstep(threshold,threshold+0.13,u_progress*1.16);
    vec3 scene=texture2D(u_scene,v_uv).rgb;
    vec3 dark=vec3(0.018,0.024,0.033);
    gl_FragColor=vec4(mix(dark,scene,mask*(1.0-u_progress*0.25)),1.0);
}
