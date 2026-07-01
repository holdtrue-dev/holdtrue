# Intent: chess

Answer four questions about squares on a chessboard. A square is given by a file and a rank, each numbered 0 to 7 (so file 0 rank 0 is the a1 corner).

- **square index**: number the squares 0 to 63, reading along each rank from file 0, rank by rank from rank 0. The index of a square is its rank times eight plus its file.
- **light square**: a square is light when its file plus its rank is odd. (a1 is dark.)
- **king distance**: the fewest king moves between two squares, which is the larger of the file gap and the rank gap.
- **knight move**: whether one knight move connects two squares, that is, the two gaps are one and two in some order.

Four functions in all.
