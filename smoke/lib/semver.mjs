// Minimal semver helpers (no dependency): parse, compare, range floor.

export function parse(v) {
  const m = String(v).trim().replace(/^v/, '').match(/^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?/);
  if (!m) return null;
  return { major: +m[1], minor: +m[2], patch: +m[3], pre: m[4] ?? null };
}

export function compare(a, b) {
  const x = parse(a);
  const y = parse(b);
  if (!x || !y) return NaN;
  for (const k of ['major', 'minor', 'patch']) {
    if (x[k] !== y[k]) return x[k] < y[k] ? -1 : 1;
  }
  if (x.pre === y.pre) return 0;
  if (x.pre === null) return 1;
  if (y.pre === null) return -1;
  return x.pre < y.pre ? -1 : 1;
}

export const lt = (a, b) => compare(a, b) < 0;
export const gte = (a, b) => compare(a, b) >= 0;

/** Does `version` satisfy a caret/tilde/exact range such as `^0.7.23`, `~1.2.0`, `1.2.3`, `>=0.7.20`? */
export function satisfies(version, range) {
  const v = parse(version);
  if (!v) return false;
  const r = String(range).trim();
  const exact = parse(r);
  if (/^\d/.test(r) && exact) return compare(version, r) === 0;
  if (r.startsWith('^')) {
    const base = parse(r.slice(1));
    if (!base) return false;
    if (compare(version, r.slice(1)) < 0) return false;
    if (base.major > 0) return v.major === base.major;
    if (base.minor > 0) return v.major === 0 && v.minor === base.minor;
    return v.major === 0 && v.minor === 0 && v.patch === base.patch;
  }
  if (r.startsWith('~')) {
    const base = parse(r.slice(1));
    if (!base) return false;
    return compare(version, r.slice(1)) >= 0 && v.major === base.major && v.minor === base.minor;
  }
  if (r.startsWith('>=')) return compare(version, r.slice(2)) >= 0;
  return false;
}

export function maxVersion(list) {
  let best = null;
  for (const v of list) {
    if (!parse(v)) continue;
    if (parse(v).pre !== null) continue;
    if (best === null || compare(v, best) > 0) best = v;
  }
  return best;
}
