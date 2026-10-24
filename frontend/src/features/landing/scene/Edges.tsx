import { useFrame } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import { AdditiveBlending, QuadraticBezierCurve3, Vector3 } from 'three';
import type { BufferGeometry, Color, Texture } from 'three';

import { BRAND_HIGHLIGHT } from '../../../core/ui/brand';
import type { SceneLayout } from './sceneLayout';

interface EdgesProps {
  layout: SceneLayout;
  colors: readonly Color[];
  glow: Texture | null;
}

const PULSES_PER_EDGE = 2;

function buildCurves(layout: SceneLayout): QuadraticBezierCurve3[] {
  return layout.edges.map(({ from, to }, index) => {
    const start = new Vector3(...layout.nodes[from].position);
    const end = new Vector3(...layout.nodes[to].position);
    const midpoint = start.clone().lerp(end, 0.5);
    midpoint.z += 0.45 + (index % 3) * 0.18;
    return new QuadraticBezierCurve3(start, midpoint, end);
  });
}

function placePulses(
  curves: readonly QuadraticBezierCurve3[],
  positions: Float32Array,
  time: number,
) {
  curves.forEach((curve, edgeIndex) => {
    const speed = 0.16 + (edgeIndex % 5) * 0.035;
    for (let pulse = 0; pulse < PULSES_PER_EDGE; pulse += 1) {
      const progress = (time * speed + edgeIndex * 0.37 + pulse / PULSES_PER_EDGE) % 1;
      curve.getPoint(progress).toArray(positions, (edgeIndex * PULSES_PER_EDGE + pulse) * 3);
    }
  });
}

function FlowTubes({ layout, colors, curves }: EdgesProps & { curves: QuadraticBezierCurve3[] }) {
  return (
    <group>
      {curves.map((curve, index) => (
        <mesh key={`${layout.edges[index].from}-${layout.edges[index].to}`}>
          <tubeGeometry args={[curve, 28, 0.012, 5, false]} />
          <meshBasicMaterial
            color={colors[layout.edges[index].from]}
            transparent
            opacity={0.34}
            depthWrite={false}
            blending={AdditiveBlending}
            toneMapped={false}
          />
        </mesh>
      ))}
    </group>
  );
}

/** Curved conduits between agents, with bright signals flowing downstream. */
export function Edges({ layout, colors, glow }: EdgesProps) {
  const pulseGeometry = useRef<BufferGeometry>(null);
  const curves = useMemo(() => buildCurves(layout), [layout]);
  const pulsePositions = useMemo(
    () => new Float32Array(layout.edges.length * PULSES_PER_EDGE * 3),
    [layout],
  );
  useFrame((state) => {
    const geometry = pulseGeometry.current;
    if (!geometry) return;
    placePulses(curves, pulsePositions, state.clock.elapsedTime);
    geometry.attributes.position.needsUpdate = true;
  });
  return (
    <>
      <FlowTubes layout={layout} colors={colors} glow={glow} curves={curves} />
      <points frustumCulled={false}>
        <bufferGeometry ref={pulseGeometry}>
          <bufferAttribute attach="attributes-position" args={[pulsePositions, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={0.5}
          sizeAttenuation
          color={BRAND_HIGHLIGHT}
          transparent
          depthWrite={false}
          blending={AdditiveBlending}
          map={glow ?? undefined}
          toneMapped={false}
        />
      </points>
    </>
  );
}
