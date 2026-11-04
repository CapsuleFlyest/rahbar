# CI fixtures

Three short Markdown documents for the `e2e-eval` job (section 6), so CI can index
a corpus and score recall in a minute instead of six. They are excerpts of the D&D
System Reference Documents (CC-BY-4.0), cut down to a few sections each.

| File | Why it is here |
| --- | --- |
| `srd-5-1-excerpt.md` | The superseded version (2014 rules): exhaustion is a 6-level table, hiding is a contested check |
| `srd-5-2-1-excerpt.md` | The current version (2024 rules): exhaustion is -2 per level, Hide is DC 15, plus one planted injection line |
| `armor-table-2024.md` | A table and exact-term numbers (cost, Strength 15) |

Mind flayers are missing on purpose: `golden.fixture.yaml` asks about them and
expects the service to decline.

Each file starts with front matter (`doc_version`, `superseded`). The indexer's
`discover()` reads it when there is no `_index.json`, so your extract stage
needs to handle `.md` files as well as PDFs.
