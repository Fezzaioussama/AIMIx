import { useFrame } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import type { Group, Points } from 'three';

import { BRAND_COLORS } from '../../../core/ui/brand';
import { buildStars } from './sceneLayout';

const STAR_COUNT = 320;
const RING_RADII = [4.5, 5.9, 7.2] as const;

/** Deep-space depth cues: a slowly turning starfield and two tilted orbit rings. */
export function Backdrop() {
  const stars = useRef<Points>(null);
  const rings = useRef<Group>(null);
  const starPositions = useMemo(() => buildStars(STAR_COUNT), []);

  useFrame((_, delta) => {
    if (stars.current) stars.current.rotation.y += delta * 0.012;
    if (rings.current) rings.current.rotation.z += delta * 0.05;
  });

  return (
    <>
      <points ref={stars}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[starPositions, 3]} />
        </bufferGeometry>
        <pointsMaterial size={0.052} sizeAttenuation color="#dbeafe" transparent opacity={0.58} />
      </points>
      <group ref={rings} rotation={[1.15, 0.2, 0]}>
        {RING_RADII.map((radius, index) => (
          <mesh key={radius} rotation={[0, 0, index]}>
            <torusGeometry args={[radius, 0.006, 8, 160]} />
            <meshBasicMaterial color={BRAND_COLORS[index + 1]} transparent opacity={0.2} />
          </mesh>
        ))}
      </group>
      <gridHelper
        args={[24, 24, '#312e81', '#172554']}
        position={[0, -3.45, -1.8]}
        rotation={[0, 0, 0]}
      />
      <mesh position={[0, 0, -5]}>
        <circleGeometry args={[5.5, 64]} />
        <meshBasicMaterial color="#312e81" transparent opacity={0.06} depthWrite={false} />
      </mesh>
    </>
  );
}
