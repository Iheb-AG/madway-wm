precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
void main() {
    vec2 aspect = vec2(u_resolution.x / max(1.0,u_resolution.y),1.0);
    float distance = length((v_uv-0.5)*aspect);
    float diagonal = length(aspect)*0.5;
    float radius = mix(diagonal+0.03,-0.025,u_progress);
    float mask = 1.0-smoothstep(radius-0.018,radius+0.018,distance);
    vec2 zoom = (v_uv-0.5)*(1.0-u_progress*0.025)+0.5;
    vec3 scene = texture2D(u_scene,zoom).rgb;
    vec3 dark = vec3(0.018,0.024,0.033);
    gl_FragColor = vec4(mix(dark,scene,mask*(1.0-u_progress*0.18)),1.0);
}
