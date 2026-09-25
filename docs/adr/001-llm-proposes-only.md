# ADR-001: The LLM proposes mappings; it never transforms data

## Context
Column names and semantics vary wildly between customer systems. Fuzzy string
matching handles obvious cases but fails on abbreviations (`CO_NM`) and vague
names (`region`, `tier`). An LLM handles these well.

## Decision
The LLM participates in exactly one step: proposing which source column maps to
which canonical field, with a confidence score and a rationale. It never:
- transforms a value
- writes to the canonical store
- resolves an exception
- introduces a transform function

All value changes are made by pure functions in a fixed registry, selected by
name in a human-approved mapping spec.

## Why
A wrong transform silently corrupts customer data and may go unnoticed for
months. A wrong mapping proposal is caught at review, before any data moves.
Restricting the model to the reversible step keeps its errors cheap.

## Consequences
- Every transformation is reproducible from (raw record, mapping version,
  transform registry version).
- The model only sees column names, statistics and masked samples, which
  simplifies the data-residency conversation with customers.
- The system degrades to heuristics-only when the model is unavailable or
  when a customer forbids external calls.
- Measured cost: heuristics alone reached 88% mapping accuracy; with the LLM,
  100% (see EVAL_REPORT.md). The added latency is 3-6s per schema.