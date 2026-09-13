import { test } from 'node:test';
import assert from 'node:assert/strict';
import { add } from '../src/add.js';
import { sum } from '../src/index.js';

test('add returns the sum', () => {
  assert.equal(add(2, 3), 5);
});

test('sum folds with add', () => {
  assert.equal(sum([1, 2, 3]), 6);
});
