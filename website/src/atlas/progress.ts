/** Honest transfer and render progress values for Atlas design §11. */

export interface TransferProgress {
  loadedBytes: number;
  totalBytes: number | null;
}

export type TransferProgressListener = (progress: TransferProgress) => void;

export type ExplorerLoadStatus =
  'loading catalog' | 'loading artifact' | 'validating' | 'rendering' | 'ready';

export interface ExplorerActivity {
  detail: string;
  label: string;
  progress: number | null;
}

export function aggregateTransferProgress(
  transfers: readonly TransferProgress[],
): number | null {
  if (
    transfers.length === 0 ||
    transfers.some(({ totalBytes }) => totalBytes === null || totalBytes <= 0)
  )
    return null;
  const totalBytes = transfers.reduce(
    (total, transfer) => total + (transfer.totalBytes ?? 0),
    0,
  );
  const loadedBytes = transfers.reduce(
    (total, transfer) =>
      total +
      Math.min(
        Math.max(0, transfer.loadedBytes),
        transfer.totalBytes ?? Number.POSITIVE_INFINITY,
      ),
    0,
  );
  return Math.min(1, loadedBytes / totalBytes);
}

export function createTransferProgressTracker<Key extends string>(
  keys: readonly Key[],
  report: (progress: number | null) => void,
): (key: Key) => TransferProgressListener {
  const transfers = new Map<Key, TransferProgress>(
    keys.map((key) => [key, { loadedBytes: 0, totalBytes: null }]),
  );
  return (key) => (transfer) => {
    transfers.set(key, transfer);
    report(aggregateTransferProgress([...transfers.values()]));
  };
}
