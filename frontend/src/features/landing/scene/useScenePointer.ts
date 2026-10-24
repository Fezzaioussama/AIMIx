import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';

/**
 * The pointer's position over the window, each axis in -1..1. Window-level (not the
 * canvas) because the hero's text sits on top of the scene and would swallow canvas
 * events; a ref, so moving the pointer never re-renders React. `pointermove` also
 * covers touch drags.
 */
export function useScenePointer(): RefObject<{ x: number; y: number }> {
  const pointer = useRef({ x: 0, y: 0 });

  useEffect(() => {
    function handleMove(event: PointerEvent) {
      pointer.current.x = (event.clientX / window.innerWidth) * 2 - 1;
      pointer.current.y = (event.clientY / window.innerHeight) * 2 - 1;
    }
    window.addEventListener('pointermove', handleMove, { passive: true });
    return () => window.removeEventListener('pointermove', handleMove);
  }, []);

  return pointer;
}
