import { test } from "node:test";
import assert from "node:assert/strict";
import { sum, mean, clamp } from "../src/math.js";

test("sum adds every element", () => {
  assert.equal(sum([1, 2, 3]), 6);
  assert.equal(sum([]), 0);
});

test("mean averages", () => {
  assert.equal(mean([2, 4]), 3);
  assert.throws(() => mean([]), RangeError);
});

test("clamp bounds", () => {
  assert.equal(clamp(5, 0, 3), 3);
  assert.equal(clamp(-1, 0, 3), 0);
});
