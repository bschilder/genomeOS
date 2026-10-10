import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import starlight from '@astrojs/starlight';
import { defineConfig } from 'astro/config';
import { viteStaticCopy } from 'vite-plugin-static-copy';
import atlasScenePreload from './integrations/atlas-scene-preload.mjs';

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
    react(),
    atlasScenePreload(),
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
        baseUrl: 'https://github.com/genomeOS/genomeOS/edit/main/website/',
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
          href: 'https://github.com/genomeOS/genomeOS',
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
  vite: {
    envDir: '..',
    build: {
      rolldownOptions: {
        output: {
          // Fast-load design §B.1: a stable chunk name lets the cold-load
          // harness attribute long animation frames to Cesium. Rolldown's
          // replacement for the deprecated manualChunks.
          codeSplitting: {
            groups: [
              {
                name: 'cesium',
                // JavaScript only. CSS must stay out of the group: AtlasExplorer.tsx
                // still imports cesium/Build/Cesium/Widgets/widgets.css, and if that
                // stub lands in the Cesium chunk the island gains a static
                // import"./cesium.<hash>.js", loading all of Cesium with the island
                // and undoing Task 35 (B2.12)'s lazy scene chunk.
                //
                // The Atlas-owned render loop joins it: its frame callback is only
                // viewer.resize() + viewer.render(), the work Cesium's default loop did
                // from this chunk, so the harness keeps counting Cesium renders as
                // Cesium (atlas-scene is its only importer).
                test: /[\\/]node_modules[\\/](?:cesium|@cesium[\\/][^\\/]+)[\\/].*\.js$|[\\/]src[\\/]atlas[\\/]scene[\\/]render-loop\.ts$/,
              },
            ],
          },
        },
      },
    },
    define: {
      CESIUM_BASE_URL: JSON.stringify(`${normalizedBase}cesium/`),
    },
    // The Atlas data worker is a module worker sharing ES modules with the island (fast-load design §B.6.3).
    worker: { format: 'es' },
    plugins: [
      viteStaticCopy({
        targets: ['Assets', 'ThirdParty', 'Widgets', 'Workers'].map((name) => ({
          src: `node_modules/cesium/Build/Cesium/${name}`,
          dest: 'cesium',
          rename: { stripBase: 4 },
        })),
      }),
    ],
  },
});
