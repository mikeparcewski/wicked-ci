// Small math helpers.

/** Sum of an array of numbers. Empty array sums to 0. */
export function sum(xs) {
  let total = 0;
  for (let i = 0; i < xs.length; i++) total += xs[i];
  return total;
}

/** Arithmetic mean; throws RangeError on an empty array. */
export function mean(xs) {
  if (xs.length === 0) throw new RangeError("mean of empty array");
  return sum(xs) / xs.length;
}

/** Clamp n into [lo, hi]. */
export function clamp(n, lo, hi) {
  return Math.min(Math.max(n, lo), hi);
}

/** Largest element of a non-empty array; throws RangeError on an empty array. */
export function max(xs) {
  if (xs.length === 0) throw new RangeError("max of empty array");
  return xs.reduce((m, x) => (x > m ? x : m), xs[0]);
}
