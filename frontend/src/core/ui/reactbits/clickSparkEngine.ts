export interface SparkOptions {
  color: string;
  count: number;
  /** How far, in CSS pixels, the sparks fly from the click. */
  radius: number;
  /** Starting length of each spark line. */
  size: number;
  /** Lifetime of one burst in milliseconds. */
  duration: number;
}

export interface SparkEngine {
  burst: (clientX: number, clientY: number) => void;
  dispose: () => void;
}

interface Spark {
  x: number;
  y: number;
  angle: number;
  start: number;
}

/** Match the backing store to the element's CSS size and pixel ratio. */
function fitCanvas(canvas: HTMLCanvasElement, context: CanvasRenderingContext2D): DOMRect {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.round(rect.width * ratio);
  const height = Math.round(rect.height * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return rect;
}

/** Draws one spark; returns false once it has burnt out. */
function drawSpark(
  context: CanvasRenderingContext2D,
  spark: Spark,
  now: number,
  options: SparkOptions,
): boolean {
  const progress = (now - spark.start) / options.duration;
  if (progress >= 1) return false;
  const eased = 1 - (1 - progress) ** 3;
  const distance = eased * options.radius;
  const length = options.size * (1 - eased);
  const cos = Math.cos(spark.angle);
  const sin = Math.sin(spark.angle);
  context.beginPath();
  context.moveTo(spark.x + distance * cos, spark.y + distance * sin);
  context.lineTo(spark.x + (distance + length) * cos, spark.y + (distance + length) * sin);
  context.stroke();
  return true;
}

/**
 * Canvas side of ClickSpark: bursts of short lines flying outward from a point.
 * The frame loop only runs while sparks are alive. Returns null without a 2D context.
 */
export function createSparkEngine(
  canvas: HTMLCanvasElement,
  options: SparkOptions,
): SparkEngine | null {
  const context = canvas.getContext('2d');
  if (!context) return null;
  let sparks: Spark[] = [];
  let raf = 0;

  const draw = (now: number) => {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = options.color;
    context.lineWidth = 2;
    context.lineCap = 'round';
    sparks = sparks.filter((spark) => drawSpark(context, spark, now, options));
    raf = sparks.length > 0 ? requestAnimationFrame(draw) : 0;
  };

  return {
    burst(clientX, clientY) {
      const rect = fitCanvas(canvas, context);
      const start = performance.now();
      for (let index = 0; index < options.count; index++) {
        const angle = (2 * Math.PI * index) / options.count;
        sparks.push({ x: clientX - rect.left, y: clientY - rect.top, angle, start });
      }
      if (!raf) raf = requestAnimationFrame(draw);
    },
    dispose() {
      cancelAnimationFrame(raf);
      sparks = [];
    },
  };
}
