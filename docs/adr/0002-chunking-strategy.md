# ADR 0002: Structure-aware chunking with overlap

<!-- DRAFT. Fill in your measured recall@5 for 3 (size, overlap) settings from docs/PIPELINE.md. -->

## Status
Proposed

## Context
Clauses and long definitions must not be cut in half; fixed windows do that.

## Decision
Split on headings, then paragraphs, then sentences, under a word budget (`CHUNK_SIZE`, default 400),
sharing `CHUNK_OVERLAP` words (default 50) inside a section. Tables are kept whole, split by rows with the header repeated.
Unit: whitespace-separated words. The shipped values are decided by measurement, not by this draft.

## Options considered
Fixed-size windows (`CHUNK_STRATEGY=fixed`) are kept only for the break-the-pipeline experiment.

## Consequences
Section headings are stored with every chunk, which gives citations and version filtering.
