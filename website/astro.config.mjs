import sitemap from '@astrojs/sitemap';
import starlight from '@astrojs/starlight';
import { defineConfig } from 'astro/config';

const site = process.env.SITE_URL ?? 'https://genome-os.org';
const base = process.env.BASE_PATH ?? '/';
const outDir = process.env.OUT_DIR ?? 'dist';
const normalizedBase =
  base === '/' ? '/' : `/${base.replace(/^\/+|\/+$/g, '')}/`;

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
      disable404Route: true,
      customCss: [
        '@fontsource-variable/figtree',
        '@fontsource-variable/raleway',
        './src/styles/starlight.css',
      ],
      editLink: {
        baseUrl:
          'https://github.com/bschilder/genomeOS/edit/main/website/src/content/docs/',
      },
      head: [
        {
          tag: 'meta',
          attrs: {
            property: 'og:image',
            content: new URL(
              `${normalizedBase}images/genomeos-banner.png`,
              site,
            ).href,
          },
        },
        {
          tag: 'meta',
          attrs: {
            name: 'twitter:image',
            content: new URL(
              `${normalizedBase}images/genomeos-banner.png`,
              site,
            ).href,
          },
        },
      ],
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/bschilder/genomeOS',
        },
      ],
      sidebar: [
        {
          label: 'Explore genomeOS',
          items: [
            { label: 'Project home', link: normalizedBase },
            {
              label: 'Working groups',
              link: `${normalizedBase}working-groups/`,
            },
            { label: 'Contribute', link: `${normalizedBase}contribute/` },
          ],
        },
        {
          label: 'Technical docs',
          items: [{ autogenerate: { directory: 'docs' } }],
        },
      ],
    }),
    sitemap(),
  ],
});
