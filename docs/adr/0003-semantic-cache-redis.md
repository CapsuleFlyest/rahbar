# ADR 0003: Redis for the semantic cache

<!-- DRAFT. Defend or change it in your own words. -->

## Status
Proposed

## Decision
Redis (Deployment + PVC `cache-data`), cosine similarity in the API against stored question vectors,
threshold from `CACHE_THRESHOLD`. Keys include the index `index_id` (generation), so re-indexing makes old
entries unreachable. Follow-ups, abstentions, fallbacks and anything that failed validation are never cached.

## Options considered
A second Chroma collection: one fewer component, but cache writes would go through the vector store
that must stay read-only for the api. Rejected for that reason.

## Consequences
Redis has no auth; a NetworkPolicy allows only the api to reach it. A Redis outage is a cache miss, never an error.
