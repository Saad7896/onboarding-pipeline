# CR-001: Add required risk_tier field

**Requested:** mid-onboarding, after mapping v2 was approved and data had loaded.
**Request:** "Compliance now requires a risk tier on every customer. Our CRM
exports it as `risk_tier` with values high / medium / low."

## Predicted impact (written BEFORE implementing)
- `pipeline/canonical.py` — add the field
- `pipeline/transforms.py` — add an enum normalizer
- DB migration — add the column
- No changes to: profiler, mapper, runner, validation engine, loader, drift, API

## Why the blast radius is small
The pipeline engine is driven by data, not code. Transforms come from a registry,
validation rules read `required` from the schema, and mappings are versioned specs.
Adding a field is therefore a configuration change, not an engine change.

## Actual impact
(filled in after implementation)

## Consequences
- Existing approved mappings do not satisfy the new schema, so a new mapping
  version must be proposed and approved. This is intentional: the schema change
  is a contract change.
- Records loaded under schema v1 predate the requirement. They are not
  retroactively invalidated in this MVP; a re-validation job would be the
  production approach.