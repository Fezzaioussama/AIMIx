import { useImagePreview } from '../../core/hooks/useImagePreview';

interface PicturePreviewProps {
  /** The picture's path in the user's workspace. */
  path: string;
  /** Sizing and spacing, from the caller. */
  className?: string;
}

/** A picture an agent drew or a user uploaded, shown once loaded; nothing until then. */
export function PicturePreview({ path, className = '' }: PicturePreviewProps) {
  const src = useImagePreview(path);
  if (!src) return null;
  // The file's name follows it, so the image itself is not announced again.
  return (
    <img
      src={src}
      alt=""
      className={`rounded-lg outline-1 -outline-offset-1 outline-white/10 ${className}`}
    />
  );
}
