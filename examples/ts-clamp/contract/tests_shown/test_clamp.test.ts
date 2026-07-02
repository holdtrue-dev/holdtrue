/**
 * Shown property test. The implementer may read this.
 *
 * Checks only the range invariant, not the exact value. The exact value is
 * pinned by the contract and the held-out test, so the answer is not here.
 */
import * as fc from 'fast-check';
import { clamp } from './core';

const numbers = fc.integer({ min: -1000, max: 1000 });

test('result is in [lo, hi]', () => {
    fc.assert(fc.property(numbers, numbers, numbers, (x, lo, hi) => {
        if (lo > hi) return;
        const result = clamp(x, lo, hi);
        expect(result).toBeGreaterThanOrEqual(lo);
        expect(result).toBeLessThanOrEqual(hi);
    }));
});

test('x already in range is returned unchanged', () => {
    fc.assert(fc.property(numbers, numbers, numbers, (x, lo, hi) => {
        if (lo > hi) return;
        if (x < lo || x > hi) return;
        expect(clamp(x, lo, hi)).toBe(x);
    }));
});
