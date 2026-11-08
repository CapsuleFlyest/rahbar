# CI fixtures

Three short Markdown documents for the `e2e-eval` job (section 6), so CI can index
a corpus and score recall in a minute instead of six. They are excerpts of the D&D
System Reference Documents (CC-BY-4.0), cut down to a few sections each.

| File | Why it is here |
| --- | --- |
| `srd-5-1-excerpt.md` | The superseded version (2014 rules): exhaustion is a 6-level table, hiding is a contested check |
| `srd-5-2-1-excerpt.md` | The current version (2024 rules): exhaustion is -2 per level, Hide is DC 15, plus one planted injection line |
| `armor-table-2024.md` | A table and exact-term numbers (cost, Strength 15) |

`golden.fixture.yaml` asks something far outside the corpus (the capital of France) and
expects the service to decline. In CI the model is a stub that always answers when it is
given a passage, so this check can only pass through the relevance floor, and a question
about D&D itself (mind flayers) would score above the floor. The near-domain abstention
questions (mind flayers, the Warlord class) are tested in `eval/golden.yaml` against the real stack.

Each file starts with front matter (`doc_version`, `superseded`). The indexer's
`discover()` reads it when there is no `_index.json`, so your extract stage
needs to handle `.md` files as well as PDFs.
