precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
float hash(vec2 p){return fract(52.9829*fract(dot(p,vec2(.0671106,.00583715))));}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+1.),f.x),f.y);}
float fbm(vec2 p){float n=0.,gain=.5;for(int i=0;i<4;i++){n+=gain*noise(p);p=p*2.03+vec2(3.7,1.9);gain*=.5;}return n;}
void main(){
    float p=u_progress;vec3 dark=vec3(.018,.024,.033);
    if(p<=0.){gl_FragColor=texture2D(u_scene,v_uv);return;}
    if(p>=.9999){gl_FragColor=vec4(dark,1.);return;}
    vec2 aspect=vec2(u_resolution.x/u_resolution.y,1.);vec2 q=v_uv*aspect;
    float field=v_uv.y*.65+fbm(q*7.+vec2(p*.25,-p))*.35;
    float d=field-(p*1.35-.16);float keep=smoothstep(-.012,.018,d);
    float rim=exp(-abs(d)*100.)*sin(p*3.14159);
    vec3 glow=mix(vec3(.65,.12,.015),vec3(1.,.62,.16),exp(-abs(d)*220.))*rim*.45;
    float ash=pow(hash(floor((q+vec2(0.,p*.18))*90.)),24.)*(1.-keep)*sin(p*3.14159);
    vec3 scene=texture2D(u_scene,v_uv+vec2(sin(v_uv.y*50.+p*6.)*.001*rim,0.)).rgb;
    gl_FragColor=vec4(mix(dark,scene,keep)+glow+vec3(.65,.27,.04)*ash*.22,1.);
}
