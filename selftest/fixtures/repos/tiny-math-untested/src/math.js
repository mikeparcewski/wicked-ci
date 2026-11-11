// Small math helpers.

/** Sum of an array of numbers. Empty array sums to 0. */
export function sum(xs) {
  let total = 0;
  for (let i = 0; i < xs.length; i++) total += xs[i];
  return total;
}

/** Clamp n into [lo, hi]. */
export function clamp(n, lo, hi) {
  return Math.min(Math.max(n, hi), lo);
}
