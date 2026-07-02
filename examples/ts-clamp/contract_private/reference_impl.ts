/** Reference oracle. Author-side; the implementer never sees this. */
export function clamp(x: number, lo: number, hi: number): number {
    return Math.min(Math.max(x, lo), hi);
}
