# Deploying into a customer's private cloud / VPC

This system is designed to run inside the customer's own environment. Their data
never needs to leave it. This document describes what changes between the sandbox
demo and a customer deployment.

## 1. What actually leaves the environment

The only outbound call is to the LLM provider during mapping *proposal*. That call
carries:

- the canonical schema (ours, not theirs)
- column names, null percentages and distinct counts
- **masked** sample values: `ops@acme.com` becomes `o***@acme.com`, `00123` becomes `00***23`

It never carries full records, and it happens once per onboarding, not per row.
No customer data leaves the environment during transform, validation, loading or
exception handling.

Three deployment modes, in order of strictness:

| Mode | LLM | Data boundary | Mapping accuracy |
|---|---|---|---|
| A — hosted API | Anthropic API | masked metadata egresses | 100% (measured) |
| B — in-cloud model | Bedrock or Vertex in the customer's own account | nothing leaves their cloud | expected ~100% |
| C — no egress | disabled | nothing leaves at all | 88% (measured) |

Mode C is not a degraded fallback bolted on later: the proposer returns `{}` on any
failure and the heuristic layer carries on, so this path is exercised every time
the API is unavailable. The 88% figure is measured, not estimated.

## 2. Packaging

Ship a Helm chart (or ECS task definitions) rather than `docker-compose.yml`:

- images pushed to the customer's own registry (ECR, ACR, Artifactory), never pulled from ours
- every setting supplied via environment variables or a ConfigMap
- API and portal as separate deployments so they scale and are secured independently
- the worker path (currently in-process) becomes its own deployment as volume grows

## 3. Network

- private subnets only; no public ingress to the API
- the portal sits behind the customer's existing load balancer and SSO
- egress allow-list: in Mode A, only the LLM endpoint; in Modes B and C, none
- database reachable only from the application security group

## 4. Data

- managed Postgres (RDS / Cloud SQL) with encryption at rest using a **customer-owned** KMS key
- raw uploads retained in object storage with a retention policy the customer sets; the pipeline never mutates them
- PII masking happens before any prompt is constructed, in `pipeline/llm_mapper.py::mask`, so it cannot be bypassed by configuration
- the canonical store and exception queue live entirely in the customer's database

## 5. Identity and secrets

- secrets from Secrets Manager or Vault; no `.env` files in production
- IAM roles for service identity instead of static credentials
- portal behind the customer's OIDC / SAML provider
- two roles: **reviewer** (propose, review, resolve exceptions) and **admin**
  (approve mappings, change schema). Currently the API is unauthenticated — this
  is the first gap to close before any real deployment.

## 6. Observability

Export via OpenTelemetry to *the customer's* stack (Datadog, CloudWatch, Splunk),
not ours. Metrics that matter:

- exception rate per batch, broken down by `rule_id`
- drift events (each one should page someone)
- mapping proposal latency and LLM error rate
- records loaded vs quarantined per run

Alert thresholds worth setting on day one: any drift event, exception rate above
the baseline established during onboarding, and any run where zero records load.

## 7. Rollout sequence

1. **Sandbox** — synthetic data, our environment, customer watches the demo.
2. **Staging** — a masked extract of their real data in their environment. This is
   where the real schema surprises appear; expect the exception queue to be noisy
   and expect to add transforms and country/enum mappings.
3. **Shadow run** — the pipeline runs in parallel with their existing process and
   outputs are compared. Nothing downstream consumes our output yet.
4. **Cutover** — with the previous process kept available for one cycle.

Mapping approval happens in staging, by *their* data owner, not by us. That is the
point of the approval workflow: the person who knows what `RSK_BND` means signs
the contract.

## 8. Support model

- we see logs and metrics only if the customer shares them; there is no phone-home
- for incidents, the mapping spec (which contains no customer data, only column
  names and transform names) can be exported and shared safely
- every transformation is reproducible from (raw record, mapping version,
  transform registry version), so a disputed record can be explained exactly

## 9. Known gaps before production

- no authentication on the API
- manual migrations instead of Alembic
- in-process job execution; large files should move to a queue and worker
- no automated re-validation of previously loaded records after a schema change
  (CR-001 records loaded under v1 are not retroactively checked against v2)