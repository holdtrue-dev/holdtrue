# Intent: scheduler

Work out meeting-room availability for a single day, in whole minutes from midnight (0 to 1440). A time interval has a start and an end, and the end is always after the start.

- **overlaps**: whether two intervals share any minute. Two intervals that only touch at an endpoint do not overlap.
- **intersect**: the interval two intervals share, or nothing when they do not overlap.
- **merge**: given a list of intervals, combine every overlapping or touching pair and return the result sorted, with no two intervals overlapping or touching.
- **free slots**: given a list of busy intervals and a window, return the gaps inside the window that no busy interval covers, sorted and non-overlapping.
- **earliest slot**: given the busy intervals, a window, and a duration, return the earliest interval of exactly that duration that fits inside the window without hitting a busy interval, or nothing when none fits.

Five functions in all, over a shared interval type.
