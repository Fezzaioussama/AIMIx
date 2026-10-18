import { FRAGMENT_SHADER, VERTEX_SHADER } from './shader';

type Uniforms = Record<string, WebGLUniformLocation | null>;

export interface AuroraProgram {
  program: WebGLProgram;
  uniforms: Uniforms;
}

export interface AuroraGeometry {
  vao: WebGLVertexArrayObject;
  buffer: WebGLBuffer;
}

/** Everything one frame needs, already resolved from props and the animation state. */
export interface AuroraFrame {
  time: number;
  palette: Float32Array;
  stopCount: number;
  amplitude: number;
  blend: number;
  height: number;
  glow: number;
  brightness: number;
  layers: number;
  pointer: [number, number, number];
  reveal: number;
  opacity: number;
}

/** Compiles one shader stage; null (never a throw) when the driver rejects it. */
function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader | null {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return shader;
  gl.deleteShader(shader);
  return null;
}

/** Looks every active uniform up once, keyed by name (`uStops[0]` → `uStops`). */
function collectUniforms(gl: WebGL2RenderingContext, program: WebGLProgram): Uniforms {
  const uniforms: Uniforms = {};
  const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS) as number;
  for (let index = 0; index < count; index++) {
    const info = gl.getActiveUniform(program, index);
    if (info) uniforms[info.name.replace('[0]', '')] = gl.getUniformLocation(program, info.name);
  }
  return uniforms;
}

/** Builds the aurora program, or null so the caller can fall back to no background. */
export function linkAuroraProgram(gl: WebGL2RenderingContext): AuroraProgram | null {
  const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
  const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
  const program = gl.createProgram();
  if (!vertex || !fragment || !program) return null;
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.bindAttribLocation(program, 0, 'aPosition');
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program);
    return null;
  }
  return { program, uniforms: collectUniforms(gl, program) };
}

/** One oversized triangle that covers clip space — cheaper than a two-triangle quad. */
export function createFullscreenTriangle(gl: WebGL2RenderingContext): AuroraGeometry | null {
  const buffer = gl.createBuffer();
  const vao = gl.createVertexArray();
  if (!buffer || !vao) return null;
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  return { vao, buffer };
}

/** Uploads one frame's uniforms and draws it across the whole canvas. */
export function drawAurora(
  gl: WebGL2RenderingContext,
  { program, uniforms: u }: AuroraProgram,
  geometry: AuroraGeometry,
  frame: AuroraFrame,
): void {
  const { width, height } = gl.canvas;
  gl.viewport(0, 0, width, height);
  gl.useProgram(program);
  gl.bindVertexArray(geometry.vao);
  gl.uniform2f(u.uResolution, width, height);
  gl.uniform1f(u.uTime, frame.time);
  gl.uniform3fv(u.uStops, frame.palette);
  gl.uniform1i(u.uStopCount, frame.stopCount);
  gl.uniform1f(u.uAmplitude, frame.amplitude);
  gl.uniform1f(u.uBlend, frame.blend);
  gl.uniform1f(u.uHeight, frame.height);
  gl.uniform1f(u.uGlow, frame.glow);
  gl.uniform1f(u.uBrightness, frame.brightness);
  gl.uniform1i(u.uLayers, frame.layers);
  gl.uniform3f(u.uPointer, ...frame.pointer);
  gl.uniform1f(u.uReveal, 1 - (1 - frame.reveal) ** 3);
  gl.uniform1f(u.uOpacity, frame.opacity);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
}

/** Frees the GPU objects and drops the context so browsers do not hit their context cap. */
export function disposeAurora(
  gl: WebGL2RenderingContext,
  { program }: AuroraProgram,
  geometry: AuroraGeometry,
): void {
  gl.deleteProgram(program);
  gl.deleteBuffer(geometry.buffer);
  gl.deleteVertexArray(geometry.vao);
  gl.getExtension('WEBGL_lose_context')?.loseContext();
}
