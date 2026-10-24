import { File as FileIcon, FileSpreadsheet, FileText } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import type { FileListing, WorkspaceFile } from '../../core/api/types';
import {
  describeTypes,
  fileIcon,
  fileName,
  folderOf,
  formatBytes,
  withFile,
  withoutFile,
} from './fileFormat';

const file = (path: string, size: number): WorkspaceFile => ({
  path,
  size,
  modified_at: '2026-10-24T10:00:00Z',
  type: path.slice(path.lastIndexOf('.') + 1),
});

const listing: FileListing = {
  files: [file('a.txt', 10), file('reports/b.pdf', 30)],
  used_bytes: 40,
  quota_bytes: 1_000,
  max_file_bytes: 100,
  allowed_extensions: ['.pdf'],
};

describe('fileFormat', () => {
  it('writes sizes in the decimal units the limits use', () => {
    expect(formatBytes(1)).toBe('1 byte');
    expect(formatBytes(999)).toBe('999 bytes');
    expect(formatBytes(1_500)).toBe('1.5 KB');
    expect(formatBytes(48_213)).toBe('48 KB');
    expect(formatBytes(10_000_000)).toBe('10 MB');
    expect(formatBytes(2_500_000_000)).toBe('2.5 GB');
  });

  it('splits a path into its folder and name', () => {
    expect([folderOf('reports/q3/b.pdf'), fileName('reports/q3/b.pdf')]).toEqual([
      'reports/q3',
      'b.pdf',
    ]);
    expect([folderOf('a.txt'), fileName('a.txt')]).toEqual(['', 'a.txt']);
  });

  it('names the accepted types in plain words, once each, the common ones first', () => {
    expect(describeTypes(['.csv', '.docx', '.pdf', '.xml', '.yaml', '.yml'])).toBe(
      'PDF, Word, CSV, YAML and XML',
    );
    expect(describeTypes(['.xml'])).toBe('XML');
  });

  it('picks an icon per type, and a plain file for the rest', () => {
    expect(fileIcon('pdf')).toBe(FileText);
    expect(fileIcon('csv')).toBe(FileSpreadsheet);
    expect(fileIcon('exe')).toBe(FileIcon);
  });

  it('keeps the used storage equal to the sum of the listed sizes', () => {
    const added = withFile(listing, file('a.txt', 25));
    expect(added.files.map((entry) => entry.path)).toEqual(['a.txt', 'reports/b.pdf']);
    expect(added.used_bytes).toBe(55);

    expect(withoutFile(added, 'reports/b.pdf').used_bytes).toBe(25);
  });
});
