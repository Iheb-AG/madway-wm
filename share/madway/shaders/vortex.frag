precision mediump float;
uniform sampler2D u_scene;
uniform float u_progress;
uniform vec2 u_resolution;
varying vec2 v_uv;
void main() {
    float p=u_progress; vec3 dark=vec3(.018,.024,.033);
    if(p<=0.0){gl_FragColor=texture2D(u_scene,v_uv);return;}
    if(p>=.9999){gl_FragColor=vec4(dark,1.);return;}
    vec2 aspect=vec2(u_resolution.x/u_resolution.y,1.);
    vec2 q=(v_uv-.5)*aspect; float r=length(q); float horizon=p*.86;
    float influence=p/(r*r*5.+.15); float a=atan(q.y+.00001,q.x+.00001)+influence*1.8;
    vec2 bent=vec2(cos(a),sin(a))*(r+influence*.035)/aspect+.5;
    vec2 dispersion=normalize(q+vec2(.0001))/aspect*.008*p;
    vec3 scene=vec3(texture2D(u_scene,clamp(bent+dispersion,0.,1.)).r,texture2D(u_scene,clamp(bent,0.,1.)).g,texture2D(u_scene,clamp(bent-dispersion,0.,1.)).b);
    float edge=abs(r-horizon); float disk=exp(-edge*75.)*(.5+.5*sin(a*3.+r*28.-p*12.));
    float aperture=smoothstep(horizon-.025,horizon+.025,r);
    vec3 corona=mix(vec3(.25,.52,.8),vec3(.9,.43,.14),.5+.5*sin(a))*disk*sin(p*3.14159)*.35;
    gl_FragColor=vec4(mix(dark,scene,aperture*(1.-smoothstep(.55,1.,p)))+corona,1.);
}
