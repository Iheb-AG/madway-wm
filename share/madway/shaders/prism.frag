precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
void main(){
    float p=u_progress;vec3 dark=vec3(.018,.024,.033);
    if(p<=0.){gl_FragColor=texture2D(u_scene,v_uv);return;}
    if(p>=.9999){gl_FragColor=vec4(dark,1.);return;}
    vec2 grid=vec2(7.,5.);vec2 cell=floor(v_uv*grid);vec2 local=fract(v_uv*grid)-.5;
    float order=fract(dot(cell,vec2(.37,.61)));float phase=smoothstep(order*.28,.72+order*.28,p);
    float angle=phase*1.570796;float width=max(.002,cos(angle));
    vec2 warped=local;warped.x/=width;warped.y/=1.+sin(angle)*local.x*.55;
    vec2 uv=(cell+warped+.5)/grid;
    float inside=(1.-smoothstep(.48,.5,abs(warped.x)))*(1.-smoothstep(.48,.5,abs(warped.y)));
    float bevel=exp(-abs(abs(warped.x)-.48)*110.);
    vec3 glass=texture2D(u_scene,clamp(uv,0.,1.)).rgb*(1.-phase*.45);
    vec3 rim=vec3(.36,.55,.76)*bevel*sin(angle)*.35;
    float seam=smoothstep(0.,.08,p);
    gl_FragColor=vec4(mix(texture2D(u_scene,v_uv).rgb,mix(dark,glass+rim,inside),seam),1.);
}
