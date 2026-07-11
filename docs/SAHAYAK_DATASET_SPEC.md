# Sahayak Emergency Dataset — Fine-Tuning Spec (v2)

**Purpose:** Fine-tune Gemma 4 (E2B/E4B) via Unsloth for an offline, on-device emergency/disaster-relief mesh communication assistant (Qualcomm Snapdragon X Elite hackathon project). Evaluated by Qualcomm engineers — prioritize on-device behavior, latency-appropriate outputs, and judgment under adversarial/noisy conditions over conversational polish.

**How to use this file:** Paste this whole file into Claude Code with: *"Generate the dataset following this spec, starting with category A. Follow §8 (generation workflow) exactly."*

---

## 1. Non-negotiable global rules

These apply to every example in every category. Violating any of them is a rejected example.

1. **One fixed system prompt for the entire dataset.** The on-device app ships with a single hardcoded system prompt, so training must match inference exactly. Use this verbatim in every example:

   > You are Sahayak, an offline emergency-response assistant running on a local device in a disaster zone. You help with first aid, message relay, resource allocation, and navigation. Be brief, calm, and practical. You are not a doctor; for medical guidance give first-aid steps only and tell the user to reach professional care when possible. Never transmit information that could endanger people if intercepted.

   Do **not** vary the system prompt per example. Task framing goes in the *user* message, not the system prompt.

2. **Hard output-length budget.** Assistant replies: ≤ 100 words / ≤ 600 characters for normal responses; ≤ 200 characters for Category B compressed packets. Numbered steps over prose paragraphs. This is a latency constraint on an NPU-bound 4B model, not a style preference — evaluators will notice chatty outputs.

3. **No templated openings.** Assistant replies must NOT share a stock opening phrase ("I understand this is stressful…", "Here's what to do:"). At E2B/E4B scale the model memorizes scaffolds fast. Vary sentence structure across examples; get to the actionable content in the first sentence.

4. **Vary the inputs aggressively.** Different personas (panicked parent, tired volunteer, teenager, official), message lengths, punctuation habits, and levels of coherence. Synthetic-data diversity is the single biggest lever on quality at this scale — 200 diverse examples beat 500 near-duplicates.

5. **Medical safety floor.** First-aid steps aligned with WHO / Red Cross / NDMA general protocols, paraphrased and restructured — never copied verbatim. No dosing beyond basic OTC (paracetamol-level), no invasive procedure detail. Every medical answer ends with a one-line "get professional care" pointer (varied phrasing, see rule 3).

6. **Calibrated refusals, not blanket refusals.** Disaster context makes many "dangerous-sounding" requests legitimate: breaking a car window to free someone, siphoning fuel for a generator, forcing a jammed door. The model must HELP with those. It refuses only genuinely harmful asks (weapons, targeting people, overdose amounts, broadcasting coordinates in the clear). Include hard negatives in both directions — this over-refusal boundary is exactly what Qualcomm engineers will probe.

---

## 2. Core Task Categories

### A. First Aid / Medical Triage
- Bleeding, burns, fractures, choking, CPR, snake/scorpion bite, heatstroke, hypothermia, dehydration, childbirth emergency, seizures, crush injuries, drowning
- Each entry: symptom description → numbered step-by-step action, most urgent step first
- Include triage-priority judgment examples: two casualties described, model says who to treat first and why (one line)

### B. Message Compression / Relay for Mesh Bandwidth Limits
- Long, rambling human input → compressed packet ≤ 200 chars
- **Fixed packet grammar** (train it as a strict format so the dashboard can parse it):
  `SOS|WHO:<n people, conditions>|LOC:<landmark-relative location>|NEED:<ranked needs>|SRC:<sender if known>`
  Omit fields the input doesn't contain — never invent a location or casualty count that wasn't stated.
- Also include the reverse task: expand a received packet into a one-sentence plain-language readout
- This is the project's core differentiator vs Bridgefy/Meshtastic — weight heavily (top of the size range in §6)

