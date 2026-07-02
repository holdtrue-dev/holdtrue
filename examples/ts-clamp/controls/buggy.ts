/** Buggy: missing lo clamp — always returns x or hi, never lo. */
export function clamp(x: number, lo: number, hi: number): number {
    return Math.min(x, hi);
}
