# genomeOS Public Documentation Website Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a distinctive, accessible Astro/Starlight documentation site that explains genomeOS, organizes contributors into forming working groups, and deploys reproducibly to GitHub Pages at `https://genome-os.org`.

**Architecture:** Keep the static Node application isolated under `website/`. Custom Astro routes provide the narrative public pages, while Starlight renders searchable technical documentation under `/docs/`; both consume one token system and base-aware URL helper. GitHub Actions validates both the custom-domain root and `/genomeOS` fallback builds, then deploys only merges to `main`.

**Tech Stack:** Node.js 24; Astro 7.3.1; Starlight 0.42.0; TypeScript 6.0.3; Vitest 5.0.0; Playwright 1.63.0; axe-core Playwright 4.13.0; local Fontsource Raleway/Figtree 5.3.0; GitHub Pages Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-docs-website-design.md`

## Global Constraints

- Production canonical origin is exactly `https://genome-os.org`; the repository Pages setting, not a `CNAME` file, owns the custom domain.
- The fallback build uses `https://bschilder.github.io` with base `/genomeOS` and must contain no root-relative link or asset failures.
- Use exact dependency versions and commit `website/package-lock.json`; clean installation is `npm ci` on Node 24.
- The memorable visual element is the existing `docs/images/genomeos-banner.png`; lower sections stay restrained and do not become a rounded-card SaaS grid.
- Raleway Variable is display type and Figtree Variable is reading/interface type; both are bundled locally.
- All capability claims are visibly marked `Available now`, `In active development`, or `Future exploration`.
- Never present conversational access, personal-genome upload, the product map, or the cell atlas as shipped.
- Measured observations, modeled estimates, and unknown regions remain visibly distinct; geography is never presented as an individual's genotype.
- Internal absolute links are built only through `sitePath()`.
- No analytics, cookies, forms, accounts, remote fonts, or third-party JavaScript.
- All routes work without client JavaScript except Starlight's progressive documentation features.
- Respect keyboard use, visible focus, semantic landmarks, WCAG 2.2 AA contrast, 200% zoom, and `prefers-reduced-motion`.
- Before every commit or push, run `python scripts/check_private_files.py` and inspect `git diff --cached --name-only`.
- Every code/configuration change runs `python scripts/smoke.py`; pre-PR verification runs all commands required by `AGENTS.md`.

## Approved feedback amendments — 2026-09-06

These changes supersede the earlier homepage details in Tasks 2 and 3:

- Lead with the higher-order mission: make human genetic diversity useful for screening, medicine,
  discovery, and more representative research. Explain why genomeOS exists, its open-source global
  community model, and its public-good purpose before describing implementation.
- Replace the `Measured / Estimated / Unknown` homepage block with corpus-scale statistics computed
  from pinned source data: 4,392 variant or allele identifiers, 6.69 million participant records,
  and two disease reference corpora. Link and expand every named source acronym at first use. Use
  lining, tabular numerals for metric typography.
- Add potential applications grounded in Discussion #1. Follow the introductory material with a
  plain-language three-stage process: aggregate evidence; model per-variant frequency and supported
  disease burden using Bayesian, geometric, or other defensible methods; build the public interface.
- Add three generated, style-matched visual guides for variation across Earth, genome organization
  inside the cell, and the bridge between those scales. Commit optimized WebP files; their role is
  conceptual navigation, not scientific evidence.
- Make GitHub Discussions, Issues, and the project board large, inviting actions on the homepage.
  Retain the GitHub icon in global navigation.
- Add `/app/` as a work-in-progress preview that embeds the current Cloud Run diagnostic. Describe
  its synthetic test data and limitations in ordinary language; do not expose unexplained P0–P5
  project shorthand on any introductory page.
- Raise public typography to an 18px root and at least 19px body copy. Add scroll reveals, hero
  parallax, a progress indicator, application spotlights, and hover/focus movement, with complete
  reduced-motion fallbacks.