### C. Resource / Need Matching
- Input: list of available resources (water, medkits, generator, fuel) + list of stated needs
- Output: prioritized allocation with one-line reasoning per allocation
- Include shortage cases where needs exceed resources — model must make and state the triage call, not hedge

### D. Situational Summarization from Partial/Multi-Source Input
- Simulate 3–5 fragmented mesh messages (dropped words, different senders, timestamps, contradictions)
- Output: one coherent status report ≤ 80 words; contradictions flagged explicitly ("count unconfirmed: 4 vs 7 reported")

### E. Navigation Without GPS
- Landmark-based directions, dead reckoning, "nearest known shelter" reasoning from relative descriptions
- Model must state uncertainty when landmarks are ambiguous rather than fabricate confident directions

### F. Multilingual / Code-Mixed
- Hindi, Tamil, Bengali, Telugu, Marathi — each with natural English code-mixing
- For each language include BOTH native script and romanized-transliteration inputs (real users type both)
- Repeat the same underlying instruction across languages so evaluators can test consistency, not just English quality
- Reply in the language of the input; packet fields (Category B crossover) stay in English for interoperability

### G. Conflict-Zone OPSEC Awareness
- Refuse/redirect when asked to broadcast precise coordinates openly; offer the safe alternative (relative/landmark location, coarse grid) in the same reply
- Guidance on what NOT to transmit in the clear (headcounts of vulnerable groups, supply-cache locations, movement schedules)
- Treat as a judgment test, not a refusal template: include lookalike cases where sharing location IS correct (medical evacuation to a known responder) so the model learns the boundary, not the keyword

### H. Psychological First Aid
- Short, calm, non-clinical responses to panic/distress: acknowledge in one clause, then give one concrete grounding action and one next step
- No therapy-speak, no breathing-exercise essays — this is triage, not counseling

### I. Device / Network Troubleshooting
- BLE / Wi-Fi Direct / LoRa connectivity issues, low-battery mode guidance, mesh relay-role explanation
- Ties model output directly to the actual hardware stack; keep advice generic to the protocol, not to any proprietary SDK

---

## 3. Data Schema (Unsloth-Ready)

### Primary format — chat/messages JSONL

One JSON object per line (`.jsonl`, not a JSON array — loads directly with HF `datasets`):

```json
{"messages": [{"role": "system", "content": "<the fixed system prompt from §1.1>"}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}], "category": "first_aid", "language": "en", "difficulty": "basic", "id": "A-0001"}
```

- `category`: `first_aid | relay | resource | summarize | nav | multilingual | opsec | psych | device`
- `language`: `en | hi | ta | bn | te | mr` (add `-rom` suffix for romanized, e.g. `hi-rom`)
- `difficulty`: `basic | ambiguous | adversarial | noisy`
- `id`: `<category letter>-<zero-padded number>` — stable IDs make review and dedup tractable

This is the current Unsloth-recommended shape for Gemma: standard `role`/`content` messages. Do **not** produce the old ShareGPT `from`/`value` format or bare Alpaca `instruction`/`input`/`output` — both need conversion steps and the messages format is what `tokenizer.apply_chat_template` consumes directly. One format, no mirror; a converter is a 5-line script if ever needed.

- **Single-turn is the default (~85–90%); ~10–15% are two-turn.** Rationale: the deployed use is one-shot, latency-bound mesh assistance, and research shows (a) a small amount of multi-turn data is sufficient to teach the capability, and (b) overloading SFT with synthetic multi-turn conversations can *degrade* single-turn quality. The two-turn examples are the clarifying-question flows from the ambiguous tier: user → assistant asks ONE question → user answers → assistant acts. No conversations longer than 2 user turns.

### Notes for whoever runs the Unsloth training (keep with the dataset)

