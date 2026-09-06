# genomeOS public documentation website — design

**Status:** Draft for user review<br>
**Issue:** [#153](https://github.com/bschilder/genomeOS/issues/153)<br>
**Visual direction:** Orbital observatory<br>
**Production domain:** `https://genome-os.org`

## 1. Product claim

A newcomer can understand why genomeOS exists, distinguish measured evidence from modeled
estimates, find the working group that matches their skills, and reach a well-specified
contribution task without first reading the technical repository.

The site is public documentation and contributor onboarding. It is not the P5 product map, the
diagnostic `/preview`, a scientific-results publication, an AI assistant, or a genetic-data upload
service.

## 2. Audience and jobs

The first release serves five audiences:

| Audience | Job the site must support |
|---|---|
| Curious visitor | Understand the problem and why geographic genetic evidence matters. |
| Prospective contributor | Find a working group and an issue suited to their skills. |
| Scientific reviewer | Find the evidence, safeguards, validation bar, and technical contracts. |
| Organizer | Send one durable link that explains the project and how work is coordinated. |
| Potential partner | Understand what data or expertise the project needs without mistaking future ideas for shipped features. |

The homepage is written for the first two audiences. The Project and Working groups pages add
detail for reviewers and partners. The Starlight documentation area is the technical route.

## 3. Information architecture

The public navigation has five destinations plus a GitHub repository link:

```text
Home
├── Project
├── Working groups
├── Contribute
├── Technical docs
└── GitHub [icon + accessible label]
```

### 3.1 Home — `/`

The homepage tells one narrative in this order:

1. Full-width banner hero: “Explore genomes across the world.”
2. A short explanation of why genetic variation differs by place and why that matters.
3. The public scientific commitment: measured, estimated, and unknown are distinct states.
4. The two-atlas vision: variation across Earth, the genome inside the cell, and the bridge.
5. Three working-group entry points.
6. The contribution path from introduction to issue to reviewed pull request.
7. Current state, active development, and future explorations.
8. A final invitation to introduce yourself or browse `Ready` work.

The sickle-cell example is the main non-technical explanatory anchor. The page does not imply
that geography predicts an individual's genotype or that a visually smooth map is measured data.

### 3.2 Project — `/project/`

This page expands the README narrative:

- the unmet problem and why now;
- the Earth atlas, cellular atlas, and their eventual bridge;
- who could use the system;
- the six scientific safeguards;
- P0–P5 in plain language;
- the HbS, G6PD, and screening-program parity bar;
- a clearly dated current-status section.

Detailed technical claims link to their authoritative repository documents rather than acquiring a
different definition on the website.

### 3.3 Working groups — `/working-groups/`

The page says that groups are forming and invites additions. It does not imply formal membership,
governance, or leadership that organizers have not established.

**Data**

- Find exact allele measurements in publications, including PubMed and non-English literature.
- Preserve source anchors, denominators, allele orientation, ascertainment, geography, and reuse
  checks.
- Join gnomAD, 1000 Genomes, HGDP, AFND, national resources, and other compatible databases without
  converting continental ancestry labels into geography.
- Identify coverage gaps and creative, reproducible transfer paths for particular genes or variants.

**Modeling**

- Estimate allele-frequency distributions with uncertainty and explicit unsupported regions.
- Develop Bayesian spatial models, with Brian leading that line of work.
- Explore geometric deep learning and other statistically defensible model classes.
- Work on calibration, uncertainty quantification, ascertainment correction, cross-validation, and
  published-science parity.
- Treat models as interchangeable offline producers of the same versioned artifact contract; no
  inference moves onto the serving path.

**Product & Experience**

- Build the globe/map interaction, zoom, movement, layers, legends, and shareable state.
- Make measurements, estimates, uncertainty, and unknown regions legible to non-specialists.
- Design conversational access to versioned evidence as a future direction.
- Explore personal-data contribution only after privacy, consent, governance, security, and
  scientific-quality requirements are approved.

Each group ends with “Good fit if…”, concrete examples, relevant `skill:*` filters, and links to
the issue board. “Suggest another direction” links to the introduction discussion and issue form.

### 3.4 Contribute — `/contribute/`

The contributor flow is a genuine sequence and is therefore numbered:

1. Introduce yourself in Discussion #76.
2. Choose a working group or skill label.
3. Search open and closed issues before starting.
4. Select `Ready` work or propose an issue for triage.
5. State objective, measurable evidence, interface, assumptions, and refusal conditions.
6. Open a pull request and request the right expert review.

The page explains Projects statuses, all four label families, `wants-expert-review`,
`needs-human-decision`, milestones, and why priority follows the dependency graph. It tells
commenters to mention the original issue author when posting substantive updates so they are
notified. It links to #65 for the forthcoming contribution files and community standards.

### 3.5 Technical docs — `/docs/`

Starlight supplies the searchable documentation shell. The first release contains concise public
guides for:

- system overview and P0–P5;
- scientific safeguards and refusal behavior;
- data sources and literature evidence;
- modeling and validation contracts;
- issue/project conventions;
- local development and verification;
- deployment and infrastructure references.

Each guide links prominently to the corresponding authoritative Markdown file in the repository.
The site summaries explain; they do not replace frozen schemas, design specs, plans, or issue
decisions. Long implementation plans remain repository references rather than primary navigation.

## 4. Capability-status language

Every product statement belongs to one of three visible states:

| State | Meaning | Examples at launch |
|---|---|---|
| **Available now** | Implemented and backed by current evidence. | P0/P1 contracts, data adapters, P2/P3 kernels, fixture-backed P4 diagnostic path. |
| **In active development** | Tracked work with an issue or milestone. | Scientific parity, broader literature corpora, product map. |
| **Future exploration** | Direction only; no promise or approved implementation. | Conversational assistant, personal-genome upload, ancient-DNA time slider, full cell atlas. |

Future cards name their prerequisites. The personal-genome contribution card explicitly names
privacy, consent, governance, security, and quality control. It has no upload control.

## 5. Visual system

The selected “orbital observatory” direction spends visual boldness on the hero and keeps reading
surfaces restrained.

### 5.1 Palette

| Token | Value | Role |
|---|---|---|
| Void | `#020712` | Page and hero base |
| Orbit | `#071831` | Raised sections and navigation |
| Starlight | `#F2F8FF` | Primary text |
| Ion cyan | `#70E6FF` | Links, focus, measured evidence |
| Genome violet | `#AD8BFF` | Modeled evidence and secondary accents |
| Aurora mint | `#72E7C1` | Confirmed/current status |
| Signal amber | `#F4C86A` | Uncertainty and caution |
| Muted blue | `#A5B9D3` | Secondary text |

The hero uses the existing `docs/images/genomeos-banner.png` with one dark readability overlay.
Aurora color is drawn from the image. Gradients are not used as generic section decoration.

Measured, modeled, and unknown states use redundant labels and marker/pattern differences; color
alone never carries their meaning.

### 5.2 Typography

- Raleway Variable, locally bundled through Fontsource, echoes the thin geometric banner wordmark
  for display text.
- Figtree Variable, also locally bundled, is the reading and interface face.
- Body lines remain under approximately 76 characters with a minimum 1.55 line height.
- Labels use sentence case. Tracking and all-caps are reserved for the existing logo treatment,
  not repeated as generic eyebrows.

Exact packages and font versions are pinned in `package-lock.json`; the site makes no font-CDN
request.

### 5.3 Layout

Desktop homepage:

```text
┌──────────────────────────────────────────────────────────────┐
│ genomeOS       Project  Groups  Contribute  Docs  [GitHub]  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Explore genomes                 banner globe / Earth lights  │
│ across the world.                                           │
│ [Find your place] [Understand the project]                  │
│                                                              │
├───────────────────────────┬──────────────────────────────────┤
│ Measured here.            │ observed  modeled  unknown       │
│ Estimated there.          │ small evidence-layer diagram     │
│ Never confused.           │                                  │
├───────────────────────────┴──────────────────────────────────┤
│ Why it matters / HbS narrative                              │
├──────────────────────────────────────────────────────────────┤
│ Data              Modeling             Product & Experience │
├──────────────────────────────────────────────────────────────┤
│ How work moves: discuss → issue → Ready → PR → review       │
└──────────────────────────────────────────────────────────────┘
```

Mobile keeps the same narrative order, reduces the hero to one screen-height maximum, turns the
navigation into an accessible disclosure menu, and stacks working groups. No horizontal content
scroll is required.

### 5.4 Motion

One non-interactive motion system is allowed: a slow hero star/aurora drift created with CSS over
the static banner. It stops under `prefers-reduced-motion`. User-triggered navigation and
disclosures animate only enough to explain changed state. Sections do not independently fade or
slide into view.

### 5.5 Shared components

- `SiteHeader` and `SiteFooter`, reused by custom pages and Starlight overrides.
- `GitHubLink`, containing a visible GitHub mark, visible “GitHub” text where space permits, and an
  accessible name in every placement.
- `Hero`, `EvidenceStates`, `WorkingGroup`, `StatusBand`, `ContributionFlow`, `Callout`, and
  `SourceLink` components.
- A base-aware `sitePath()` helper is the only way components construct internal absolute paths.

Components have one content/layout responsibility. No component should become a second content
database.

## 6. Technical architecture

### 6.1 Project boundary

The static site lives under `website/`:

```text
website/
  package.json
  package-lock.json
  .nvmrc
  astro.config.mjs
  tsconfig.json
  public/
  src/
    assets/
    components/
    content/docs/
    layouts/
    pages/
    styles/
  tests/
```

The Python package does not import from the website and the website does not import Python runtime
code. It may copy the banner into its build graph and link to repository documents.

### 6.2 Runtime and dependencies

- Node.js 24 is declared in `.nvmrc`, `package.json#engines`, and CI.
- `package.json` uses exact versions rather than floating ranges.
- `package-lock.json` is committed; clean setup is `cd website && npm ci`.
- Astro, Starlight, the sitemap integration, local Fontsource packages, TypeScript checks, Vitest,
  Playwright, and axe are the intended dependency groups.
- No server adapter is installed. Every route is statically prerendered.

Dependency changes regenerate and commit the lockfile. CI uses `npm ci`, never `npm install`.

### 6.3 Custom pages and Starlight

Astro file-based routes implement the four public-facing pages. Starlight owns the `/docs/`
content collection and is customized through supported CSS/component overrides rather than a fork.
This follows Starlight's documented support for mixing custom Astro routes and content pages.

The public pages and documentation share design tokens, header, footer, canonical metadata, skip
link, and focus treatment. Starlight retains its semantic article navigation, table of contents,
code blocks, and search behavior.

### 6.4 URLs and domain behavior

Production configuration uses:

```text
site = https://genome-os.org
base = /
```

Preview verification also builds with the fallback combination:

```text
site = https://bschilder.github.io
base = /genomeOS
```

This catches root-relative paths that work on the custom domain but fail on a GitHub project-site
subpath. Components use `import.meta.env.BASE_URL` through `sitePath()`.

Because Pages is built by a custom GitHub Actions workflow, GitHub's current documentation says a
repository `CNAME` file is ignored and not required. The repository Pages “Custom domain” setting
is authoritative. Astro's `site` setting controls canonical and sitemap URLs.

## 7. Deployment

`.github/workflows/pages.yml` runs on relevant pull requests, pushes to `main`, and manual dispatch.

**Validate job, every PR and main push**

1. Check out the repository.
2. Install pinned Node 24.
3. Run `npm ci` in `website/`.
4. Run formatting/lint, `astro check`, unit/content tests, custom-domain build, fallback-subpath
   build, internal-link checks, and browser accessibility tests.

**Build and deploy jobs, main only**

1. Build the already validated static site for `https://genome-os.org/`.
2. Upload the Pages artifact.
3. Deploy through the `github-pages` environment using `pages:write` and `id-token:write` only in
   the deployment jobs.

Pull requests never deploy or mutate Pages. Concurrency cancels an obsolete in-progress deployment
when a newer `main` commit arrives.

The workflow follows Astro's official Pages action architecture and GitHub's Actions-based Pages
source already enabled for the repository.

## 8. Metadata, privacy, and performance

- Every route has a unique title, description, canonical URL, and social metadata.
- The existing banner is the default Open Graph image; pages may override alt text, never the
  scientific status of an image.
- `@astrojs/sitemap` emits the sitemap for the canonical domain.
- A custom 404 page leads to Home, Contribute, and Docs.
- The first release has no analytics, cookies, forms, accounts, remote fonts, or third-party
  JavaScript.
- External links are normal links; opening a new tab is not forced.
- Banner and screenshot assets declare dimensions, use responsive sources when beneficial, and do
  not block text rendering.
- Performance acceptance is Lighthouse-style rather than a marketing number: no avoidable client
  hydration, no layout shift from images/fonts, and no JavaScript required to read content.

## 9. Accessibility requirements

- Semantic landmarks, one page-level heading, skip link, and logical heading order.
- All interaction works by keyboard with a clearly visible ion-cyan focus indicator.
- Mobile menu and disclosures expose correct names, expanded state, and focus behavior.
- Text and controls meet WCAG 2.2 AA contrast; meaningful state is never color-only.
- Motion honors `prefers-reduced-motion`.
- Banner and scientific visuals have contextual alternative text; decorative stars are hidden.
- Axe browser tests cover every top-level route at desktop and mobile viewport widths.
- Browser zoom to 200% does not hide navigation or require horizontal reading scroll.

## 10. Verification and review evidence

The implementation is accepted when all of the following are true:

1. `npm ci` succeeds from a clean Node 24 environment.
2. Astro/TypeScript checks and unit tests pass.
3. Both production-root and `/genomeOS` fallback builds contain no broken internal links or missing
   assets.
4. Browser tests exercise navigation, the mobile menu, working-group links, repository icon link,
   capability-state labels, and the 404 route.
5. Axe reports no serious or critical violations on top-level pages.
6. Text-level tests prevent accidental removal of “measured”, “estimated”, “unknown”, working-group
   scope, future-feature caveats, issue/project guidance, and Discussion #76.
7. The existing Python lint, contract, module-size, privacy, smoke, and full test gates remain green.
8. A reproducible capture script produces `docs/figures/docs-site-homepage.png`; the PR embeds that
   figure and labels it as website review evidence.
9. CI deploys the merged artifact successfully and a post-deployment HTTP check confirms canonical
   metadata and navigation at the Pages URL.

Visual review explicitly checks the desktop homepage, mobile menu, docs page, focus states, reduced
motion, and the distinction between current and future capabilities.

## 11. Domain handoff

The code can establish canonical URLs, but the owner must perform the DNS/ownership steps that
require GitHub and GoDaddy account control.

1. In personal GitHub Settings → Pages, add `genome-os.org` as a verified domain.
2. Add the exact TXT record GitHub supplies at GoDaddy, then complete verification and retain the
   TXT record.
3. In repository Settings → Pages, set Custom domain to `genome-os.org` before pointing DNS.
4. In GoDaddy DNS, remove conflicting parked/forwarded records and add four apex `A` records for
   `@`: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, and `185.199.111.153`.
5. Add `www` as a `CNAME` to `bschilder.github.io` without `/genomeOS`.
6. Optionally add GitHub's four documented `AAAA` records for IPv6. Keep IPv4 records as well.
7. Do not add a wildcard DNS record.
8. Wait for DNS propagation, verify apex and `www`, then enable/confirm Enforce HTTPS in repository
   Pages settings.

GitHub may take up to 24 hours to observe DNS and provision HTTPS. The deployment is not considered
publicly handed off until both `https://genome-os.org/` and the `www` redirect work.

## 12. Error and refusal behavior

- A missing required environment URL, broken internal link, absent asset, invalid page metadata, or
  accessibility failure breaks the site workflow.
- A future feature without a visible prerequisite/status label breaks the content test.
- Build failures do not deploy an older newly labeled artifact as if it were current; the existing
  successful Pages deployment remains intact.
- The site has no client-side fallback that invents content when a source is missing.
- External GitHub API data is not fetched at page render time. Counts and issue states are either
  linked live or stated with an explicit date.

## 13. Non-goals

- Building or embedding the P5 interactive scientific map.
- Implementing the conversational agent.
- Accepting personal genetic data or contributor accounts.
- Mirroring every issue, plan, or generated API reference.
- Adding analytics, a CMS, comments, or a newsletter.
- Moving existing Python modules or repository documentation as a side effect.

## 14. Downstream consumers

The website becomes the public entry point for working-group organizers and contributors. Future P5
and P12 product documentation may adopt its visual tokens and navigation vocabulary, but they must
consume stable APIs and governance decisions rather than importing website implementation details.

## 15. References

- [Issue #153](https://github.com/bschilder/genomeOS/issues/153)
- [Astro: deploy to GitHub Pages](https://v6.docs.astro.build/en/guides/deploy/github/)
- [Starlight: content and custom pages](https://starlight.astro.build/guides/pages/)
- [Starlight customization](https://starlight.astro.build/guides/customization/)
- [GitHub: managing a Pages custom domain](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site)
- [GitHub: verifying a Pages domain](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages)
- [GoDaddy: manage DNS records](https://www.godaddy.com/help/manage-dns-records-680)
