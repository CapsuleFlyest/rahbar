# Corpus

Source: public Dungeons & Dragons 5th-edition rules documents (Wizards of the Coast) · Documents: 6 · Pages: 799

Why this domain: the 2014 and 2024 rules are the same game with different numbers, so a retriever that
ignores versions quotes a repealed rule with total confidence. That is failure mode E, built in.

| # | File (`source`) | Document | Version | Superseded | Pages |
| --- | --- | --- | --- | --- | ---: |
| 1 | `srd-5-1-2014.pdf` | System Reference Document 5.1 | 5.1 (2014 rules) | yes | 403 |
| 2 | `srd-5-2-1-2024.pdf` | System Reference Document 5.2.1 | 5.2.1 (2024 rules) | no | 364 |
| 3 | `sage-advice-compendium-v2-7-2021.pdf` | Sage Advice Compendium (official rulings) | 2.7 | no | 23 |
| 4 | `player-s-handbook-errata-2021-scanned-copy.pdf` | Player's Handbook Errata, rendered image-only | 2021 | no | 5 |
| 5 | `dungeon-master-s-guide-errata-2021.pdf` | Dungeon Master's Guide Errata | 2021 | no | 2 |
| 6 | `monster-manual-errata-2018.pdf` | Monster Manual Errata | 2018 | no | 2 |

Rule for `superseded`: a document is superseded only when a newer edition of the same document replaced it.
That is true of one document here: SRD 5.1 (2014), replaced by SRD 5.2.1 (2024). The Compendium and the errata
are the latest editions of themselves, so the retriever shows them to every question, and the scanned
errata can actually be retrieved. The retriever hides superseded documents unless the question asks about an
older version.

| # | Required property | Document(s) that provide it | Evidence or notes |
| --- | --- | --- | --- |
| 1 | At least 6 documents, 40 pages | All six rows above | 799 pages in total (767 in the two SRDs alone). All public: SRD 5.1 and 5.2.1 are CC-BY-4.0 (attribution in the README); the other four are free downloads from `media.wizards.com`. Nothing is LLM-generated or behind a login. |
| 2 | Two versions of one policy | SRD 5.1 (2014) and SRD 5.2.1 (2024) | The 2024 SRD replaces the 2014 one. Same topics, different rules: Exhaustion is a six-level table in 5.1 and "-2 to D20 Tests per level, death at 6" in 5.2.1; Hiding is a contested Stealth check in 5.1 and a DC 15 check in 5.2.1. `doc_version` is `5.1` / `5.2.1`; `superseded` is true / false. Golden questions q09-q11 test the filter. |
| 3 | Scanned, image-only PDF | `player-s-handbook-errata-2021-scanned-copy.pdf` | **Simulated scan, stated plainly.** `fetch.py` downloads the real errata PDF and renders each page to a slightly blurred, slightly rotated picture (`rasterize: true`), so no text layer is left. Proof: `pdffonts corpus/raw/player-s-handbook-errata-2021-scanned-copy.pdf` prints only the header row (an empty font list), so the file has no text layer; it has 5 pages and is 1.6 MB of page images. The extract stage must OCR it. Because the text version exists, OCR accuracy can be measured. |
| 4 | A table with real information | SRD 5.2.1 and SRD 5.1 | Hundreds of tables: the armor table (AC, Strength, Stealth, weight, cost), the weapon table, the exhaustion table in 5.1, class feature tables per level. |
| 5 | Long definitions | SRD 5.2.1 (spells, conditions, class features) and the Sage Advice Compendium | Spell and feature descriptions run to many paragraphs; the Compendium answers are long, with reasoning ("RAW", "RAI") that a fixed-size chunker cuts in half. Both SRDs use a two-column layout, which makes extraction harder (see `PIPELINE.md`). |
| 6 | A deliberately absent topic | Mind flayers and the 4th-edition Warlord class | Neither is in any of the six documents (check with `pdftotext` and `grep`, run after `make fetch`). A player plausibly asks about both: mind flayers are famous monsters, and the Warlord is a class people remember from the previous edition. Golden questions q14 and q15 expect a refusal. |
| 7 | Exact-term content | Armor costs and Strength requirements, DCs, dice | Plate Armor: 1,500 GP, Strength 15, 65 lb. Half Plate Armor: 750 GP, 40 lb. Hide action: DC 15. Death Saving Throw: roll 10 or higher. Golden questions q12 and q13. |

## Where the files come from

`corpus/sources.yaml` lists every document. `python corpus/fetch.py` (or `make fetch`) re-records the two
committed SRDs (already in `corpus/raw/`) in the manifest, downloads the other four politely (one request at a time, a pause
between), rasterizes the scanned copy, and writes `corpus/MANIFEST.md` with every URL and SHA-256.
`python corpus/fetch.py --verify` re-checks the bytes. The two SRD PDFs are committed because their
CC-BY-4.0 licence allows it; the other four are not, because they are not ours to redistribute.

## Known traps in this corpus

- The 2014 and 2024 SRDs have different headings and numbers for the same rule; a prompt cannot tell them apart, only metadata can.
- The Sage Advice Compendium and the errata describe the 2014 books but are not superseded, so they can surface next to 2024 rules. Their chunks carry `doc_version` 2.7 / 2021 / 2018, so a citation shows which edition a rule comes from.
- SRD 5.1's text layer breaks words across lines; SRD 5.2.1's page footers ("13 System Reference Document 5.2.1") look like headings to a naive chunker.
