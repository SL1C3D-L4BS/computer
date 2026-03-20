---
name: Bug report
about: A service is behaving incorrectly or an invariant is violated
labels: bug
---

## Summary

_One sentence: what is wrong._

## Service / component

_Which service, package, or CLI command is affected._

## Steps to reproduce

1.
2.
3.

## Expected behavior

_What should happen._

## Actual behavior

_What actually happens._

## Trace ID (if available)

_Run `computer trace <trace_id>` and `computer explain <trace_id>` before filing. Paste trace_id here._

## Invariant violation?

- [ ] No invariant violation
- [ ] Invariant violated — which one: `I-___`

## Severity

- [ ] Safety-critical (invariant violation, wrong actuation)
- [ ] Trust-degrading (wrong decision, missed interrupt, memory leak)
- [ ] Operational (service unavailable, slow, misconfigured)
- [ ] Cosmetic (wrong output format, incorrect label)

## Environment

- Version / commit:
- Mode at time of issue:
- System load / context:
