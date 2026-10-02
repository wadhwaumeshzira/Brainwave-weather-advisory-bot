---
name: sop-authoring
description: Use when writing or editing SOP policy YAML files in sops/ for the weather-advisory bot. Covers schema, severity use, thresholds, fuzzy and regime SOPs.
---

# Writing SOPs

An SOP is a testable rule: condition -> advice at a severity. It must be specific enough
that a script can check it. "Be careful in bad weather" is NOT an SOP.

## Checklist for each SOP
- Unique stable `id` like `CAT-TOPIC-NN`. Never reuse or renumber ids.
- One condition set a script can evaluate against the fetched fields. Use real units
  (km/h, mm, %, UV index, deg C). State the threshold and the time window.
- `advice` tells the user what to DO (avoid, reschedule, precautions), in 1-3 sentences,
  with no numbers hardcoded that the data should supply (numbers come from the facts dict).
- `description` explains intent in plain words, not a keyword list, so semantic routing works
  for paraphrases.
- Pick severity honestly: info, low, moderate, high, critical. Not everything is high.

## Required coverage (12 SOPs is a good target)
- >= 3 categories: outdoor_exercise, travel, vulnerable_groups (children / elderly / pets), general.
- Mixed severities, including at least a few info/low ones.
- 1 fuzzy SOP (e.g. "good day for a picnic"): use `n_of` (e.g. at least 3 of: temp 18-32C, rain
  probability < 30%, gusts < 25 km/h, UV < 8, no thunderstorm code). Explain in the file comment why.
- 1 regime SOP: heavy-rain system. Signals: daily precipitation_sum >= 64.5 mm (IMD "heavy" starts
  at 64.5 mm/24h; "very heavy" 115.6 mm), OR heavy-rain/thunderstorm weather codes (65, 82, 95-99)
  with many precipitation_hours, with high gusts as a reinforcing signal. `lead_with: true`,
  `overrides_scope: true`, severity critical. The reason is bigger than any single threshold,
  so combine signals with `any` of `all` groups.

## Do not
- Do not write SOP-specific Python. If a rule cannot be expressed, extend the generic
  evaluator once, for all SOPs, and tell the student.
- Do not copy the assignment's example SOPs verbatim.
- Do not give medical or legal claims beyond "avoid / reschedule / take precautions".

## Template
See the schema in AGENTS.md. Add a YAML comment at the top of each file with one line on
why the thresholds were chosen.
