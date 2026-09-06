import sitemap from '@astrojs/sitemap';
import starlight from '@astrojs/starlight';
import { defineConfig } from 'astro/config';

const site = process.env.SITE_URL ?? 'https://genome-os.org';
const base = process.env.BASE_PATH ?? '/';
const outDir = process.env.OUT_DIR ?? 'dist';
const normalizedBase = base === '/' ? '/' : `/${base.replace(/^\/+|\/+$/g, '')}/`;

export default defineConfig({
  site,
  base,
  outDir,
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: 'genomeOS',
      description: 'An open atlas of human genetic variation across geography.',
      favicon: `${normalizedBase}favicon.svg`,
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/bschilder/genomeOS',
        },
      ],
      sidebar: [
        {
          label: 'Start here',
          items: [{ label: 'Technical overview', slug: 'docs' }],
        },
      ],
    }),
    sitemap(),
  ],
});
