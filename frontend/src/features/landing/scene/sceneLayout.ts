/**
 * The hero's "pipeline constellation": agents laid out as the stages of a pipeline,
 * fanning out from one input and converging on one deliverable. Pure data — the
 * WebGL scene and the SVG fallback both draw from it, so they always agree (DRY).
 */

export type Vec3 = readonly [x: number, y: number, z: number];

export interface SceneNode {
  stage: number;
  position: Vec3;
}

export interface SceneEdge {
  from: number;
  to: number;
}

export interface SceneLayout {
  nodes: readonly SceneNode[];
  edges: readonly SceneEdge[];
  stageCount: number;
}

/** Agents per stage: one input, two parallel stages, then back down to one output. */
const STAGE_SIZES = [1, 3, 3, 2, 1] as const;
const SPAN_X = 9;
const SPREAD_Y = 3.4;
const DEPTH_Z = 1.5;

/** A stable pseudo-random value in [-1, 1] — no Math.random, so renders never differ. */
const jitter = (seed: number): number => Math.sin(seed * 12.9898) * 0.999;

function buildNodes(): SceneNode[] {
  const last = STAGE_SIZES.length - 1;
  return STAGE_SIZES.flatMap((size, stage) =>
    Array.from({ length: size }, (_, row): SceneNode => {
      const x = (stage / last - 0.5) * SPAN_X;
      const y = size === 1 ? 0 : (row / (size - 1) - 0.5) * SPREAD_Y;
      const z = jitter(stage * 7 + row * 3 + 1) * DEPTH_Z;
      return { stage, position: [x, y, z] };
    }),
  );
}

/** Every agent hands its result to every agent in the next stage. */
function buildEdges(nodes: readonly SceneNode[]): SceneEdge[] {
  return nodes.flatMap((source, from) =>
    nodes.flatMap((target, to) => (target.stage === source.stage + 1 ? [{ from, to }] : [])),
  );
}

export function buildPipelineLayout(): SceneLayout {
  const nodes = buildNodes();
  return { nodes, edges: buildEdges(nodes), stageCount: STAGE_SIZES.length };
}

/** Where a stage sits along the brand gradient, 0 (input) to 1 (deliverable). */
export const stageProgress = (stage: number, stageCount: number): number =>
  stageCount < 2 ? 0 : stage / (stageCount - 1);

/** Deterministic points scattered behind the constellation (a tiny seeded LCG). */
export function buildStars(count: number): Float32Array {
  const positions = new Float32Array(count * 3);
  let seed = 1337;
  const next = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
  for (let i = 0; i < count; i += 1) {
    positions[i * 3] = (next() - 0.5) * 30;
    positions[i * 3 + 1] = (next() - 0.5) * 16;
    positions[i * 3 + 2] = -3 - next() * 12;
  }
  return positions;
}