- Treat the site as a first-time introduction everywhere: expand scientific acronyms on first use,
  translate project codes before displaying them in technical docs, and replace internal terms such
  as “read path,” “artifact,” and milestone codes in public-facing copy.

---

### Task 1: Reproducible Astro/Starlight foundation

**Files:**

- Create: `website/package.json`
- Create: `website/package-lock.json`
- Create: `website/.nvmrc`
- Create: `website/astro.config.mjs`
- Create: `website/tsconfig.json`
- Create: `website/src/content.config.ts`
- Create: `website/src/lib/paths.ts`
- Create: `website/tests/paths.test.ts`
- Modify: `.gitignore`

**Interfaces:**

- Consumes: `SITE_URL`, `BASE_PATH`, and `OUT_DIR` environment variables at the Astro composition boundary.
- Produces: `sitePath(path: string, base?: string): string`, a statically prerendered Starlight integration, and exact npm scripts used by every later task.

- [ ] **Step 1: Add the exact Node manifest and configuration boundary**

Create a manifest with `type: "module"`, `engines.node: "24.x"`, and these exact dependencies: `astro@7.3.1`, `@astrojs/starlight@0.42.0`, `@astrojs/sitemap@3.7.4`, `@fontsource-variable/raleway@5.3.0`, and `@fontsource-variable/figtree@5.3.0`. Add exact dev dependencies `@astrojs/check@0.9.10`, `typescript@6.0.3`, `vitest@5.0.0`, `@playwright/test@1.63.0`, `@axe-core/playwright@4.13.0`, `prettier@3.9.6`, and `prettier-plugin-astro@0.14.1`.

Define scripts for `dev`, `build`, `build:fallback`, `preview`, `check`, `format:check`, `test`, `test:e2e`, `check:links`, and `capture`. Add `website/node_modules/`, `website/dist/`, `website/dist-fallback/`, and `website/test-results/` to `.gitignore`.

- [ ] **Step 2: Install reproducibly**

Run:

```bash
cd website
npm install --save-exact
```

Expected: `package-lock.json` is generated with no floating direct dependency versions. Subsequent setup uses `npm ci` only.

- [ ] **Step 3: Write the failing base-path unit tests**

```ts
import { describe, expect, it } from "vitest";
import { sitePath } from "../src/lib/paths";

describe("sitePath", () => {
  it("keeps a root deployment rooted once", () => {
    expect(sitePath("/working-groups/", "/")).toBe("/working-groups/");
  });

  it("prefixes a project-site deployment exactly once", () => {
    expect(sitePath("/working-groups/", "/genomeOS/")).toBe(
      "/genomeOS/working-groups/",
    );
  });

  it("preserves query strings and fragments", () => {
    expect(sitePath("/contribute/?status=ready#start", "/genomeOS/")).toBe(
      "/genomeOS/contribute/?status=ready#start",
    );
  });
});
```

- [ ] **Step 4: Run the tests and verify RED**

Run: `cd website && npm test -- tests/paths.test.ts`

Expected: FAIL because `src/lib/paths.ts` does not exist.

- [ ] **Step 5: Implement the minimal URL helper and Astro config**

Implement `sitePath()` by stripping leading slashes from the requested path, normalizing the supplied base to one leading and trailing slash, and joining the two without touching the query or fragment. Configure Astro from `SITE_URL ?? 'https://genome-os.org'`, `BASE_PATH ?? '/'`, and `OUT_DIR ?? 'dist'`; set `trailingSlash: 'always'`, register Starlight before sitemap, and configure Starlight's content sidebar under `/docs/`.

- [ ] **Step 6: Verify GREEN and type-check**

Run:

```bash
cd website
npm test -- tests/paths.test.ts
npm run check
```

Expected: all path tests pass and Astro reports no errors.

- [ ] **Step 7: Commit the foundation**

Stage only Task 1 files, run the privacy gate, inspect staged paths, and commit:

```bash
git commit -m "build: add the reproducible Astro site foundation"
```

