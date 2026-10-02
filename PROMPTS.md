# PROMPTS.md: paste these into Antigravity one at a time

Rule: after each phase, DO NOT move on until you can explain the output in your own words.
Use the "Check yourself" lines. If you can't answer, ask Antigravity to explain that file again.

First message to Antigravity (once):
> Read AGENTS.md and the skills in .agent/skills fully. Confirm you understand the non-negotiables
> and the working rules (one phase at a time, EXPLAIN block, 3 questions). Do not write code yet.

---
## Phase 1: Weather client
> Phase 1. Implement app/config.py and app/weather.py: geocode(city) via Open-Meteo geocoding
> (empty result or error => raise a typed LocationError) and fetch_weather(lat, lon) with the wide
> field superset from AGENTS.md, timezone=auto, forecast_days=2. Support WEATHER_MODE=fixture
> (read evals/fixtures/<name>.json) and WEATHER_FORCE_FAIL=1 (raise WeatherError). Add timeouts.
> First make one real call and show me the raw response shape. Then EXPLAIN and ask me 3 questions.

Check yourself: what happens on timeout? why timezone=auto? where do the numbers come from?

## Phase 2: SOP engine (the heart; spend the most time here)
> Phase 2. Write the SOP YAML schema usage in app/sops.py: load_sops(dir) with validation
> (unique ids, required keys), evaluate_conditions(sop, weather) as ONE generic function
> (field/agg/scope/op, all/any/n_of), and rank_and_resolve(matched). No LLM here, pure functions.
> Then write 12 SOPs in sops/ following the sop-authoring skill (>=3 categories, mixed severities,
> one fuzzy picnic-type SOP using n_of, one heavy-rain regime SOP with lead_with + overrides_scope).
> Add small pytest unit tests for the evaluator. EXPLAIN and ask me 3 questions.

Check yourself: how would I add an 11th SOP live? what if a field is missing in the data?
how is "any/all/n_of" evaluated? why is severity ranked in code, not by the LLM?

## Phase 3: Graph skeleton without the LLM
> Phase 3. Build app/state.py, app/nodes.py, app/graph.py with the full node/edge layout from AGENTS.md,
> but stub parse_intent/route_sops/compose_reply with simple deterministic fakes so we can test the
> branching first. Use MemorySaver and thread_id. Show me a printed trace for: success path,
> location failure, weather failure, no-match. EXPLAIN and ask me 3 questions.

Check yourself: draw the graph on paper. Which function decides each branch?

## Phase 4: Add the LLM parts
> Phase 4. Implement app/llm.py (init_chat_model from env), real parse_intent (structured output,
> includes session carry-over for follow-ups), route_sops (returns ONLY ids from an enum of loaded
> SOP ids), compose_reply (gets only matched SOP advice + a facts dict; user text as quoted data),
> and app/validators.py + validate_reply + template_reply fallback. EXPLAIN and ask me 3 questions.

Check yourself: where exactly is "LLM can't invent numbers" enforced? what if the LLM cites SOP-999?

## Phase 5: API + frontend
> Phase 5. app/main.py with POST /chat {session_id, message} -> {reply, sop_ids, trace} and GET /
> serving static/index.html (minimal chat thread, generates a session_id in the browser, shows
> cited SOP ids under each reply). Keep it tiny. EXPLAIN and ask me 3 questions.

## Phase 6: Evals (carries the most weight)
> Phase 6. Follow the eval-writing skill. Create evals/cases.yaml, fixtures, run_evals.py and
> evals/RESULTS.md. Required: 2 clear-SOP cases, 2 paraphrase cases, 1 severe-live case (fixture-based
> for determinism + one optional live run flagged as time-dependent), 1 no-SOP case, 1 API-down case,
> 1 adversarial/injection case. Report PASS/FAIL honestly; if something fails, keep it failing and
> explain why, don't tweak the test to pass. EXPLAIN and ask me 3 questions.

## Phase 7: Deploy + README
> Phase 7. Prepare deployment on Render (or Railway) as a single FastAPI service serving the static
> frontend: start command, env vars list, health check. Then write README.md per the "Definition of
> done" in AGENTS.md. Keep the write-up honest about gaps. EXPLAIN and ask me 3 questions.

---
## Before submitting
- [ ] `git log -p | grep -i "api_key"` finds no real key
- [ ] Live URL opens and a follow-up question works
- [ ] I can add an 11th SOP in under 2 minutes without editing .py files
- [ ] I can explain every node, every branch, and the validator out loud
- [ ] Notes box in the form: trade-offs, AI tools used, what I'd do next
