# CarbonShift Scheduling Policy

Cite this document as "CarbonShift Scheduling Policy" when explaining decisions.

## Objective
Minimise CO2 emissions of flexible electrical workloads by choosing the lowest
carbon-intensity start window that still satisfies every hard constraint.

## Hard constraints (never violated)
1. start_time >= earliest_start
2. start_time + duration <= deadline
3. Inflexible jobs run immediately and are never shifted.

## Decision procedure
1. Build a baseline: emissions if the job ran at its earliest_start ("run now").
2. Scan every candidate 30-minute start slot between earliest_start and
   (deadline - duration). Compute the average intensity over the run window.
3. Pick the slot with the lowest average intensity.
4. Compute kg CO2 saved versus baseline.

## Traffic-light risk ratings
- GREEN: a clean window was found that saves >= 15% versus running now.
- AMBER: some saving is available but the deadline limits how clean a window we can
  reach, or running now is already near-optimal.
- RED: the job cannot be shifted — either it is inflexible, or the deadline is too
  tight to move it.

## Operator guidance
- GREEN decisions are safe to apply automatically.
- AMBER decisions are worth a glance: confirm the small saving is worth any
  operational change.
- RED decisions need no action; they explain why no saving is possible.
