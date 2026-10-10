/**
 * SHA-256 of a GOSA container for Atlas design §11 and fast-load design §B.6.3. The site is also
 * served over plain HTTP, where `crypto.subtle` does not exist, so this uses the exact-pinned
 * pure-JS `@noble/hashes`.
 */

import { sha256 } from '@noble/hashes/sha2.js';
import { bytesToHex } from '@noble/hashes/utils.js';

export function sha256Hex(bytes: Uint8Array): string {
  return bytesToHex(sha256(bytes));
}
