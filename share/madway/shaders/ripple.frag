precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
void main(){
    float p=u_progress;vec3 dark=vec3(.018,.024,.033);
    if(p<=0.){gl_FragColor=texture2D(u_scene,v_uv);return;}
    if(p>=.9999){gl_FragColor=vec4(dark,1.);return;}
    vec2 aspect=vec2(u_resolution.x/u_resolution.y,1.);vec2 q=(v_uv-.5)*aspect;
    float r=length(q);float front=p*1.2;float distance=r-front;
    float envelope=exp(-distance*distance*90.)*sin(p*3.14159);
    float wave=sin(distance*65.)*envelope;
    vec2 normal=normalize(q+vec2(.0001))/aspect;
    vec2 uv=v_uv+normal*wave*.025;
    float split=envelope*.003;
    vec3 scene=vec3(texture2D(u_scene,clamp(uv+normal*split,0.,1.)).r,texture2D(u_scene,clamp(uv,0.,1.)).g,texture2D(u_scene,clamp(uv-normal*split,0.,1.)).b);
    float visible=smoothstep(front-.06,front+.06,r)*(1.-smoothstep(.6,1.,p));
    vec3 caustic=vec3(.18,.38,.52)*pow(max(0.,wave),3.)*.22;
    gl_FragColor=vec4(mix(dark,scene,visible)+caustic,1.);
}
