# GenomeOS Map UI

The P5 client implements design §11 with MapLibre navigation and independent deck.gl evidence
layers. The static export is mounted at `/map/` by the FastAPI container, keeping browser reads
same-origin with the P4 API.

```bash
npm ci
npm run typecheck
npm test
npm run build
```

Run `npm run dev` for frontend work. A standalone dev server needs the P4 endpoints available on
the same origin; the container is the authoritative integrated runtime.

Layer availability comes from the immutable artifact manifest. A missing observation or burden
artifact disables that control; the client never substitutes a different dataset. Scientific
resolution is selected only from the resolutions published in the manifest, so map zoom cannot
invent finer data.
