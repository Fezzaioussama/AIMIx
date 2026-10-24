import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react';
import type { PointerEvent, ReactNode } from 'react';

interface TiltCardProps {
  children: ReactNode;
  /** Largest rotation, in degrees, when the pointer is at an edge. */
  maxTilt?: number;
  className?: string;
}

const SPRING = { stiffness: 220, damping: 22, mass: 0.6 } as const;

/**
 * Leans its children toward the pointer in 3D. Purely a hover flourish: touch input
 * and prefers-reduced-motion leave the card flat, and nothing here is interactive.
 */
export function TiltCard({ children, maxTilt = 7, className = '' }: TiltCardProps) {
  const reduceMotion = useReducedMotion();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotateX = useSpring(useTransform(y, [-0.5, 0.5], [maxTilt, -maxTilt]), SPRING);
  const rotateY = useSpring(useTransform(x, [-0.5, 0.5], [-maxTilt, maxTilt]), SPRING);

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (reduceMotion || event.pointerType === 'touch') return;
    const rect = event.currentTarget.getBoundingClientRect();
    x.set((event.clientX - rect.left) / rect.width - 0.5);
    y.set((event.clientY - rect.top) / rect.height - 0.5);
  }

  function reset() {
    x.set(0);
    y.set(0);
  }

  return (
    <div className={`[perspective:1000px] ${className}`}>
      <motion.div
        style={{ rotateX, rotateY, transformStyle: 'preserve-3d' }}
        onPointerMove={handlePointerMove}
        onPointerLeave={reset}
        className="h-full will-change-transform"
      >
        {children}
      </motion.div>
    </div>
  );
}