---

### Task 2: Shared orbital-observatory shell and first meaningful homepage preview

**Files:**

- Create: `website/public/favicon.svg`
- Create: `website/public/images/genomeos-banner.png` (mechanical copy of `docs/images/genomeos-banner.png`)
- Create: `website/src/styles/tokens.css`
- Create: `website/src/styles/global.css`
- Create: `website/src/components/GitHubLink.astro`
- Create: `website/src/components/SiteHeader.astro`
- Create: `website/src/components/SiteFooter.astro`
- Create: `website/src/components/Hero.astro`
- Create: `website/src/components/EvidenceStates.astro`
- Create: `website/src/layouts/SiteLayout.astro`
- Create: `website/src/pages/index.astro`
- Create: `website/tests/home.test.ts`

**Interfaces:**

- Consumes: `sitePath()`, local banner and fonts, canonical `Astro.url`, and static page metadata.
- Produces: `SiteLayout` props `{ title: string; description: string; imageAlt?: string }`, a shared semantic header/footer, accessible repository link, and a recognizable homepage first viewport.

- [ ] **Step 1: Write the failing homepage contract test**

Create a Vitest test that runs the production build once in a temporary output directory, reads `index.html`, and asserts independently derived behavior:

```ts
expect(html).toContain("<h1>Explore genomes across the world.</h1>");
expect(html).toMatch(
  /Measured here[\s\S]*Estimated there[\s\S]*Never confused/,
);
expect(html).toContain('aria-label="View genomeOS on GitHub"');
expect(html).toContain("https://github.com/bschilder/genomeOS");
expect(html).toContain("Skip to main content");
```

The production break caught is a homepage that compiles but loses its primary claim, evidence distinction, repository route, or keyboard bypass.

- [ ] **Step 2: Verify RED**

Run: `cd website && npm test -- tests/home.test.ts`

Expected: FAIL because no homepage or shared shell exists.

- [ ] **Step 3: Implement the token system and layout**

Define the exact palette from spec §5.1 as CSS custom properties. Import local Figtree and Raleway variable fonts in `global.css`; set a maximum reading width of approximately 76 characters, explicit focus-visible outlines, skip-link behavior, responsive navigation, and reduced-motion rules.

`SiteLayout` must emit unique title/description, canonical URL, Open Graph and X metadata using `/images/genomeos-banner.png`, one skip link, `SiteHeader`, `<main id="main-content">`, and `SiteFooter`.

- [ ] **Step 4: Implement the first coherent homepage slice**

Build the full banner-backed hero, two direct actions (`Find your place` and `Understand the project`), and `EvidenceStates` with three redundant presentations:

- Measured — a source-anchored observation marker.
- Estimated — a model surface with uncertainty.
- Unknown — a visibly hatched refusal where evidence is insufficient.

Use a single slow background-position drift for the hero, disabled by `prefers-reduced-motion`. Do not add section reveal animations or generic cards.

- [ ] **Step 5: Verify GREEN and open the first meaningful preview**

Run:

```bash
cd website
npm test -- tests/home.test.ts
npm run dev -- --host 127.0.0.1
```

From another process, request the exact printed local URL and require HTTP 200. Open that URL in the user's browser only after the test, compiler, and request succeed. Keep the development server alive for the remaining tasks.

- [ ] **Step 6: Commit the first slice**

Run the site checks, repository smoke test, privacy gate, and staged-path inspection, then commit:

```bash
git commit -m "feat: establish the genomeOS public site shell"
```

---

### Task 3: Complete public narrative and contributor routes

**Files:**

- Create: `website/src/components/Callout.astro`
- Create: `website/src/components/ContributionFlow.astro`
- Create: `website/src/components/StatusBand.astro`
- Create: `website/src/components/WorkingGroup.astro`
- Create: `website/src/pages/project.astro`
- Create: `website/src/pages/working-groups.astro`
- Create: `website/src/pages/contribute.astro`
- Expand: `website/src/pages/index.astro`
- Create: `website/tests/content.test.ts`

