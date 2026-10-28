"""Usage: trace.py SPEC.toml OUT.json

Assemble the spec's AT&T snippet, single-step it in Unicorn, and write every
intermediate register/memory state to JSON for asmdemo.typ.
"""

import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import capstone
from unicorn import UC_ARCH_X86, UC_HOOK_MEM_WRITE, UC_MODE_64, Uc
from unicorn import x86_const as ux

CODE_BASE = 0x1000000
DATA_SIZE = 0x200000  # memory at [0, 2 MiB) is mapped for data/stack
MAX_STEPS = 500  # guard against infinite loops

# 32/16/8-bit register names -> the 64-bit register they live in
SUBREGS = {}
for r in "abcd":
    SUBREGS |= {
        f"e{r}x": f"r{r}x",
        f"{r}x": f"r{r}x",
        f"{r}l": f"r{r}x",
        f"{r}h": f"r{r}x",
    }
for r in ("si", "di", "bp", "sp"):
    SUBREGS |= {f"e{r}": f"r{r}", r: f"r{r}", f"{r}l": f"r{r}"}
for n in range(8, 16):
    SUBREGS |= {f"r{n}d": f"r{n}", f"r{n}w": f"r{n}", f"r{n}b": f"r{n}"}


def uc_reg(name: str) -> int:
    return getattr(ux, f"UC_X86_REG_{name.upper()}")


def fmt(value: int, hex_: bool) -> str:
    return f"0x{value:X}" if hex_ else str(value)


def assemble(src: str) -> bytes:
    """Assemble with GNU as (AT&T syntax) and return the raw .text bytes."""
    with tempfile.TemporaryDirectory() as d:
        s, o, b = Path(d, "a.s"), Path(d, "a.o"), Path(d, "a.bin")
        s.write_text(f".text\n{src}\n")
        subprocess.run(["as", "--64", "-o", o, s], check=True)
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", o, b], check=True)
        return b.read_bytes()


def parse_listing(src: str) -> list[dict]:
    """Split the source into display lines, dropping comments and directives.

    A trailing `# c:N` comment links the instruction to line N of the C code
    (1-based) so that line gets highlighted too.
    """
    lines = []
    for raw in src.strip("\n").splitlines():
        code, _, comment = raw.partition("#")
        stripped = code.strip()
        if stripped.startswith("."):
            continue
        kind = (
            "blank" if not stripped else "label" if stripped.endswith(":") else "insn"
        )
        m = re.search(r"\bc:\s*(\d+)", comment)
        lines.append(
            {"text": code.rstrip(), "kind": kind, "c": int(m[1]) if m else None}
        )
    return lines


