/**
 * The explorer's single page heading and its catalog-loading dock (Atlas
 * design §11; mobile sheets design 2026-10-07 §A.1.11): exactly one <h1>,
 * visually hidden on phones.
 */

import { MOBILE_QUERY, useMediaQuery } from './useMediaQuery';

export function ExplorerHeading() {
  const isMobile = useMediaQuery(MOBILE_QUERY);
  return (
    <h1 className={isMobile ? 'visually-hidden' : undefined}>
      Explore human genetic variation
    </h1>
  );
}

export function ControlsLoading() {
  return (
    <aside className="atlas-controls atlas-controls--loading">
      <p className="atlas-kicker atlas-kicker--brand">
        <span className="brand-name">genomeOS</span> Atlas
      </p>
      <ExplorerHeading />
      <p>Loading the public catalog…</p>
    </aside>
  );
}
