import { Canvas, useFrame } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import { MathUtils } from 'three';
import type { CanvasTexture, Group } from 'three';

import { Backdrop } from './Backdrop';
import { Edges } from './Edges';
import { createGlowTexture } from './glowTexture';
import { Nodes } from './Nodes';
import { brandColorAt } from './palette';
import { buildPipelineLayout, stageProgress } from './sceneLayout';
import { useScenePointer } from './useScenePointer';

export type SceneFrameloop = 'always' | 'never';

const CAMERA = { position: [0.35, 0.25, 10.5] as [number, number, number], fov: 44 };
// Cap the pixel ratio: the scene is soft glow, so retina sharpness is not worth the fill cost.
const DPR: [number, number] = [1, 1.5];

/**
 * The glow sprite, built during render rather than in an effect: a point material
 * only samples a `map` that existed when it was first compiled, so a texture that
 * arrives a frame late leaves every halo a flat square. Freed on unmount.
 */
function useGlowTexture(): CanvasTexture | null {
  const texture = useMemo(createGlowTexture, []);
  useEffect(() => () => texture?.dispose(), [texture]);
  return texture;
}

function Constellation() {
  const layout = useMemo(buildPipelineLayout, []);
  const colors = useMemo(
    () => layout.nodes.map((node) => brandColorAt(stageProgress(node.stage, layout.stageCount))),
    [layout],
  );
  const glow = useGlowTexture();
  const pointer = useScenePointer();
  const group = useRef<Group>(null);

  useFrame((state, delta) => {
    const target = group.current;
    if (!target) return;
    const time = state.clock.elapsedTime;
    // Narrow viewports shrink the whole constellation so it never clips.
    target.scale.setScalar(MathUtils.clamp(state.viewport.width / 10.5, 0.42, 1.15));
    target.rotation.y = MathUtils.damp(
      target.rotation.y,
      pointer.current.x * 0.4 + Math.sin(time * 0.25) * 0.2,
      3,
      delta,
    );
    target.rotation.x = MathUtils.damp(target.rotation.x, pointer.current.y * 0.18, 3, delta);
    target.position.y = Math.sin(time * 0.7) * 0.15;
  });

  return (
    <group ref={group}>
      <ambientLight intensity={0.35} />
      <pointLight position={[-4, 3, 4]} color="#22d3ee" intensity={18} distance={12} />
      <pointLight position={[4, -1, 3]} color="#d946ef" intensity={20} distance={12} />
      <Edges layout={layout} colors={colors} glow={glow} />
      <Nodes layout={layout} colors={colors} glow={glow} />
      <Backdrop />
    </group>
  );
}

/**
 * The hero's 3D pipeline constellation. Default export so the page can lazy-load
 * three.js; `frameloop` lets the parent stop rendering when the hero is off-screen
 * ('never') or the visitor paused it ('demand').
 */
export default function PipelineScene({ frameloop }: { frameloop: SceneFrameloop }) {
  return (
    <Canvas
      dpr={DPR}
      camera={CAMERA}
      frameloop={frameloop}
      gl={{ alpha: true, antialias: true, powerPreference: 'high-performance' }}
    >
      <fog attach="fog" args={['#050611', 11, 25]} />
      <Constellation />
    </Canvas>
  );
}
