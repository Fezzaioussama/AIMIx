/**
 * True when this browser can create a WebGL context. The probe canvas is thrown
 * away straight after, and the context released, so it never counts against the
 * browser's limit on live contexts.
 */
export function hasWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2') ?? canvas.getContext('webgl');
    gl?.getExtension('WEBGL_lose_context')?.loseContext();
    return gl !== null && gl !== undefined;
  } catch {
    return false;
  }
}