def main(spec_path: str, out_path: str):
    spec = tomllib.loads(Path(spec_path).read_text())
    code_base = spec.get("code_base", CODE_BASE)
    code = assemble(spec["asm"])
    listing = parse_listing(spec["asm"])

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.syntax = capstone.CS_OPT_SYNTAX_ATT
    md.detail = True
    insns = list(md.disasm(code, code_base))
    insn_lines = [i for i, l in enumerate(listing) if l["kind"] == "insn"]
    if len(insns) != len(insn_lines):
        sys.exit(
            f"source has {len(insn_lines)} instructions, assembler produced {len(insns)}"
        )
    by_addr, line_of = {}, {}
    for ins, ln in zip(insns, insn_lines):
        by_addr[ins.address] = ins
        line_of[ins.address] = ln
        listing[ln]["addr"] = f"0x{ins.address:X}"
    # calls to these are followed; calls to anything else are stepped over
    local_labels = {l["text"].strip()[:-1] for l in listing if l["kind"] == "label"}

    # "rdi:hex" -> show rdi in hex
    shown = [(r.split(":")[0], r.endswith(":hex")) for r in spec.get("regs_shown", [])]
    cells = spec.get("mem", [])
    pointers = spec.get("pointers", [])

    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(0, DATA_SIZE)
    uc.mem_map(code_base & ~0xFFF, 0x10000)
    uc.mem_write(code_base, code)
    uc.reg_write(ux.UC_X86_REG_RIP, code_base)
    uc.reg_write(ux.UC_X86_REG_RSP, DATA_SIZE - 0x1000)  # default; spec may override

    known_regs = {"rip"}
    for name, val in spec.get("regs", {}).items():
        uc.reg_write(uc_reg(name), val)
        known_regs.add(name)
    known_cells = set()
    for i, c in enumerate(cells):
        if "value" in c:
            uc.mem_write(
                c["addr"],
                c["value"].to_bytes(c["size"], "little", signed=c["value"] < 0),
            )
            known_cells.add(i)

    # mark cells as known once anything writes into them
    def on_write(_uc, _access, addr, size, _value, _data):
        for i, c in enumerate(cells):
            if addr < c["addr"] + c["size"] and c["addr"] < addr + size:
                known_cells.add(i)

    uc.hook_add(UC_HOOK_MEM_WRITE, on_write)

    def snapshot():
        regs = {
            n: fmt(uc.reg_read(uc_reg(n)), h) if n in known_regs else "?"
            for n, h in shown
        }
        mem = []
        for i, c in enumerate(cells):
            raw = uc.mem_read(c["addr"], c["size"])
            v = int.from_bytes(raw, "little", signed=c.get("signed", True))
            mem.append(fmt(v, c.get("hex", False)) if i in known_cells else "")
        ptrs = {p: uc.reg_read(uc_reg(p)) for p in pointers}
        tags = [["%" + p for p, v in ptrs.items() if v == c["addr"]] for c in cells]
        return {"regs": regs, "mem": mem, "tags": tags}

    # step numbers as used by `[steps.N]` and `show`
    first = 0 if spec.get("show_initial") else 1
    annotations = spec.get("steps", {})
    steps = []

    def record(line, cur, prev):
        steps.append(
            {
                "line": line,
                **cur,
                "changed_regs": [
                    r for r in cur["regs"] if cur["regs"][r] != prev["regs"][r]
                ],
                "changed_mem": [
                    i for i, v in enumerate(cur["mem"]) if v != prev["mem"][i]
                ],
                **annotations.get(str(first + len(steps)), {}),  # optional title / note
            }
        )

    prev = snapshot()
    if first == 0:
        record(None, prev, prev)
    pc = code_base
    depth = 0  # how many followed calls we're inside
    while pc in by_addr and len(steps) < MAX_STEPS:
        ins = by_addr[pc]
        if ins.mnemonic.startswith("ret"):
            if depth == 0:
                break  # returning from the traced function: done
            depth -= 1
        if ins.mnemonic.startswith("call"):
            if listing[line_of[pc]]["text"].split()[-1] in local_labels:
                depth += 1
            else:
                # step over: the callee is treated as doing nothing
                pc += ins.size
                uc.reg_write(ux.UC_X86_REG_RIP, pc)
        if pc == ins.address:
            _, written = ins.regs_access()
            uc.emu_start(pc, code_base + len(code), count=1)
            pc = uc.reg_read(ux.UC_X86_REG_RIP)
            known_regs.update(SUBREGS.get(n, n) for n in map(ins.reg_name, written))
        cur = snapshot()
        record(line_of[ins.address], cur, prev)
        prev = cur

    if keep := spec.get("show"):
        steps = [s for k, s in enumerate(steps, start=first) if k in keep]

    out = {
        "title": spec.get("title", ""),
        "panels": spec.get("panels", ["c", "asm", "state"]),
        "c": spec["c"].strip("\n").splitlines() if "c" in spec else None,
        "asm": listing,
        "regs": [n for n, _ in shown],
        "mem": [
            {"addr": f"0x{c['addr']:X}", "label": c.get("label", "")} for c in cells
        ],
        "mem_title": spec.get("mem_title", "Memory"),
        "pointers": pointers,
        "steps": steps,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(out, indent=1))
    print(f"{spec_path}: {len(steps)} steps -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
