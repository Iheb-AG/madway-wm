precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
float hash(vec2 p){return fract(52.9829*fract(dot(p,vec2(.0671106,.00583715))));}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+1.),f.x),f.y);}
float fbm(vec2 p){float n=0.,g=.5;for(int i=0;i<4;i++){n+=noise(p)*g;p=mat2(.8,.6,-.6,.8)*p*2.1+1.3;g*=.5;}return n;}
void main(){
    float p=u_progress;vec3 dark=vec3(.018,.024,.033);
    if(p<=0.){gl_FragColor=texture2D(u_scene,v_uv);return;}
    if(p>=.9999){gl_FragColor=vec4(dark,1.);return;}
    vec2 uv=v_uv;uv.x*=u_resolution.x/u_resolution.y;
    float flow=fbm(uv*3.+vec2(p*.7,-p*.4));
    float front=p*1.5-.25;float distance=v_uv.x+flow*.25-front;
    float veil=1.-smoothstep(-.06,.12,distance);
    float ribbons=pow(.5+.5*sin(uv.x*12.+flow*9.+p*4.),6.);
    float envelope=exp(-distance*distance*35.)*sin(p*3.14159);
    vec3 light=mix(vec3(.08,.44,.35),vec3(.28,.18,.6),flow)*ribbons*envelope*.3;
    vec2 refraction=vec2(flow-.5,sin(flow*6.28))*.008*envelope;
    vec3 scene=texture2D(u_scene,clamp(v_uv+refraction,0.,1.)).rgb;
    gl_FragColor=vec4(mix(mix(scene,dark,veil)+light,dark,smoothstep(.82,1.,p)),1.);
}
