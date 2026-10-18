import { buildPalette } from './palette';
import { createFullscreenTriangle, disposeAurora, drawAurora, linkAuroraProgram } from './program';
import type { AuroraGeometry, AuroraProgram } from './program';

export interface AuroraSettings {
  stops: readonly string[];
  amplitude: number;
  blend: number;
  speed: number;
  height: number;
  glow: number;
  brightness: number;
  layers: number;
  opacity: number;
  mouseInteraction: boolean;
  intro: boolean;
  dpr: number;
}

interface Host {
  container: HTMLElement;
  canvas: HTMLCanvasElement;
  settings: () => AuroraSettings;
}

const INTRO_SECONDS = 2.4;
const CONTEXT: WebGLContextAttributes = {
  alpha: true,
  premultipliedAlpha: true,
  antialias: false,
  depth: false,
  stencil: false,
};

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/**
 * Owns the WebGL context, the frame loop and the listeners behind one <Aurora>.
 * It creates its own canvas so a remount (React StrictMode) never inherits a lost context.
 */
export class AuroraRenderer {
  private raf = 0;
  private last = 0;
  private visible = true;
  private paletteKey = '';
  private palette: Float32Array = new Float32Array(0);
  private readonly reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  private readonly pointer = { x: 0, y: 0, inside: false };
  private readonly view = { width: 1, height: 1 };
  private readonly state = { clock: 0, px: 0, reach: 0, reveal: 1 };
  private readonly disposers: Array<() => void> = [];

  private constructor(
    private readonly gl: WebGL2RenderingContext,
    private readonly program: AuroraProgram,
    private readonly geometry: AuroraGeometry,
    private readonly host: Host,
  ) {
    this.state.reveal = host.settings().intro && !this.reduce ? 0 : 1;
  }

  static start(container: HTMLElement, settings: () => AuroraSettings): AuroraRenderer | null {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2', CONTEXT);
    if (!gl) return null;
    const program = linkAuroraProgram(gl);
    const geometry = program && createFullscreenTriangle(gl);
    if (!program || !geometry) return null;
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.cssText = 'position:absolute;inset:0;display:block;width:100%;height:100%';
    container.appendChild(canvas);
    const renderer = new AuroraRenderer(gl, program, geometry, { container, canvas, settings });
    renderer.listen();
    renderer.resize();
    return renderer;
  }

  /** Draws again after a prop change and restarts the loop if it had stopped. */
  wake = (): void => {
    if (!this.raf && this.visible && !document.hidden) this.raf = requestAnimationFrame(this.frame);
  };

  dispose(): void {
    cancelAnimationFrame(this.raf);
    this.disposers.forEach((dispose) => dispose());
    disposeAurora(this.gl, this.program, this.geometry);
    this.host.canvas.remove();
  }

  private frame = (now: number): void => {
    this.raf = 0;
    if (!this.visible || document.hidden) return;
    const dt = this.last ? clamp((now - this.last) / 1000, 0.0005, 0.05) : 1 / 60;
    this.last = now;
    this.advance(dt, this.host.settings());
    this.render();
    // Under reduced motion the picture is static: one frame per wake is enough.
    if (!this.reduce) this.raf = requestAnimationFrame(this.frame);
  };

  private advance(dt: number, settings: AuroraSettings): void {
    const { state, pointer, view } = this;
    if (!this.reduce) state.clock += dt * settings.speed;
    const engaged = settings.mouseInteraction && pointer.inside && !this.reduce;
    if (engaged) {
      const target = (pointer.x - view.width / 2) / view.height;
      state.px += (target - state.px) * (1 - Math.exp(-dt / 0.6));
    }
    state.reach += ((engaged ? 1 : 0) - state.reach) * (1 - Math.exp(-dt / (engaged ? 0.9 : 1.4)));
    const intro = settings.intro && !this.reduce;
    state.reveal = intro ? Math.min(1, state.reveal + dt / INTRO_SECONDS) : 1;
  }

  private render(): void {
    const settings = this.host.settings();
    const key = settings.stops.join('|');
    if (key !== this.paletteKey) {
      this.paletteKey = key;
      this.palette = buildPalette(settings.stops);
    }
    drawAurora(this.gl, this.program, this.geometry, {
      ...settings,
      time: this.state.clock,
      palette: this.palette,
      stopCount: settings.stops.length,
      pointer: [this.state.px, 0, this.state.reach],
      reveal: this.state.reveal,
    });
  }

  private resize = (): void => {
    const { container, canvas, settings } = this.host;
    const ratio = Math.min(settings().dpr, 2);
    this.view.width = Math.max(1, container.clientWidth);
    this.view.height = Math.max(1, container.clientHeight);
    canvas.width = Math.max(1, Math.round(this.view.width * ratio));
    canvas.height = Math.max(1, Math.round(this.view.height * ratio));
    this.render();
    this.wake();
  };

  private listen(): void {
    const { container } = this.host;
    const resizer = new ResizeObserver(this.resize);
    const intersection = new IntersectionObserver((entries) => {
      this.visible = entries.some((entry) => entry.isIntersecting);
      this.resume();
    });
    resizer.observe(container);
    intersection.observe(container);
    window.addEventListener('pointermove', this.onPointer, { passive: true });
    document.documentElement.addEventListener('pointerleave', this.onLeave);
    document.addEventListener('visibilitychange', this.resume);
    this.disposers.push(
      () => resizer.disconnect(),
      () => intersection.disconnect(),
      () => window.removeEventListener('pointermove', this.onPointer),
      () => document.documentElement.removeEventListener('pointerleave', this.onLeave),
      () => document.removeEventListener('visibilitychange', this.resume),
    );
  }

  /** Back on screen: restart timing from zero so the clock does not jump. */
  private resume = (): void => {
    this.last = 0;
    this.wake();
  };

  private onPointer = (event: PointerEvent): void => {
    const rect = this.host.container.getBoundingClientRect();
    const { pointer } = this;
    const wasInside = pointer.inside;
    pointer.x = event.clientX - rect.left;
    pointer.y = event.clientY - rect.top;
    pointer.inside =
      pointer.x >= 0 && pointer.y >= 0 && pointer.x <= rect.width && pointer.y <= rect.height;
    // Entering snaps the bulge under the cursor instead of sweeping in from its old spot.
    if (pointer.inside && !wasInside) {
      this.state.px = (pointer.x - rect.width / 2) / Math.max(1, rect.height);
    }
  };

  private onLeave = (): void => {
    this.pointer.inside = false;
  };
}
