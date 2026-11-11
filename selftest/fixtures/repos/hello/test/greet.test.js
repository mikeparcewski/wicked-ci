const test = require('node:test');
const assert = require('node:assert/strict');
const { greet } = require('../src/greet.js');
test('greets by name', () => { assert.equal(greet('Ada'), 'Hello, Ada!'); });
test('greets friend when empty', () => { assert.equal(greet(''), 'Hello, friend!'); });
