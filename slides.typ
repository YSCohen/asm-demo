#import "@preview/touying:0.8.0": *
#import themes.simple: *
#import "asmdemo.typ": demo-colors, trace-demo

#show: simple-theme.with(
  aspect-ratio: "16-9",
  config-page(fill: demo-colors.bg, margin: (x: 1.4em, y: 1em)),
  config-colors(neutral-darkest: demo-colors.text, primary: demo-colors.accent),
)
#set text(font: "Liberation Sans", fill: demo-colors.text, size: 22pt)

// add demos below. they will be concatenated in the final PDF

// &x forces x into a stack slot
#trace-demo(slide, json("build/addr_of_local.json"), dim: true, widths: (1fr, 1.2fr))

// Swap through pointers
#trace-demo(slide, json("build/swap.json"))

// call / preamble / body / epilogue
#trace-demo(slide, json("build/procedure.json"), addrs: true, code-size: 0.55em, widths: (1.2fr, 0.8fr, 1.2fr))

// array indexing
#trace-demo(slide, json("build/array.json"))

// passing a struct by address
#trace-demo(slide, json("build/struct.json"), code-size: 0.55em, widths: (1.3fr, 1fr, 0.7fr))
