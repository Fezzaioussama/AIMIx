import { useFrame } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import { AdditiveBlending } from 'three';
import type { Color, Group, Texture } from 'three';

import { coreColor } from './palette';
import type { SceneLayout, SceneNode } from './sceneLayout';

interface NodesProps {
  layout: SceneLayout;
  colors: readonly Color[];
  glow: Texture | null;
}

function AgentCore({ node, color }: { node: SceneNode; color: Color }) {
  return (
    <group position={node.position}>
      <mesh>
        <icosahedronGeometry args={[0.15, 3]} />
        <meshStandardMaterial
          color={coreColor(color)}
          emissive={color}
          emissiveIntensity={1.8}
          metalness={0.72}
          roughness={0.18}
          toneMapped={false}
        />
      </mesh>
      <mesh scale={1.42}>
        <icosahedronGeometry args={[0.15, 1]} />
        <meshBasicMaterial
          color={color}
          wireframe
          transparent
          opacity={0.42}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}

function OrbitalCages({ layout, colors }: Omit<NodesProps, 'glow'>) {
  const cages = useRef<Group>(null);
  useFrame((state, delta) => {
    cages.current?.children.forEach((cage, index) => {
      cage.rotation.y += delta * (0.12 + (index % 3) * 0.025);
      cage.rotation.z = Math.sin(state.clock.elapsedTime * 0.35 + index) * 0.22;
    });
  });
  return (
    <group ref={cages}>
      {layout.nodes.map((node, index) => (
        <group key={`cage-${node.stage}-${node.position.join('-')}`} position={node.position}>
          <mesh rotation={[Math.PI / 2, index * 0.37, 0]}>
            <torusGeometry args={[0.29, 0.008, 6, 40]} />
            <meshBasicMaterial
              color={colors[index]}
              transparent
              opacity={0.5}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
        </group>
      ))}
    </group>
  );
}

/** Each agent is a lit metal-glass core, orbital cage, and soft additive halo. */
export function Nodes({ layout, colors, glow }: NodesProps) {
  const haloPositions = useMemo(
    () => Float32Array.from(layout.nodes.flatMap((node) => [...node.position])),
    [layout],
  );
  const haloColors = useMemo(
    () => Float32Array.from(colors.flatMap((color) => color.toArray())),
    [colors],
  );
  return (
    <>
      {layout.nodes.map((node, index) => (
        <AgentCore
          key={`${node.stage}-${node.position.join('-')}`}
          node={node}
          color={colors[index]}
        />
      ))}
      <OrbitalCages layout={layout} colors={colors} />
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[haloPositions, 3]} />
          <bufferAttribute attach="attributes-color" args={[haloColors, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={3.6}
          sizeAttenuation
          vertexColors
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
