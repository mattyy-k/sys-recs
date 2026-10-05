// Android NDK / OpenGL ES 3.1 forest-fire simulation. Each epoch executes on
// GPU.
#include <EGL/egl.h>
#include <GLES3/gl31.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *shader_src =
    "#version 310 es\n"
    "layout(local_size_x=8, local_size_y=8) in;\n"
    "layout(std430, binding=0) readonly buffer Src { uint src[]; };\n"
    "layout(std430, binding=1) writeonly buffer Dst { uint dst[]; };\n"
    "uniform uint side;\n"
    "uniform uint seed;\n"
    "uint hashv(uint x) {\n"
    "    x ^= x >> 16;\n"
    "    x *= 0x7feb352du;\n"
    "    x ^= x >> 15;\n"
    "    x *= 0x846ca68bu;\n"
    "    x ^= x >> 16;\n"
    "    return x;\n"
    "}\n"
    "void main() {\n"
    "    uint x = gl_GlobalInvocationID.x;\n"
    "    uint y = gl_GlobalInvocationID.y;\n"
    "    if (x >= side || y >= side) return;\n"
    "    uint i = y * side + x;\n"
    "    uint s = src[i];\n"
    "    if (s == 1u) { dst[i] = 2u; return; }\n"
    "    if (s != 0u) { dst[i] = s; return; }\n"
    "    bool fire = false;\n"
    "    for (int dy = -1; dy <= 1; dy++) {\n"
    "        for (int dx = -1; dx <= 1; dx++) {\n"
    "            if (dx == 0 && dy == 0) continue;\n"
    "            int nx = int(x) + dx;\n"
    "            int ny = int(y) + dy;\n"
    "            if (nx >= 0 && ny >= 0 && nx < int(side) && ny < int(side) "
    "&&\n"
    "                src[uint(ny) * side + uint(nx)] == 1u) {\n"
    "                fire = true;\n"
    "            }\n"
    "        }\n"
    "    }\n"
    "    uint r = hashv(i ^ seed);\n"
    "    dst[i] = (fire && (r % 10000u) < 1500u) ? 1u : 0u;\n"
    "}\n";

