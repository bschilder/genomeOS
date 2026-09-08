/** Download helpers for reviewed external records in Atlas design §11. */

import type { ExternalInfo } from './contracts';

function safeFilenamePart(value: string): string {
  return value.replaceAll(/[^A-Za-z0-9._-]+/g, '-');
}

export function externalInfoDownloadFilename(info: ExternalInfo): string {
  return [
    info.query.normalized_variant_id,
    info.source,
    info.source_release,
    'json',
  ]
    .map(safeFilenamePart)
    .join('.');
}

export function externalInfoDownloadText(info: ExternalInfo): string {
  return `${JSON.stringify(info, null, 2)}\n`;
}

export function downloadExternalInfo(info: ExternalInfo): void {
  const blob = new Blob([externalInfoDownloadText(info)], {
    type: 'application/json;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.download = externalInfoDownloadFilename(info);
  anchor.href = url;
  anchor.click();
  URL.revokeObjectURL(url);
}