**Interfaces:**

- Consumes: `SiteLayout`, `sitePath()`, GitHub issue/search/project/discussion URLs, and the claims in `docs/overview.md` plus `docs/scientific-engineering-objectives.md`.
- Produces: four complete public routes, reusable working-group and capability-state presentations, and a six-step contribution path.

- [ ] **Step 1: Write failing content-state tests**

Build the site and assert rendered user-visible behavior rather than source text. Check all four routes exist, each has one `h1`, and the rendered output includes:

```ts
expect(home).toMatch(
  /Available now[\s\S]*In active development[\s\S]*Future exploration/,
);
expect(groups).toMatch(/Data[\s\S]*Modeling[\s\S]*Product &amp; Experience/);
expect(groups).toContain("geometric deep learning");
expect(groups).toContain("Brian");
expect(groups).toMatch(
  /Future exploration[\s\S]*privacy[\s\S]*consent[\s\S]*governance/,
);
expect(contribute).toContain("Discussion #76");
expect(contribute).toContain("mention the original issue author");
expect(contribute).toContain("Ready");
```

The break caught is an attractive site that drops the project's operating guidance or turns future ideas into current claims.

- [ ] **Step 2: Verify RED**

Run: `cd website && npm test -- tests/content.test.ts`

Expected: FAIL because the routes and capability bands are absent.

- [ ] **Step 3: Complete the homepage narrative**

Add the plain-language HbS anchor, multi-scale vision, forming working-group entry points, contribution sequence, capability status band, and final actions. State directly that geography describes population evidence and does not predict an individual's genotype.

- [ ] **Step 4: Implement the Project route**

Explain the problem, Earth atlas, cellular atlas, eventual bridge, audiences, six safeguards, P0–P5, HbS/G6PD/screening parity bar, and a status section dated September 2026. Link each detailed claim to the authoritative repository document.

- [ ] **Step 5: Implement Working groups**

Mark all groups as forming. Include the exact Data, Modeling, and Product & Experience scopes in spec §3.3, `Good fit if…` guidance, relevant `skill:*` issue filters, and an invitation to suggest another direction. State that Brian leads the Bayesian modeling line without implying that Bayesian modeling exhausts the group.

- [ ] **Step 6: Implement Contribute**

Render the genuine numbered sequence from spec §3.4. Explain board statuses, `type:*`, `P*:`, `skill:*`, `priority:*`, milestones, `wants-expert-review`, `needs-human-decision`, issue search, and substantive-update author mentions. Link Discussion #76, Project 8, Issue #65, the new-issue chooser, and pull-request list.

- [ ] **Step 7: Verify GREEN and responsive semantics**

Run:

```bash
cd website
npm test
npm run check
npm run format:check
```

Expected: all contract tests pass with no compiler or formatter errors.

- [ ] **Step 8: Commit public routes**

Run repository smoke and privacy gates, inspect staged paths, then commit:

```bash
git commit -m "feat: add public project and contribution guides"
```

---

### Task 4: Searchable technical documentation and helpful 404

**Files:**

- Create: `website/src/styles/starlight.css`
- Create: `website/src/content/docs/docs/index.md`
- Create: `website/src/content/docs/docs/system-overview.md`
- Create: `website/src/content/docs/docs/scientific-safeguards.md`
- Create: `website/src/content/docs/docs/data-and-literature.md`
- Create: `website/src/content/docs/docs/modeling-and-validation.md`
- Create: `website/src/content/docs/docs/issues-and-projects.md`
- Create: `website/src/content/docs/docs/local-development.md`
- Create: `website/src/content/docs/docs/deployment.md`
- Create: `website/src/pages/404.astro`
- Create: `website/tests/docs.test.ts`

**Interfaces:**

- Consumes: Starlight docs collection, repository source links, and shared design tokens.
- Produces: `/docs/` plus seven focused technical guides, searchable Starlight navigation, and a custom recovery route.

