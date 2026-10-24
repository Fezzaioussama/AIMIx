import { useInView, useReducedMotion } from 'motion/react';
import { lazy, Suspense, useRef, useState } from 'react';

import { hasWebGL } from '../../core/ui/webgl';
import { ConstellationFallback } from './ConstellationFallback';
import { SceneBoundary } from './SceneBoundary';

// three.js is the heaviest dependency; keep it out of the main bundle.
const PipelineScene = lazy(() => import('./scene/PipelineScene'));

// Fades the scene out toward the edges so the hero copy stays readable on top of it.
const SCENE_MASK =
  'absolute inset-y-0 -right-1/2 -left-1/2 opacity-70 [mask-image:radial-gradient(ellipse_58%_64%_at_58%_42%,black_34%,transparent_78%)] lg:right-[-10%] lg:left-[34%] lg:opacity-100 lg:[mask-image:radial-gradient(ellipse_70%_68%_at_56%_42%,black_32%,transparent_82%)]';

// A dark pool behind the headline: the glow stays visible around the words, not under them.
const SCRIM =
  'absolute inset-0 bg-[radial-gradient(ellipse_54%_38%_at_50%_34%,rgba(5,6,17,0.82),transparent_78%)] lg:bg-[linear-gradient(90deg,#050611_4%,rgba(5,6,17,0.92)_34%,rgba(5,6,17,0.28)_68%,#050611_100%)]';

/**
 * The hero's decorative 3D backdrop. Real WebGL only where it is available and the
 * visitor has not asked for reduced motion; otherwise the flat constellation. It
 * stops rendering while off-screen. The parent must be `relative`.
 */
export function HeroScene() {
  const reduceMotion = useReducedMotion();
  const [webgl] = useState(hasWebGL);
  const container = useRef<HTMLDivElement>(null);
  const inView = useInView(container);

  const flat = <ConstellationFallback />;
  const live = webgl && !reduceMotion;

  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 h-[50rem] sm:h-[54rem]">
      <div ref={container} aria-hidden="true" className={SCENE_MASK}>
        {live ? (
          <SceneBoundary fallback={flat}>
            <Suspense fallback={flat}>
              <PipelineScene frameloop={inView ? 'always' : 'never'} />
            </Suspense>
          </SceneBoundary>
        ) : (
          flat
        )}
      </div>
      <div aria-hidden="true" className={SCRIM} />
    </div>
  );
}
