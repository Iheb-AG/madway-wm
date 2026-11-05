precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
void main() {
    vec3 dark = vec3(0.018, 0.024, 0.033);
    float p = clamp(u_progress, 0.0, 1.0);
    float height = max(0.001, 1.0 - smoothstep(0.02, 0.72, p));
    float width = max(0.001, 1.0 - smoothstep(0.62, 0.96, p));
    vec2 centered = v_uv - 0.5;
    vec2 sample_uv = centered / vec2(width, height) + 0.5;
    float inside = step(0.0,sample_uv.x)*step(sample_uv.x,1.0)*step(0.0,sample_uv.y)*step(sample_uv.y,1.0);
    vec3 scene = texture2D(u_scene, clamp(sample_uv,0.0,1.0)).rgb;
    float gain = 1.0 - smoothstep(0.72,1.0,p);
    float line = exp(-abs(centered.y)*u_resolution.y*0.8)*step(abs(centered.x),width*0.5);
    float glow = line * smoothstep(0.25,0.7,p) * (1.0-smoothstep(0.82,1.0,p)) * 0.2;
    gl_FragColor = vec4(mix(dark,scene,inside*gain) + vec3(0.55,0.65,0.8)*glow,1.0);
}