- [ ] **Step 1: Write the failing docs-route tests**

After a production build, require every planned documentation HTML path and `404.html`. Assert the docs landing page names P0–P5 and links to the authoritative overview/objectives/design; assert the 404 offers Home, Contribute, and Technical docs routes. The production break caught is a navigation shell that exists but does not lead to the contracts contributors must follow.

- [ ] **Step 2: Verify RED**

Run: `cd website && npm test -- tests/docs.test.ts`

Expected: FAIL because docs entries and custom 404 are absent.

- [ ] **Step 3: Author the Starlight guides**

Each page must explain one topic concisely, identify authoritative repository sources, and avoid duplicating frozen contracts. The data guide includes the literature evidence safeguards against invented coordinates, radii, denominators, ascertainment, allele orientation, and source locators. The local-development guide lists the exact Python and website verification commands.

- [ ] **Step 4: Apply the shared visual language to Starlight**

Override Starlight through `customCss`, using the same tokens, local fonts, focus treatment, and restrained surfaces. Configure its GitHub social icon/link and explicit sidebar labels. Preserve Starlight's semantic article, sidebar, table-of-contents, search, and code-block behavior.

- [ ] **Step 5: Implement 404 recovery**

Use `SiteLayout`, describe that the route was not found, and offer clear links to Home, Contribute, and Technical docs without blaming the user.

- [ ] **Step 6: Verify GREEN**

Run `cd website && npm test && npm run check && npm run build`.

Expected: all content tests pass and Astro emits every planned static route.

- [ ] **Step 7: Commit docs**

Run repository smoke and privacy gates, inspect staged paths, then commit:

```bash
git commit -m "docs: add searchable technical guidance"
```

---

### Task 5: Deployment, link, accessibility, and browser contracts

**Files:**

- Create: `website/scripts/build-fallback.mjs`
- Create: `website/scripts/check-links.mjs`
- Create: `website/playwright.config.ts`
- Create: `website/tests/site.spec.ts`
- Create: `.github/workflows/pages.yml`
- Modify: `website/package.json`
- Update: `website/package-lock.json`

**Interfaces:**

- Consumes: production and fallback static output, all top-level routes, GitHub's Pages artifact/deployment APIs.
- Produces: deterministic build variants, broken-link refusal, desktop/mobile axe coverage, and main-only Pages deployment.

- [ ] **Step 1: Write the failing built-link checker fixture test**

Extract the checker's pure `resolveInternalTarget(href, currentFile, base)` function and first test literals for `/`, `/genomeOS/`, query/fragment links, directories, and missing output paths. Run it and confirm RED because the script does not exist.

- [ ] **Step 2: Implement both build variants and the link checker**

`build-fallback.mjs` spawns Astro with `SITE_URL=https://bschilder.github.io`, `BASE_PATH=/genomeOS`, and `outDir=dist-fallback`. `check-links.mjs` walks HTML in the requested output directory, resolves internal `href`/`src` targets under that build's base, and exits nonzero with the referring page and unresolved target. It ignores external, mail, telephone, data, and fragment-only URLs.

- [ ] **Step 3: Verify root and fallback outputs**

Run:

```bash
cd website
npm run build
npm run check:links -- dist /
npm run build:fallback
npm run check:links -- dist-fallback /genomeOS/
```

Expected: both build trees pass; mutating a fixture link to a missing file makes the checker fail with the exact referrer.

- [ ] **Step 4: Write browser and axe tests before interaction code changes**

Use Playwright against `npm run preview` to test desktop and mobile widths. Assert top-level navigation, mobile `<details>` menu keyboard behavior, working-group links, GitHub icon accessible name and destination, all three capability labels, 404 recovery, one `h1` per route, and no serious/critical axe findings. These tests exercise real rendered pages and do not mock Astro or Starlight.

- [ ] **Step 5: Run browser tests and verify any missing behavior fails**

Run: `cd website && npx playwright install chromium && npm run test:e2e`

