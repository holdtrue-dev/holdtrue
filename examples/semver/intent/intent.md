# Intent: semver

Resolve semantic-version constraints, the way a package manager does. A version is a major, minor, and patch number. A constraint is an operator paired with a version.

- **compare**: order two versions. Return 1 if the first is newer, -1 if the second is newer, 0 if they are the same. Compare major first, then minor, then patch.
- **satisfies**: whether a version meets a single constraint. The operators are `==`, `>=`, `>`, `<=`, `<`, caret (same major and at least the version), and tilde (same major and minor and at least the version).
- **satisfies all**: whether a version meets every constraint in a set (an empty set is met by anything).
- **max satisfying**: the newest version in a list that meets a constraint, or nothing when none do.

Four functions over shared version and constraint types.