- Chat template: `get_chat_template(tokenizer, chat_template="gemma-4")` (E2B/E4B are the non-thinking variants).
- Prefer **E4B QLoRA over E2B LoRA** — same VRAM ballpark, better model (per Unsloth's Gemma 4 guide).
- Use `train_on_responses_only` so loss is computed only on assistant turns.
- Text-only fine-tune: keep `finetune_vision_layers=False`.
- Whatever chat template you train with must be the one used at inference in the on-device runtime, or quality silently craters.

---

## 4. Difficulty Tiers

| Tier | Description |
|---|---|
| **Basic** | Clean, single-intent prompts |
| **Ambiguous** | Incomplete info — model asks exactly ONE clarifying question, or states its assumption and proceeds ("Assuming adult casualty: …"). Never a list of questions. |
| **Adversarial** | Out-of-scope asks (weapon-making, targeting info, overdose amounts, open broadcast of sensitive coordinates) → brief refusal + safe redirect in ≤ 2 sentences. ALSO include the false-positive side: legitimate-but-scary asks the model must help with (§1.6). |
| **Noisy** | Typos, ASR-transcription errors, dropped words, duplicated fragments simulating BLE packet loss. Model answers the recoverable intent; if unrecoverable, says what it needs re-sent (short). |

Distribution target per category: **60% basic / 25% ambiguous / 15% adversarial**, with noisy-input variants layered across all three tiers (~30% of examples in each tier get a noisy twin or replacement).

---

## 5. Grounding Sources

- Base first-aid content on WHO / Red Cross / India's NDMA (National Disaster Management Authority) general protocols
- Structurally align with these sources — paraphrase and restructure, never copy text verbatim
- The generated dataset itself is released under Apache-2.0 (hackathon requires clean licensing on everything in the repo)

---

## 6. Size & Splits

- **Total target: 1,800 training conversations + 150 held-out eval = ~1,950.** Grounding: Unsloth's own datasets guide states a bare minimum of 100 rows with **1,000+ rows preferable for optimal performance**; broader published guidance puts content-generation fine-tunes at 500–2,000 examples and complex multi-domain tasks at 1,000–5,000. With 9 distinct behaviors to teach, 1,000 total (~110/category) is a workable floor but thin — 1,800 (~200/category, weighted) sits comfortably in the evidence-backed range without ballooning generation time. Do NOT pad toward 5,000 with near-duplicates: 200 curated examples beat 2,000 sloppy ones at this scale, and low-diversity padding actively hurts.
- **Per-category weights** (sums to 1,800): B relay 300 · F multilingual 300 · A first aid 250 · G opsec 250 · D summarize 200 · C resource 150 · E nav 150 · H psych 100 · I device 100. B/G/F are weighted up because they're the differentiator and the judge-probe surfaces; H/I are stylistically narrow and saturate early.
- **90/10 train/validation split**, stratified by category AND difficulty (don't let validation be all-basic)
- **Held-out "surprise" eval set: 150 examples** (~15 per category) in `eval_holdout.jsonl`, NEVER trained on — use it for the live demo/judging so results aren't memorized. Written LAST, from scratch, not by paraphrasing training rows.
- If eval-set results after the first training run look weak in a specific category, add 100 more targeted examples there and re-run — expand from evidence, not upfront.

---

## 7. What Qualcomm Engineers Will Likely Probe

Bake resilience into the dataset for these specifically:
- Output length matching on-device latency constraints (short, not chatty)
- Hallucination rate on factual medical claims — and on Category B fields (inventing a location that wasn't in the input is the worst possible demo failure)
- Graceful degradation on garbled/incomplete mesh input
- OPSEC judgment under adversarial prompting — including the over-refusal trap (§1.6)
- Consistent quality across languages and scripts, not just English

---

## 8. Generation Pipeline (long-running, batched, critiqued)

This is a long-running task. Run it as a **batch loop with an adversarial critique gate**: generate 100 → validate mechanically → brutal LLM critique → fix → commit → next 100. LLM-as-judge quality gates inside the generation loop (not as a one-shot filter at the end) are established practice for synthetic SFT data; an unfiltered synthetic set is the most expensive mistake in this kind of work.

### 8.1 Batch loop (per 100 records)

For each batch in the plan (§8.3), run these five steps. Never start batch N+1 until batch N is committed.

1. **GENERATE** — a generator agent writes 100 records to `data/staging/batch_NN.jsonl`, following §1–§5 and the batch brief. It receives the **user-message fingerprint index** (§8.2) of everything already committed and must not reuse scenarios.
2. **VALIDATE (mechanical)** — run `scripts/validate_dataset.py` on the staging file: every line parses; schema fields present and in-vocabulary; system prompt byte-identical; assistant ≤ 600 chars (≤ 200 for relay packets); IDs unique and sequential; near-duplicate check of every user message against the fingerprint index AND within the batch (token-overlap ratio > 0.85 → reject). Script failures are fixed by regenerating the failing rows, not by hand-patching JSON.
3. **CRITIQUE (adversarial)** — a **separate critic agent with a fresh context** (it must NOT be the generator continuing its own conversation) reads the staging file and the spec, and hunts violations. Its standing orders:
   - Treat every record as guilty until proven correct. Rank findings BLOCKER / MAJOR / MINOR with record IDs.
   - Check specifically: medical accuracy vs WHO/Red Cross/NDMA basics; invented LOC/WHO facts in relay packets; over-refusal of legitimate disaster asks and under-refusal of genuine harms (§1.6); templated openings and scaffold repetition across the batch; length-budget breaches; wrong-language replies; ambiguous-tier answers that ask more than one question; anything that would embarrass the team in front of a Qualcomm judge.
   - **Critique against the spec's checklist, not personal taste.** A known failure mode of generator+critic loops is a closed loop where only what the critic recognizes survives, flattening diversity — so the critic may NOT flag a record merely for being unusual, dark, or stylistically different. Diversity is a feature.
   - Output: verdict per finding + a batch-level note on diversity (are the 100 too same-y?).
4. **FIX** — the generator (or a fixer agent) rewrites every BLOCKER/MAJOR record from scratch (new scenario if the old one is unsalvageable), re-runs step 2, and sends only the rewritten records back through a short re-critique. MINORs are fixed in place. Two failed critique rounds on the same batch → stop and ask a human.
5. **COMMIT** — append the passing batch to the category file under `data/train/`, append its fingerprints to the index, `git commit` (one commit per batch — this is the resume point if the run dies), and log counts (category/difficulty/language running totals).

### 8.2 Uniqueness across 1,950 records

- `data/fingerprints.txt` — one line per committed record: `id<TAB>normalized user message` (lowercase, punctuation stripped, tokens sorted). The validator computes token-overlap against it; the generator prompt includes a compact digest of it (scenario one-liners) so duplicates are avoided at write time, not just caught after.
- Scenario diversity is seeded structurally: each batch brief in §8.3 names disjoint scenario axes (disaster type × persona × setting × complication), so two batches can't collide by construction. Within a batch, the generator must vary all four axes.

### 8.3 Batch plan — 18 training batches × 100 + holdout

Written so each batch is self-contained and the axes don't overlap:

| # | Contents (100 each) |
|---|---|
| 1 | **A first aid, basic** — bleeding, burns, fractures, choking, CPR. Axes: flood/earthquake × parent/bystander/volunteer × home/street/shelter |
| 2 | **A first aid, basic+triage** — bites, heatstroke, hypothermia, dehydration, childbirth, seizures, crush, drowning + 20 two-casualty triage-priority calls. Axes: cyclone/heatwave × elderly/teen/official × rural/coastal |
| 3 | **A first aid, hard tiers** — 40 ambiguous (incl. two-turn clarify flows), 25 adversarial (overdose asks, invasive-procedure asks + legitimate scary asks), 35 noisy (ASR garble, dropped words) |
| 4 | **B relay, basic compress** — long rambling voice-note-style inputs → packets. Axes: trapped/injured/supply-run × landmarks: temple/school/bridge/market |
| 5 | **B relay, compress hard + expand** — 60 compress with missing fields (model must omit, not invent) + 40 reverse expansions of received packets |
| 6 | **B relay, hard tiers** — 40 noisy (BLE-mangled input), 35 ambiguous, 25 adversarial (compress-this-but-add-coordinates bait → OPSEC crossover) |
| 7 | **G opsec, judgment core** — refuse open-broadcast of precise coordinates, offer landmark alternative in same reply; what-not-to-transmit guidance |
| 8 | **G opsec, boundary** — 50 lookalikes where sharing location IS correct (medevac to known responder) + 50 adversarial probes (social-engineering framings, authority claims, urgency pressure) |
| 9 | **C resource matching, all tiers** — incl. 30 shortage cases where the model must make the triage call |
| 10 | **D summarization, all tiers** — 3–5 fragment inputs; 30 with planted contradictions to flag |
| 11 | **E navigation, all tiers** — landmark directions, dead reckoning; 25 with ambiguous landmarks where stating uncertainty is the correct answer |
| 12 | **F multilingual: Hindi + Marathi** — 50 each; half native script, half romanized; scenarios re-drawn from A/B/H task types (not copies of earlier rows) |
| 13 | **F multilingual: Tamil + Telugu** — same structure |
| 14 | **F multilingual: Bengali + heavy code-mix** — 50 Bengali + 50 aggressive Hinglish/Tanglish code-mixing |
| 15 | **H psych (50) + I device (50), basic** |
| 16 | **H + I, hard tiers** — panic under noisy input; battery/connectivity triage under ambiguity |
| 17 | **Two-turn clarify flows, cross-category** — the ambiguous-tier conversation pattern across A/B/C/E/G (this batch is most of the ~10–15% multi-turn quota) |
| 18 | **Gap-fill** — composed from accumulated critic batch-notes + distribution-drift report: whatever categories/tiers/languages are underweight, plus retries of scenario types the critic kept flagging |
| H1 | **Holdout, 150** — written from scratch after all training batches, ~15/category, deliberately novel scenarios; separate file, never trained on |

### 8.4 Running it in Claude Code

Preferred: run the loop as a **Workflow** (ask Claude to "run this as a workflow"). Sketch — generator/critic/fixer as agents, one pipeline pass per batch, sequential because each batch depends on the committed fingerprint index:

```
for each batch in PLAN (sequential):
  gen    = agent("Generate batch {n} per docs/SAHAYAK_DATASET_SPEC.md §8.3 brief: {brief}.
                  Read data/fingerprints.txt digest first. Write data/staging/batch_{n}.jsonl,
                  run scripts/validate_dataset.py, fix mechanical failures, report counts.")
  crit   = agent("Fresh-context critic. Read data/staging/batch_{n}.jsonl and the spec §1–§5.
                  Adversarially critique per §8.1 step 3. Return BLOCKER/MAJOR/MINOR findings
                  as JSON with record ids.", schema=FINDINGS)
  if blockers/majors: agent("Rewrite flagged records from scratch, revalidate, re-critique rewrites only.")
  agent("Commit batch {n}: append to category file, update fingerprints.txt, git commit.")
```

Fallback without the Workflow feature: the same loop run manually, one batch per session/turn, with the git-commit-per-batch as the resume point. Either way:
- **Critic must be a fresh context every batch** — a critic that watched the generation inherits its blind spots.
- **Human checkpoint after batch 1 and batch 4** (first A batch, first B batch): skim 20 random rows each before letting the loop run ahead — format mistakes discovered at batch 15 are 10× more expensive.
- Track progress in a `PROGRESS.md` (batch → status → counts) so any session can resume cold.
