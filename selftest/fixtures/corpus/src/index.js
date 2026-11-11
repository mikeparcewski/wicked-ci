import { add } from './add.js';

export function sum(list) {
  return list.reduce((acc, n) => add(acc, n), 0);
}
