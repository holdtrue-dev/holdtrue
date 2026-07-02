"""Build a minimal seccomp BPF filter and apply it via bwrap's --seccomp option.

The filter blocks syscalls that can be used to escape namespace isolation or leak
information, on top of what bwrap's --unshare-all already prevents.  It uses a
pure-Python BPF assembler so no C bindings are needed.

Only x86-64 is supported.  On other architectures the filter is not loaded (the
function returns None) and the caller falls back to a plain bwrap sandbox.

See linux/filter.h and linux/seccomp.h for the BPF / seccomp constants.
"""
from __future__ import annotations

import os
import platform
import struct

# --------------------------------------------------------------------------- #
# BPF instruction encoding (linux/filter.h)
# --------------------------------------------------------------------------- #
_BPF_LD  = 0x00
_BPF_W   = 0x00   # 32-bit word
_BPF_ABS = 0x20   # absolute packet offset
_BPF_JMP = 0x05
_BPF_JEQ = 0x10   # jump-if-equal
_BPF_K   = 0x00   # use constant k
_BPF_RET = 0x06

# seccomp return values (linux/seccomp.h)
_RET_ALLOW  = 0x7FFF_0000
_RET_EPERM  = 0x0005_0000 | 1   # SECCOMP_RET_ERRNO | EPERM

# Offsets into struct seccomp_data (linux/seccomp.h)
_OFF_NR   = 0    # int nr — syscall number
_OFF_ARCH = 4    # __u32 arch

# struct seccomp_data.arch value for x86-64
_AUDIT_ARCH_X86_64 = 0xC000_003E

# Syscall numbers to block (x86-64, linux/syscall.h)
_BLOCKED: list[int] = [
    101,  # ptrace             — process inspection / injection
    155,  # pivot_root         — change root filesystem
    164,  # settimeofday       — system clock manipulation
    165,  # mount              — filesystem mounting
    166,  # umount2            — filesystem unmounting
    250,  # keyctl             — kernel keyring access
    272,  # unshare            — create new namespaces from inside the sandbox
    298,  # perf_event_open    — performance counter access (info leakage)
    305,  # clock_adjtime      — system clock manipulation
    310,  # process_vm_readv   — read another process's memory
    311,  # process_vm_writev  — write another process's memory
    317,  # seccomp            — block loading additional filters
    321,  # bpf                — load kernel BPF programs
    323,  # userfaultfd        — user-space page-fault handler (escape vector)
    424,  # pidfd_send_signal  — cross-pid signalling (new in 5.1)
]


def _instr(code: int, jt: int, jf: int, k: int) -> bytes:
    return struct.pack("<HBBI", code, jt, jf, k)


def build_filter() -> bytes:
    """Return the raw sock_filter[] bytes for bwrap's --seccomp fd."""
    program: list[bytes] = []

    # 1. Load the arch field from seccomp_data.
    program.append(_instr(_BPF_LD | _BPF_W | _BPF_ABS, 0, 0, _OFF_ARCH))
    # 2. If arch != x86-64: jump past all syscall checks and ALLOW.
    #    Distance (jt): len(blocked) + 2 instructions (load nr + all jne checks) + allow
    #    We calculate this after assembling; for now use a forward label trick:
    #    place the arch-mismatch ALLOW before the syscall checks.
    #    Layout:
    #      [0] load arch
    #      [1] jeq x86_64, +0 (fall through to nr checks), else jump to ALLOW(end-1)
    #      [2] load nr
    #      [3..N+2] jeq blocked[i]: if match jump to DENY(end), else fall through
    #      [N+3] ALLOW
    #      [N+4] DENY (EPERM)
    n = len(_BLOCKED)
    # Instruction [1]: jt=0 (fall through on match = arch IS x86-64),
    #                  jf = skip to ALLOW = n + 1 instructions ahead
    program.append(_instr(_BPF_JMP | _BPF_JEQ | _BPF_K, 0, n + 1, _AUDIT_ARCH_X86_64))
    # 3. Load the syscall number.
    program.append(_instr(_BPF_LD | _BPF_W | _BPF_ABS, 0, 0, _OFF_NR))
    # 4. For each blocked syscall: if nr == syscall, jump to DENY; else fall through.
    #    The DENY instruction is always the last one. After the final check, the ALLOW
    #    instruction is at position n+3 (0-indexed: the next instruction after the checks).
    for i, nr in enumerate(_BLOCKED):
        # remaining checks after this one: n - 1 - i
        # allow is 1 instruction after the last check
        # deny  is 1 instruction after allow
        # from here: jt = (n - 1 - i) + 1 = n - i  → jump over remaining + allow → deny
        jt = n - i   # jumps to deny
        jf = 0       # fall through to next check
        program.append(_instr(_BPF_JMP | _BPF_JEQ | _BPF_K, jt, jf, nr))
    # 5. ALLOW (reached when no blocked syscall matched)
    program.append(_instr(_BPF_RET | _BPF_K, 0, 0, _RET_ALLOW))
    # 6. DENY (reached when a blocked syscall matched)
    program.append(_instr(_BPF_RET | _BPF_K, 0, 0, _RET_EPERM))

    return b"".join(program)


def open_filter_fd() -> int | None:
    """Write the seccomp filter to a pipe and return the read-end fd for --seccomp.

    Returns None when not on x86-64 (filter is arch-specific).  The caller is
    responsible for closing the fd after spawning the process.
    """
    if platform.machine() not in ("x86_64", "amd64"):
        return None
    try:
        r_fd, w_fd = os.pipe()
        data = build_filter()
        os.write(w_fd, data)
        os.close(w_fd)
        os.set_inheritable(r_fd, True)
        return r_fd
    except Exception:
        return None
