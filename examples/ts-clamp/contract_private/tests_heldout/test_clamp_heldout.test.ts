/**
 * Held-out differential test. The implementer never sees this.
 *
 * Compares the implementation's exact value against the reference oracle over
 * the full input domain to catch implementations that pass the shown tests
 * only by satisfying the range condition without returning the right value.
 */
import * as fc from 'fast-check';
import { clamp as impl } from './core';
import { clamp as oracle } from './reference_impl';

const numbers = fc.integer({ min: -10000, max: 10000 });

test('agrees with oracle over sampled inputs', () => {
    fc.assert(fc.property(numbers, numbers, numbers, (x, lo, hi) => {
        if (lo > hi) return;
        expect(impl(x, lo, hi)).toBe(oracle(x, lo, hi));
    }));
});
