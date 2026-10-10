/**
 * The data provenance credit (Atlas design §11). On phones it shortens to
 * "Data: genomeOS" and docks under the Cesium credits as one wrapping credit
 * block above the active sheet (mobile sheets design 2026-10-07 §A.1.7), and
 * ends with the cookie settings icon in a build that loads analytics (#422).
 */

import { AtlasCookieSettings } from './AtlasCookieSettings';

export function AtlasDataCredit() {
  return (
    <p className="atlas-data-credit">
      <span className="atlas-data-credit__long">
        Scientific data and provenance:{' '}
      </span>
      <a
        href="https://huggingface.co/datasets/bschilder/genomeos-data"
        target="_blank"
        rel="noreferrer"
      >
        <span className="atlas-data-credit__short">Data: </span>
        <span className="brand-name">genomeOS</span>
        <span className="atlas-data-credit__long"> public dataset</span>
      </a>
      <AtlasCookieSettings placement="credit" />
    </p>
  );
}
