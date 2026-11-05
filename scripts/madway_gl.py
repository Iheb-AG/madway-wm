"""Small GLES2 renderer for the built-in session shaders, owned by Gtk.GLArea."""
import ctypes as C
import ctypes.util


class ShaderRenderer:
    def __init__(self,vertex,fragment,pixbuf):
        library=ctypes.util.find_library('GLESv2')
        if not library:raise RuntimeError('OpenGL ES 2 is unavailable')
        self.lib=C.CDLL(library);self.program=0;self.texture=C.c_uint();self.buffer=C.c_uint();self.vao=C.c_uint()
        self.lib.glGetString.restype=C.c_char_p;self.lib.glGetString.argtypes=[C.c_uint]
        version=self.lib.glGetString(0x1F02) or b''
        self.desktop=not version.startswith(b'OpenGL ES')
        if self.desktop:
            vertex='#version 150\n'+vertex.replace('attribute ','in ').replace('varying ','out ')
            fragment='#version 150\nout vec4 fragColor;\n'+fragment.replace('precision mediump float;','').replace('varying ','in ').replace('texture2D(','texture(').replace('gl_FragColor','fragColor')
        else:vertex='#version 100\n'+vertex;fragment='#version 100\n'+fragment
        signatures={
            'glCreateShader':(C.c_uint,[C.c_uint]),'glShaderSource':(None,[C.c_uint,C.c_int,C.POINTER(C.c_char_p),C.POINTER(C.c_int)]),
            'glCompileShader':(None,[C.c_uint]),'glGetShaderiv':(None,[C.c_uint,C.c_uint,C.POINTER(C.c_int)]),
            'glGetShaderInfoLog':(None,[C.c_uint,C.c_int,C.POINTER(C.c_int),C.c_char_p]),'glDeleteShader':(None,[C.c_uint]),
            'glCreateProgram':(C.c_uint,[]),'glAttachShader':(None,[C.c_uint,C.c_uint]),'glBindAttribLocation':(None,[C.c_uint,C.c_uint,C.c_char_p]),
            'glLinkProgram':(None,[C.c_uint]),'glGetProgramiv':(None,[C.c_uint,C.c_uint,C.POINTER(C.c_int)]),
            'glGetProgramInfoLog':(None,[C.c_uint,C.c_int,C.POINTER(C.c_int),C.c_char_p]),'glDeleteProgram':(None,[C.c_uint]),
            'glGenTextures':(None,[C.c_int,C.POINTER(C.c_uint)]),'glBindTexture':(None,[C.c_uint,C.c_uint]),
            'glTexParameteri':(None,[C.c_uint,C.c_uint,C.c_int]),'glPixelStorei':(None,[C.c_uint,C.c_int]),
            'glTexImage2D':(None,[C.c_uint,C.c_int,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_void_p]),
            'glGenBuffers':(None,[C.c_int,C.POINTER(C.c_uint)]),'glBindBuffer':(None,[C.c_uint,C.c_uint]),
            'glBufferData':(None,[C.c_uint,C.c_ssize_t,C.c_void_p,C.c_uint]),'glUseProgram':(None,[C.c_uint]),
            'glGetUniformLocation':(C.c_int,[C.c_uint,C.c_char_p]),'glUniform1i':(None,[C.c_int,C.c_int]),
            'glUniform1f':(None,[C.c_int,C.c_float]),'glUniform2f':(None,[C.c_int,C.c_float,C.c_float]),
            'glActiveTexture':(None,[C.c_uint]),'glViewport':(None,[C.c_int,C.c_int,C.c_int,C.c_int]),
            'glDisable':(None,[C.c_uint]),'glEnableVertexAttribArray':(None,[C.c_uint]),
            'glVertexAttribPointer':(None,[C.c_uint,C.c_int,C.c_uint,C.c_ubyte,C.c_int,C.c_void_p]),
            'glDrawArrays':(None,[C.c_uint,C.c_int,C.c_int]),'glDeleteTextures':(None,[C.c_int,C.POINTER(C.c_uint)]),
            'glDeleteBuffers':(None,[C.c_int,C.POINTER(C.c_uint)]),
        }
        for name,(result,args) in signatures.items():
            function=getattr(self.lib,name);function.restype=result;function.argtypes=args;setattr(self,name,function)
        if self.desktop:
            for name,args in [('glGenVertexArrays',[C.c_int,C.POINTER(C.c_uint)]),('glBindVertexArray',[C.c_uint]),('glDeleteVertexArrays',[C.c_int,C.POINTER(C.c_uint)])]:
                function=getattr(self.lib,name);function.restype=None;function.argtypes=args;setattr(self,name,function)
            self.glGenVertexArrays(1,C.byref(self.vao));self.glBindVertexArray(self.vao.value)
        shaders=[]
        try:
            for kind,source in ((0x8B31,vertex),(0x8B30,fragment)):
                shader=self.glCreateShader(kind);shaders.append(shader)
                data=C.c_char_p(source.encode());self.glShaderSource(shader,1,C.byref(data),None);self.glCompileShader(shader)
                status=C.c_int();self.glGetShaderiv(shader,0x8B81,C.byref(status))
                if not status.value:
                    error=C.create_string_buffer(4096);self.glGetShaderInfoLog(shader,len(error),None,error)
                    raise RuntimeError('Session shader compilation: '+error.value.decode(errors='replace'))
            self.program=self.glCreateProgram()
            for shader in shaders:self.glAttachShader(self.program,shader)
            self.glBindAttribLocation(self.program,0,b'a_position');self.glLinkProgram(self.program)
            status=C.c_int();self.glGetProgramiv(self.program,0x8B82,C.byref(status))
            if not status.value:
                error=C.create_string_buffer(4096);self.glGetProgramInfoLog(self.program,len(error),None,error)
                raise RuntimeError('Session shader linking: '+error.value.decode(errors='replace'))
            image=pixbuf if pixbuf.get_has_alpha() else pixbuf.add_alpha(False,0,0,0)
            width,height=image.get_width(),image.get_height();stride=image.get_rowstride();pixels=image.get_pixels()
            packed=b''.join(pixels[y*stride:y*stride+width*4] for y in range(height))
            self.glGenTextures(1,C.byref(self.texture));self.glBindTexture(0x0DE1,self.texture.value)
            for key,value in ((0x2801,0x2601),(0x2800,0x2601),(0x2802,0x812F),(0x2803,0x812F)):self.glTexParameteri(0x0DE1,key,value)
            self.glPixelStorei(0x0CF5,1);data=C.create_string_buffer(packed)
            self.glTexImage2D(0x0DE1,0,0x1908,width,height,0,0x1908,0x1401,data)
            vertices=(C.c_float*8)(-1,-1,1,-1,-1,1,1,1)
            self.glGenBuffers(1,C.byref(self.buffer));self.glBindBuffer(0x8892,self.buffer.value);self.glBufferData(0x8892,C.sizeof(vertices),vertices,0x88E4)
            self.progress=self.glGetUniformLocation(self.program,b'u_progress');self.resolution=self.glGetUniformLocation(self.program,b'u_resolution')
            self.scene=self.glGetUniformLocation(self.program,b'u_scene')
        except Exception:
            self.close();raise
        finally:
            for shader in shaders:self.glDeleteShader(shader)

    def draw(self,progress,width,height):
        self.glViewport(0,0,width,height);self.glDisable(0x0BE2);self.glDisable(0x0B71)
        self.glUseProgram(self.program);self.glActiveTexture(0x84C0);self.glBindTexture(0x0DE1,self.texture.value)
        if self.vao.value:self.glBindVertexArray(self.vao.value)
        self.glUniform1i(self.scene,0);self.glUniform1f(self.progress,progress);self.glUniform2f(self.resolution,width,height)
        self.glBindBuffer(0x8892,self.buffer.value);self.glEnableVertexAttribArray(0);self.glVertexAttribPointer(0,2,0x1406,0,0,None)
        self.glDrawArrays(0x0005,0,4)

    def close(self):
        if self.texture.value:self.glDeleteTextures(1,C.byref(self.texture));self.texture.value=0
        if self.buffer.value:self.glDeleteBuffers(1,C.byref(self.buffer));self.buffer.value=0
        if self.program:self.glDeleteProgram(self.program);self.program=0
        if self.vao.value:self.glDeleteVertexArrays(1,C.byref(self.vao));self.vao.value=0
