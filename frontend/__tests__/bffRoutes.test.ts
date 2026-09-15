/**
 * Every `/api/...` path the browser fetches must resolve to something.
 *
 * Next.js answers an unmatched /api path with a plain 404, which reaches the
 * component as "request failed" and gets rendered as whatever its else-branch
 * says. That is how the lyrics modal spent months showing "Lyrics not found"
 * for songs whose lyrics were sitting in the database: SongList fetched
 * /api/songs/{id}/lyrics and no route handler was ever created for it.
 *
 * This walks the client-side source for literal /api/ fetches and resolves each
 * one against app/api/ on disk (and the next.config rewrites), so a fetch to a
 * path nobody implemented fails here instead of in the UI.
 */
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const FRONTEND = resolve(__dirname, '..');
const APP_API = join(FRONTEND, 'app', 'api');

/** Paths served by next.config rewrites rather than a route handler. */
const REWRITTEN_PREFIXES = ['/api/agent/'];

/** Stands in for a `${...}` interpolation while resolving a path. */
const DYNAMIC = '__DYNAMIC__';

function walk(dir: string, onFile: (path: string) => void) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === 'node_modules' || entry === '.next') continue;
      walk(full, onFile);
    } else if (/\.(ts|tsx)$/.test(entry)) {
      onFile(full);
    }
  }
}

/** Client-side source: components, hooks, and pages — not the route handlers. */
function clientSourceFiles(): string[] {
  const files: string[] = [];
  for (const dir of ['components', 'hooks', 'app']) {
    const root = join(FRONTEND, dir);
    try {
      statSync(root);
    } catch {
      continue;
    }
    walk(root, (file) => {
      if (!file.startsWith(APP_API)) files.push(file);
    });
  }
  return files;
}

/** Literal `/api/...` paths fetched in a file, with `${...}` reduced to a placeholder. */
function fetchedApiPaths(source: string): string[] {
  const paths: string[] = [];
  const pattern = /fetch\(\s*(['"`])(\/api\/[^'"`]*)\1/g;

  for (const match of source.matchAll(pattern)) {
    const cleaned = match[2]
      .split('?')[0]
      .replace(/\$\{[^}]*\}/g, DYNAMIC)
      .replace(/\/+$/, '');
    paths.push(cleaned);
  }

  return paths;
}

/** Resolve an /api path to a route.ts on disk, matching [param] dirs. */
function routeFileFor(apiPath: string): string | null {
  const segments = apiPath.split('/').filter(Boolean).slice(1); // drop "api"
  let dir = APP_API;

  for (const segment of segments) {
    let entries: string[];
    try {
      entries = readdirSync(dir).filter((e) => statSync(join(dir, e)).isDirectory());
    } catch {
      return null;
    }

    const isDynamic = segment.includes(DYNAMIC);
    // A literal segment can still be served by a dynamic directory
    // (e.g. /api/produce/tools/eq/analyze -> tools/[tool]/analyze).
    const exact = isDynamic ? undefined : entries.find((e) => e === segment);
    const dynamic = entries.find((e) => e.startsWith('[') && e.endsWith(']'));
    const next = exact ?? dynamic;

    if (!next) return null;
    dir = join(dir, next);
  }

  for (const candidate of ['route.ts', 'route.tsx', 'route.js']) {
    try {
      statSync(join(dir, candidate));
      return join(dir, candidate);
    } catch {
      // keep looking
    }
  }
  return null;
}

describe('every /api path the browser fetches is implemented', () => {
  const offenders: string[] = [];
  let checked = 0;

  for (const file of clientSourceFiles()) {
    for (const apiPath of fetchedApiPaths(readFileSync(file, 'utf8'))) {
      if (REWRITTEN_PREFIXES.some((prefix) => apiPath.startsWith(prefix))) continue;
      checked += 1;
      if (!routeFileFor(apiPath)) {
        offenders.push(`${relative(FRONTEND, file)} -> ${apiPath.split(DYNAMIC).join('${...}')}`);
      }
    }
  }

  it('finds fetches to check', () => {
    expect(checked).toBeGreaterThan(5);
  });

  it('has a route handler for each', () => {
    expect(offenders).toEqual([]);
  });
});

describe('the lyrics modal route specifically', () => {
  it('exists, since SongList depends on it', () => {
    expect(routeFileFor(`/api/songs/${DYNAMIC}/lyrics`)).not.toBeNull();
  });

  it('is distinct from the timed-lyrics route', () => {
    const plain = routeFileFor(`/api/songs/${DYNAMIC}/lyrics`);
    const timed = routeFileFor(`/api/songs/${DYNAMIC}/lyrics/timed`);
    expect(plain).not.toBeNull();
    expect(timed).not.toBeNull();
    expect(plain).not.toEqual(timed);
  });
});
