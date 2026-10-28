EXAMPLES := $(wildcard examples/*.toml)
TRACES   := $(patsubst examples/%.toml,build/%.json,$(EXAMPLES))

build/slides.pdf: slides.typ asmdemo.typ $(TRACES)
	typst compile slides.typ $@

build/%.json: examples/%.toml trace.py
	uv run trace.py $< $@

traces: $(TRACES)

# live preview: re-run `make traces` after editing a .toml
watch: $(TRACES)
	typst watch slides.typ build/slides.pdf

clean:
	rm -rf build

.PHONY: traces watch clean
