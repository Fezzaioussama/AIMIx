import { Link } from 'react-router-dom';

import type { Run } from '../../../core/api/types';
import { Heading } from '../../../core/ui/Heading';
import { isPicture } from '../../files/fileFormat';
import { FileRow } from '../../files/FileRow';
import { PicturePreview } from '../../files/PicturePreview';
import { TEXT_LINK } from './textStyles';
import { useRunFiles } from './useRunFiles';

interface RunFilesProps {
  run: Run;
  level: 2 | 3;
}

/**
 * "Saved during this run": the files that reached the workspace while the run worked,
 * pictures first and shown whole, each with its download. Nothing at all while they
 * load, when there are none, or when they cannot be listed.
 */
export function RunFiles({ run, level }: RunFilesProps) {
  const { files, busyPath, rowError, download } = useRunFiles(run);
  if (!files?.length) return null;
  const headingId = `run-${run.id}-files`;
  return (
    <section aria-labelledby={headingId}>
      <div className="flex items-center justify-between gap-3">
        <Heading level={level} id={headingId} className="text-lg font-semibold text-white">
          Saved during this run
        </Heading>
        <Link to="/files" className={`shrink-0 text-sm ${TEXT_LINK}`}>
          All files<span className="sr-only"> in your workspace</span>
        </Link>
      </div>
      <p className="mt-1 text-sm text-slate-400">
        Files saved to your workspace while this run worked.
      </p>
      <ul className="mt-4 divide-y divide-white/[0.06] rounded-2xl border border-white/10 bg-slate-900/40">
        {files.map((file) => (
          <FileRow
            key={file.path}
            file={file}
            action={busyPath === file.path ? 'download' : undefined}
            error={rowError?.path === file.path ? rowError.message : ''}
            onDownload={() => download(file)}
            preview={
              isPicture(file.type) ? (
                <PicturePreview
                  path={file.path}
                  className="mb-2 max-h-80 w-auto max-w-full rounded-lg object-contain"
                />
              ) : undefined
            }
          />
        ))}
      </ul>
    </section>
  );
}
