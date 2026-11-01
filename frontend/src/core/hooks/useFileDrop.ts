import { useEffect, useState, type DragEvent } from 'react';

function carriesFiles(event: { dataTransfer: DataTransfer | null }): boolean {
  return event.dataTransfer?.types.includes('Files') ?? false;
}

/** A file dropped just beside a drop zone would otherwise replace the page with itself. */
function useDropGuard() {
  useEffect(() => {
    const hold = (event: globalThis.DragEvent) => {
      if (carriesFiles(event)) event.preventDefault();
    };
    window.addEventListener('dragover', hold);
    window.addEventListener('drop', hold);
    return () => {
      window.removeEventListener('dragover', hold);
      window.removeEventListener('drop', hold);
    };
  }, []);
}

/**
 * A drop zone for files: `dragging` while files are held over it, `onFiles` with the ones
 * dropped; while not `enabled` it stays dark and drops are ignored. Anything else dragged
 * (text, say) keeps the browser's own behaviour, and while the zone is on screen a file
 * dropped just beside it is held instead of replacing the page.
 */
export function useFileDrop(onFiles: (files: File[]) => void, enabled = true) {
  const [dragging, setDragging] = useState(false);
  useDropGuard();
  return {
    dragging: dragging && enabled,
    zone: {
      onDragOver(event: DragEvent<HTMLElement>) {
        if (!carriesFiles(event)) return;
        event.preventDefault();
        setDragging(true);
      },
      onDragLeave(event: DragEvent<HTMLElement>) {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
      },
      onDrop(event: DragEvent<HTMLElement>) {
        if (!carriesFiles(event)) return;
        event.preventDefault();
        setDragging(false);
        const files = [...event.dataTransfer.files];
        if (enabled && files.length > 0) onFiles(files);
      },
    },
  };
}