static GLuint compile_shader(void) {
  GLuint s = glCreateShader(GL_COMPUTE_SHADER);
  glShaderSource(s, 1, &shader_src, NULL);
  glCompileShader(s);
  GLint ok = 0;
  glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
  if (!ok) {
    GLint n = 0;
    glGetShaderiv(s, GL_INFO_LOG_LENGTH, &n);
    char *log = calloc((size_t)n + 1, 1);
    glGetShaderInfoLog(s, n, NULL, log);
    fprintf(stderr, "shader compile: %s\n", log);
    free(log);
    return 0;
  }
  return s;
}
static int egl_start(void) {
  EGLDisplay d = eglGetDisplay(EGL_DEFAULT_DISPLAY);
  EGLint ma, mi;
  if (d == EGL_NO_DISPLAY || !eglInitialize(d, &ma, &mi)) {
    fprintf(stderr, "EGL unavailable: eglInitialize failed (run on Android "
                    "with GLES 3.1)\n");
    return 0;
  }
  if (!eglBindAPI(EGL_OPENGL_ES_API))
    return 0;
  const EGLint ca[] = {EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
                       EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_NONE};
  EGLConfig cfg;
  EGLint num;
  if (!eglChooseConfig(d, ca, &cfg, 1, &num) || !num) {
    fprintf(stderr, "No EGL OpenGL ES3 config\n");
    return 0;
  }
  const EGLint xa[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
  EGLContext c = eglCreateContext(d, cfg, EGL_NO_CONTEXT, xa);
  if (c == EGL_NO_CONTEXT) {
    fprintf(stderr, "Cannot create GLES3 context\n");
    return 0;
  }
  if (!eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, c)) {
    const EGLint pa[] = {EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE};
    EGLSurface surf = eglCreatePbufferSurface(d, cfg, pa);
    if (surf == EGL_NO_SURFACE || !eglMakeCurrent(d, surf, surf, c)) {
      fprintf(stderr, "Cannot make EGL context current (surfaceless and "
                      "pbuffer unavailable)\n");
      return 0;
    }
  }
  GLint major = 0, minor = 0;
  glGetIntegerv(GL_MAJOR_VERSION, &major);
  glGetIntegerv(GL_MINOR_VERSION, &minor);
  if (major < 3 || (major == 3 && minor < 1)) {
    fprintf(stderr, "OpenGL ES 3.1 required; got %d.%d\n", major, minor);
    return 0;
  }
  return 1;
}
int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: %s M [seed] (Android GLES 3.1)\n", argv[0]);
    return 2;
  }
  unsigned m = (unsigned)strtoul(argv[1], NULL, 10),
           seed = argc > 2 ? (unsigned)strtoul(argv[2], NULL, 10) : 12345u;
  if (!m || m > 8192) {
    fprintf(stderr, "M must be 1..8192\n");
    return 2;
  }
  if (!egl_start())
    return 1;
  GLuint sh = compile_shader();
  if (!sh)
    return 1;
  GLuint prog = glCreateProgram();
  glAttachShader(prog, sh);
  glLinkProgram(prog);
  GLint ok;
  glGetProgramiv(prog, GL_LINK_STATUS, &ok);
  if (!ok) {
    fprintf(stderr, "compute program link failed\n");
    return 1;
  }
  size_t n = (size_t)m * m;
  GLuint *grid = calloc(n, sizeof(*grid)),
         *readback = malloc(n * sizeof(*grid));
  if (!grid || !readback)
    return 1;
  srand(seed);
  for (size_t i = 0; i < n; i++)
    grid[i] = (rand() % 100 < 55) ? 0u : 2u;
  grid[(m / 2) * m + m / 2] = 1u;
  if (m <= 20)
    grid[(m / 2) * m + m / 2] = 1;
  GLuint b[2];
  glGenBuffers(2, b);
  for (int k = 0; k < 2; k++) {
    glBindBuffer(GL_SHADER_STORAGE_BUFFER, b[k]);
    glBufferData(GL_SHADER_STORAGE_BUFFER, n * sizeof(uint32_t), grid,
                 GL_DYNAMIC_COPY);
  }
  glUseProgram(prog);
  glUniform1ui(glGetUniformLocation(prog, "side"), m);
  unsigned epoch = 0;
  int burning = 1;
  uint32_t base = 0;
  while (burning && epoch < 100000) {
    int src = epoch & 1, dst = 1 - src;
    glUniform1ui(glGetUniformLocation(prog, "seed"), seed + epoch + base);
    glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, b[src]);
    glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 1, b[dst]);
    glDispatchCompute((m + 7) / 8, (m + 7) / 8, 1);
    glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT |
                    GL_BUFFER_UPDATE_BARRIER_BIT);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER, b[dst]);
    void *mapped =
        glMapBufferRange(GL_SHADER_STORAGE_BUFFER, 0,
                         (GLsizeiptr)(n * sizeof(uint32_t)), GL_MAP_READ_BIT);
    if (!mapped) {
      fprintf(stderr, "GPU buffer readback mapping failed\n");
      return 1;
    }
    memcpy(readback, mapped, n * sizeof(uint32_t));
    glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
    burning = 0;
    for (size_t i = 0; i < n; i++)
      if (readback[i] == 1u)
        burning = 1;
    epoch++;
    if (m <= 20) {
      printf("epoch %u\n", epoch);
      for (unsigned y = 0; y < m; y++) {
        for (unsigned x = 0; x < m; x++) {
          uint32_t v = readback[(size_t)y * m + x];
          putchar(v == 0 ? 'H' : v == 1 ? 'B' : 'N');
          putchar(x + 1 == m ? '\n' : ' ');
        }
      }
    }
  }
  printf("M=%u epochs=%u status=%s\n", m, epoch,
         burning ? "iteration limit reached" : "extinguished");
  glDeleteBuffers(2, b);
  glDeleteProgram(prog);
  glDeleteShader(sh);
  free(grid);
  free(readback);
  return burning ? 1 : 0;
}
