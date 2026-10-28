// Renders a trace.py JSON trace as a Touying step-through slide.
//
//   #import "asmdemo.typ": trace-demo
//   #trace-demo(slide, json("build/swap.json"))

#let demo-colors = (
  bg: rgb("#03070d"),
  panel: rgb("#0a1626"),
  panel-stroke: rgb("#1d4466"),
  cell: rgb("#0e2238"),
  cell-stroke: rgb("#2a5a80"),
  text: rgb("#e8eef5"),
  dim: rgb("#5d6b7a"),
  muted: rgb("#8fa3b8"),
  accent: rgb("#2fd6e3"), // titles, highlighted line, pointer tags
  hl-fill: rgb("#123a4f"),
  changed: rgb("#f2e35b"), // values that changed in this step
)
#let c = demo-colors

#let panel(title: none, height: 100%, body) = block(
  width: 100%,
  height: height,
  fill: c.panel,
  stroke: 0.8pt + c.panel-stroke,
  radius: 16pt,
  inset: 12pt,
  {
    if title != none {
      text(weight: "bold", size: 0.95em, fill: c.muted, title)
      v(0.4em)
    }
    body
  },
)

// One line of code; `state` is "current", "normal" or "dim".
#let code-line(line, state) = {
  let body = raw(if line == "" { " " } else { line })
  if state == "current" {
    block(
      width: 100%,
      fill: c.hl-fill,
      stroke: 0.8pt + c.accent,
      radius: 3pt,
      inset: (y: 3pt),
      outset: (x: 5pt),
      text(fill: c.accent, weight: "bold", body),
    )
  } else {
    block(inset: (y: 3pt), text(fill: if state == "dim" { c.dim } else { c.text }, body))
  }
}

#let code-panel(title, lines, current, executed: none, size: 0.7em) = panel(title: title, {
  set text(size: size)
  set block(spacing: 0.25em)
  for (i, l) in lines.enumerate() {
    let state = if i == current { "current" } else if executed == none or i in executed {
      "normal"
    } else { "dim" }
    code-line(l, state)
  }
})

#let mono = text.with(font: "DejaVu Sans Mono")

#let value(v, changed) = mono(weight: "bold", fill: if changed { c.changed } else { c.text }, v)

// two-column label/value table
#let kv-grid(rows) = grid(
  columns: (auto, 1fr),
  column-gutter: 1.6em,
  row-gutter: 0.75em,
  ..rows.flatten(),
)

#let regs-panel(data, step, height: 100%) = panel(title: "Registers", height: height, {
  set text(size: 0.6em)
  kv-grid(data.regs.map(r => (
    mono(weight: "bold", fill: c.text, "%" + r),
    value(step.regs.at(r), r in step.changed_regs),
  )))
})

#let mem-panel(data, step, cells: false, height: 100%) = panel(title: data.mem_title, height: height, {
  set text(size: 0.6em)
  if not cells {
    // compact address/value table
    kv-grid(data.mem.enumerate().map(((i, m)) => (
      mono(fill: c.muted, m.addr),
      value(step.mem.at(i), i in step.changed_mem),
    )))
  } else {
    // one box per cell, with pointer tags
    for (i, m) in data.mem.enumerate() {
      let changed = i in step.changed_mem
      let known = step.mem.at(i) != ""
      grid(
        columns: (1fr, 3.6em),
        align: horizon,
        block(
          width: 100%,
          fill: c.cell,
          stroke: 0.8pt + if changed or (known and m.label != "unused") { c.changed } else { c.cell-stroke },
          inset: (x: 8pt, y: 9pt),
          grid(
            columns: (3.4em, 1fr, auto),
            mono(size: 0.8em, fill: c.muted, m.addr),
            text(weight: "bold", m.label),
            value(step.mem.at(i), true),
          ),
        ),
        pad(left: 6pt, text(fill: c.accent, weight: "bold", step.tags.at(i).join("\n"))),
      )
      v(0.5em, weak: true)
    }
  }
})

// The content of subslide `i` (0-based).
#let demo-frame(data, i, dim: false, widths: auto, addrs: false, code-size: 0.7em) = {
  let step = data.steps.at(i)
  let has-notes = data.steps.any(s => s.at("note", default: none) != none)

  // which listing lines have been executed so far (for `dim: true`)
  let executed = if dim { data.steps.slice(0, i + 1).map(s => s.line) } else { none }
  let c-line = if step.line != none { data.asm.at(step.line).c } else { none }

  let title = text(size: 1.15em, weight: "bold", fill: c.accent, step.at("title", default: data.title))

  let panels = data.panels.map(p => {
    if p == "c" {
      code-panel("C code", data.c, if c-line != none { c-line - 1 } else { -1 }, size: code-size)
    } else if p == "asm" {
      // with `addrs: true`, the address replaces the indent so it can be matched against %rip
      let lines = data.asm.map(l => if addrs and "addr" in l { l.addr + "  " + l.text.trim() } else { l.text })
      code-panel("assembly", lines, step.line, executed: executed, size: code-size)
    } else if p == "regs" { regs-panel(data, step) } else if p == "mem" {
      mem-panel(data, step, cells: data.panels.len() == 2 or data.pointers.len() > 0)
    } else if p == "state" {
      stack(spacing: 12pt, regs-panel(data, step, height: auto), mem-panel(data, step, height: auto))
    }
  })
  let cols = if widths != auto { widths } else if data.panels.len() == 3 {
    (1fr, 1fr, 0.75fr)
  } else { (1fr,) * data.panels.len() }

  let note = if has-notes {
    block(
      width: 100%,
      height: 2.6em,
      fill: c.panel,
      stroke: 0.8pt + c.panel-stroke,
      radius: 10pt,
      align(center + horizon, text(size: 0.8em, step.at("note", default: ""))),
    )
  }

  block(height: 1fr, grid(
    rows: (auto, 1fr, auto),
    row-gutter: 14pt,
    title,
    grid(columns: cols, column-gutter: 14pt, ..panels),
    note,
  ))
}

// A Touying slide that steps through the whole trace.
// `slide` is your theme's slide function.
#let trace-demo(slide, data, ..opts) = slide(
  repeat: data.steps.len(),
  self => demo-frame(data, self.subslide - 1, ..opts),
)
