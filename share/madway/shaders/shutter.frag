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
    float sector=.897598;float angle=atan(q.y+.00001,q.x+.00001)+p*1.25;
    float facet=mod(angle+sector*.5,sector)-sector*.5;
    float distance=length(q)*cos(facet);float aperture=(1.-p)*(length(aspect)*.55+.03)-.03;
    float aa=max(.002,1.5/u_resolution.y);float mask=1.-smoothstep(aperture-aa,aperture+aa,distance);
    float seam=pow(abs(facet)/(sector*.5),35.);
    vec3 metal=mix(dark,vec3(.07,.085,.11),.35+.25*cos(facet*3.));metal+=vec3(.025,.035,.05)*seam;
    metal=mix(metal,dark,smoothstep(.6,1.,p));
    float bevel=exp(-abs(distance-aperture)*120.)*sin(p*3.14159);
    vec3 scene=texture2D(u_scene,(v_uv-.5)*(1.-p*.035)+.5).rgb;
    gl_FragColor=vec4(mix(metal,scene,mask)+vec3(.12,.2,.3)*bevel*.2,1.);
}
