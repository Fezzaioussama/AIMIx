import { BRAND_COLORS } from '../../core/ui/brand';
import { buildPipelineLayout } from './scene/sceneLayout';

const LAYOUT = buildPipelineLayout();
const GRADIENT_ID = 'constellation-gradient';
const HALF_SPAN = 4.5;

/**
 * The hero's constellation as flat SVG: what visitors see while three.js loads, and
 * what they keep when WebGL is missing or they prefer reduced motion. It draws the
 * same layout as the 3D scene, with the brand gradient running left to right
 * (input → deliverable), so nothing jumps when the canvas takes over.
 */
export function ConstellationFallback() {
  const [first, middle, last] = BRAND_COLORS;
  return (
    <svg viewBox="-6 -3.4 12 6.8" className="size-full" preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient
          id={GRADIENT_ID}
          gradientUnits="userSpaceOnUse"
          x1={-HALF_SPAN}
          x2={HALF_SPAN}
          y1="0"
          y2="0"
        >
          <stop offset="0" stopColor={first} />
          <stop offset="0.5" stopColor={middle} />
          <stop offset="1" stopColor={last} />
        </linearGradient>
      </defs>
      <g stroke={`url(#${GRADIENT_ID})`} strokeWidth="0.02" opacity="0.5">
        {LAYOUT.edges.map(({ from, to }) => {
          const [x1, y1] = LAYOUT.nodes[from].position;
          const [x2, y2] = LAYOUT.nodes[to].position;
          return <line key={`${from}-${to}`} x1={x1} y1={-y1} x2={x2} y2={-y2} />;
        })}
      </g>
      <g fill={`url(#${GRADIENT_ID})`}>
        {LAYOUT.nodes.map(({ position: [x, y] }) => (
          <g key={`${x}-${y}`}>
            <circle cx={x} cy={-y} r="0.55" opacity="0.14" />
            <circle cx={x} cy={-y} r="0.19" />
          </g>
        ))}
      </g>
    </svg>
  );
}
