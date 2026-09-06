import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const EXTERNAL_SCHEME = /^[a-z][a-z\d+.-]*:/i;

function normalizeBase(base) {
  const clean = base.replace(/^\/+|\/+$/g, '');
  return clean ? `/${clean}/` : '/';
}

/** Resolve an internal URL to the corresponding path inside an Astro output tree. */
export function resolveInternalTarget(href, currentFile, base = '/') {
  if (
    !href ||
    href.startsWith('#') ||
    href.startsWith('//') ||
    EXTERNAL_SCHEME.test(href)
  ) {
    return null;
  }

  const deploymentBase = normalizeBase(base);
  const currentRoute = currentFile.endsWith('index.html')
    ? `/${currentFile.slice(0, -'index.html'.length)}`
    : `/${currentFile}`;
  const currentUrl = new URL(
    `${deploymentBase}${currentRoute.replace(/^\/+/, '')}`,
    'https://genomeos.invalid',
  );
  const targetUrl = new URL(href, currentUrl);

  if (!targetUrl.pathname.startsWith(deploymentBase)) {
    throw new Error(`URL ${href} is outside configured base ${deploymentBase}`);
  }

  let target = decodeURIComponent(
    targetUrl.pathname.slice(deploymentBase.length),
  );
  if (!target || target.endsWith('/')) target += 'index.html';
  return target;
}

function walk(root, relative = '') {
  const directory = path.join(root, relative);
  return readdirSync(directory).flatMap((name) => {
    const child = path.join(relative, name);
    return statSync(path.join(root, child)).isDirectory()
      ? walk(root, child)
      : [child];
  });
}

function extractTargets(source) {
  const targets = [];
  const attributes = /(?:href|src)=["']([^"']+)["']/g;
  const cssUrls = /url\(\s*["']?([^"')]+)["']?\s*\)/g;
  for (const match of source.matchAll(attributes)) targets.push(match[1]);
  for (const match of source.matchAll(cssUrls)) targets.push(match[1]);
  return targets;
}

export function checkOutput(outputDirectory, base = '/') {
  const root = path.resolve(outputDirectory);
  const errors = [];

  for (const currentFile of walk(root).filter((file) =>
    /\.(?:html|css)$/.test(file),
  )) {
    const source = readFileSync(path.join(root, currentFile), 'utf8');
    for (const href of extractTargets(source)) {
      try {
        const target = resolveInternalTarget(href, currentFile, base);
        if (target && !existsSync(path.join(root, target))) {
          errors.push(`${currentFile}: ${href} -> ${target}`);
        }
      } catch (error) {
        errors.push(`${currentFile}: ${error.message}`);
      }
    }
  }

  if (errors.length) {
    throw new Error(`Broken internal links:\n${errors.join('\n')}`);
  }
}

const invokedPath = process.argv[1]
  ? pathToFileURL(path.resolve(process.argv[1])).href
  : '';
if (import.meta.url === invokedPath) {
  const outputDirectory = process.argv[2] ?? 'dist';
  const base = process.argv[3] ?? '/';
  checkOutput(outputDirectory, base);
  console.log(
    `Internal links valid in ${outputDirectory} for base ${normalizeBase(base)}`,
  );
}
