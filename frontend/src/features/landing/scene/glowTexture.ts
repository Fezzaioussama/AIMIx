import { CanvasTexture } from 'three';

const SIZE = 128;

/**
 * A soft white radial falloff. Used as the sprite of every glowing point; the point
 * material's vertex colours tint it to the brand palette. Returns null where no 2D
 * canvas exists. The caller owns the texture and must `dispose()` it.
 */
export function createGlowTexture(): CanvasTexture | null {
  const canvas = document.createElement('canvas');
  canvas.width = SIZE;
  canvas.height = SIZE;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const half = SIZE / 2;
  const gradient = context.createRadialGradient(half, half, 0, half, half, half);
  gradient.addColorStop(0, 'rgba(255,255,255,1)');
  gradient.addColorStop(0.18, 'rgba(255,255,255,0.8)');
  gradient.addColorStop(0.45, 'rgba(255,255,255,0.28)');
  gradient.addColorStop(0.75, 'rgba(255,255,255,0.06)');
  gradient.addColorStop(1, 'rgba(255,255,255,0)');
  context.fillStyle = gradient;
  context.fillRect(0, 0, SIZE, SIZE);
  return new CanvasTexture(canvas);
}