Expected before final refinements: at least one intended mobile/accessibility assertion fails for the missing behavior rather than a setup error.

- [ ] **Step 6: Implement only the required accessibility refinements**

Correct semantic names, disclosure behavior, focus placement, overflow, or contrast exposed by Step 5. Do not add hydration when native HTML provides the behavior.

- [ ] **Step 7: Implement Pages workflow**

Use `actions/checkout@v7`, `actions/setup-node@v6` with Node 24 and npm cache keyed to `website/package-lock.json`, `actions/upload-pages-artifact@v4`, and `actions/deploy-pages@v5`. Validate pull requests and `main`; upload/deploy only on `main`. Grant `contents: read` globally and `pages: write` plus `id-token: write` only where required. Set deployment concurrency to cancel obsolete runs.

- [ ] **Step 8: Verify GREEN**

Run all website checks and require clean output:

```bash
cd website
npm ci
npm run format:check
npm run check
npm test
npm run build
npm run check:links -- dist /
npm run build:fallback
npm run check:links -- dist-fallback /genomeOS/
npm run test:e2e
```

- [ ] **Step 9: Commit deployment and quality gates**

Run repository smoke and privacy checks, inspect staged paths, then commit:

```bash
git commit -m "ci: validate and deploy the Pages site"
```

---

### Task 6: Reproducible review figure, full verification, and PR

**Files:**

- Create: `website/scripts/capture-homepage.mjs`
- Create: `docs/figures/docs-site-homepage.png`
- Modify: `website/package.json`
- Update: `website/package-lock.json` only if script wiring changes dependencies

**Interfaces:**

- Consumes: a successfully built production preview at a caller-supplied URL.
- Produces: deterministic 1440×1000 PNG review evidence and a pull request closing Issue #153.

- [ ] **Step 1: Write the capture script**

Use Playwright Chromium with a 1440×1000 viewport, reduced-motion media, loaded fonts, and the exact homepage URL supplied by `CAPTURE_URL` (default `http://127.0.0.1:4321/`). Save to `../docs/figures/docs-site-homepage.png` relative to `website/`. Fail if the page response is absent/non-OK or the primary heading is missing.

- [ ] **Step 2: Generate and inspect the review image**

Run the production preview, execute `npm run capture`, and inspect the PNG at native resolution. Check hero crop, heading legibility, evidence-state distinction, line lengths, focus treatment, and absence of horizontal overflow. If a visual bug is found, first add the smallest browser regression test, confirm RED, fix, confirm GREEN, and recapture.

- [ ] **Step 3: Run the complete website verification from a clean install**

Repeat every command in Task 5 Step 8 with no existing `node_modules` dependency assumed.

- [ ] **Step 4: Run the complete repository verification**

From repository root run:

```bash
ruff check .
python scripts/freeze_contract.py --check
python scripts/check_module_size.py
python scripts/check_private_files.py
python scripts/smoke.py
pytest -v
```

Use the existing environment documented for the worktree and isolated writable PyTensor/matplotlib cache directories. Report any skipped or failed gate exactly.

- [ ] **Step 5: Commit the implementation with the issue-closing keyword**

Stage only the capture script, package metadata if changed, and PNG. Run privacy and staged-path checks, then commit:

```bash
git commit -m "feat: publish the genomeOS documentation site, closes #153"
```

- [ ] **Step 6: Push and open the pull request**

Run the privacy gate again, push `feat/153-docs-site`, and open one PR containing:

- `Closes #153`
- implemented spec §§1–12;
- exact website and Python verification commands/results;
- the raw branch image URL for `docs/figures/docs-site-homepage.png`;
- the custom-domain handoff state, including pending HTTPS if GitHub is still provisioning it.

If posting a separate update on Issue #153, mention its original author explicitly.

- [ ] **Step 7: Leave the verified local preview running**

Return the exact local URL to the user and keep the dev server alive for their review. Do not merge the PR without an explicit request.
