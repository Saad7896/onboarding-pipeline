# ADR-002: Mapping specs are immutable, versioned artifacts

## Context
A mapping between a customer's schema and ours is a contract. It changes when
the customer's system changes, when a reviewer corrects a proposal, or when our
canonical schema gains a field. We need to know which contract was in force when
any given record was loaded.

## Decision
Each approved mapping is stored as an immutable version row. Approving or editing
never mutates an existing version: it writes version N+1 with a computed diff,
and marks version N `superseded`. Each version stores:
- the full field mappings and their transform chains
- the source schema fingerprint it was built against
- who approved it and when
- what changed relative to the previous version

## Why
- Auditability: "why does this record look like this?" is answerable by pointing
  at the version that was live at load time.
- Drift detection: comparing an incoming file's fingerprint against the approved
  version's is a cheap, exact check.
- Reversibility: a bad mapping is superseded, not patched over.

## Consequences
- The version table grows, which is acceptable at this scale.
- A schema change (see ADR-003) invalidates existing approved mappings by design;
  they must be re-proposed and re-approved. This is the intended behaviour for a
  contract change, not a bug.
- Approval is refused when a required canonical field is unmapped, so an invalid
  contract cannot be signed.