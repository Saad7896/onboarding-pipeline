# ADR-004: Refuse ambiguous dates rather than guessing

## Context
Source files arrive with dates in multiple formats within a single column.
A value like `06/01/2025` is genuinely ambiguous: it is 6 January under
DD/MM and 1 June under MM/DD. Nothing in the value itself resolves it.

## Decision
`parse_date` refuses any NN/NN/YYYY value where both leading components are
<= 12 and differ. The record enters the exception queue with the reason and a
suggested fix ("confirm the source system's date order").

## Why
A guess that is wrong by five months is invisible: the record loads, looks
plausible, and corrupts every downstream calculation that uses the date. One
exception row and one question to the customer is far cheaper than discovering
this in a quarterly report.

## Measured impact
In the evaluation set, this rule produced exceptions in S2 and S3. Writing the
expected outcomes by hand before running the eval revealed that the S2 test
data contained an ambiguous date the author had not noticed - evidence that
these values are common, not edge cases.

## Consequences
- More exceptions on first load for customers using NN/NN/YYYY formats.
- Future work: a `date_order` option on the mapping spec, confirmed once with
  the customer at onboarding, which would resolve the whole column
  deterministically instead of row by row.