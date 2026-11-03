# ADR 0004: Pluggable LLM provider and data governance

<!-- DRAFT. State which provider you actually shipped. -->

## Status
Proposed

## Decision
`LLM_PROVIDER` selects stub, ollama-host (default), ollama-incluster or hosted behind one interface
(`api/app/providers/llm`). The key lives only in the `rahbar-secret` Secret, created with `make secret`.
Only questions and retrieved public passages are sent to the model; nothing is logged beyond ids and scores.

## Consequences
Hosted mode sends student questions to a third party: keep personal data out of the corpus and questions.
