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
  devToolbar: { enabled: false },
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: 'genomeOS',
      description: 'An open atlas of human genetic variation across geography.',
      favicon: '/favicon.svg',
      disable404Route: true,
      components: {
        EditLink: './src/components/starlight/EditLink.astro',
        SocialIcons: './src/components/starlight/SocialIcons.astro',
      },
      customCss: [
        '@fontsource-variable/figtree',
        '@fontsource-variable/raleway',
        './src/styles/starlight.css',
      ],
      editLink: {
        baseUrl: 'https://github.com/bschilder/genomeOS/edit/main/website/',
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
          label: 'Explore the project',
          items: [
            { label: 'Project home', link: '/' },
            { label: 'Application preview', link: '/app/' },
            { label: 'Working groups', link: '/working-groups/' },
            { label: 'Contribute', link: '/contribute/' },
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
