# Project Rudder notes

Snorkel AI "Project Rudder - Rating" (expertdocs.snorkel-ai.com/rudder-comparison-preference/how-to-task/submission-guidelines). Learned 2026-09-23 from the Submission Guidelines page. Separate from Project Geranium.

**Task:** one general chat prompt (no domain expertise needed) + Response A and Response B. Rate each independently, then compare. Judge as a capable, well-informed general user. Use only what is in the task, no outside tools or beyond-general-user knowledge. If the same prompt/response pair shows up again, choose "skip task".

**Steps (2-4 done separately for A and for B):**
1. Read prompt and both responses in full.
2. Rate the 8 attributes, select failure-mode flags, each attribute judged independently.
3. Overall quality 1-5: 5 Excellent (extremely helpful; a warranted refusal with useful context can be 5), 4 Good (mostly helpful, minor issues), 3 Adequate = baseline (partially helpful, notable issue on a critical attribute or several secondary), 2 Fair (slightly helpful, user must work around it), 1 Poor (fails prompt, includes unwarranted refusals). Not an average of attributes, not a tally of flags.
4. Overall rating rationale: call it "the response" (never @Response_A/B). No first person. Evidence-based, specific, complete sentences, no grammar/spelling errors, judge the whole, cite strengths/weaknesses (flags), name the most important factors. No word limit.
5. Preference: A>>B, A>B, A=B, A<B, A<<B. Ties sparingly; if one is even slightly better, pick a direction. Strong (>> / <<) only for substantial gaps: factual error vs correct, unsafe vs safe, major completeness gap, multi-attribute superiority.
6. Preference explanation: MUST refer to "@Response_A" and "@Response_B" (strict, affects validity). No first person. Say what the stronger one did well, what the weaker lacked, which attributes decided it; justify a strong preference as substantial; justify a tie as genuinely similar.

**Attributes (1-5 unless noted):**
- Constraint Following: explicit, pass/fail-checkable requirements only. Constraints: "write a haiku" (5-7-5), "only China vs USA", "~10 options", "under $100", "use an abbreviation of Olatec and a number", "don't mention X". NOT constraints: "respond in JSON if you can" (Intent), "short Indian male names" (Intent), "explain like I'm 5" (Tone), "quick text" (subjective), "crisp email" (Tone/Focus), "power rock ballad" (Tone), "same format as my last email" (Intent), "help me with this text for a survey" (task description). Flags: length/count, format/structure, language, required element absent, forbidden element present, scope exceeded, other. 5 all precise; 4 minor deviation (210 words vs <=200); 3 misses one minor without hurting usability; 2 misses in ways that materially affect usability; 1 misses most/all. N/A only if no explicit constraints.
- Intent Understanding: reads the real goal incl. implicit needs, reasonable reading of ambiguity, right response shape. Flag: did not address an ambiguity. Example: "How should I dress for a job interview?" noting it depends on field = 4; generic advice = 3. 2 = partial misunderstanding, 1 = entirely wrong reading. N/A only for empty/nonsensical prompt.
- Correctness: no 1-5 score. Top flag OK / Flagged / I'm not sure (then skip sub-flags). Sub-flags: false claim; accepts faulty premise; fabricated info (quotes, citations, stats, study names, proper nouns, URLs); unwarranted confidence on uncertain claim; outdated; contradictions; other. Do NOT flag style/opinion, missing content (Coverage), appropriate hedging, or unverifiable claims (use I'm not sure).
- Coverage: list the prompt's parts first, score against that list. Flags: key info missing; misses specific requirement(s); unwarranted refusal; other. Length is not coverage (test: delete the longest paragraph, does any part go unaddressed?). Narrow interpretation = Intent issue; right interpretation but parts left out = Coverage. Unwarranted refusal of a benign request = Coverage 1. N/A only for empty prompt.
- Focus: on topic, right length, no tangents/filler/repetition. Flags: irrelevant info; unnecessary repetition/redundant phrasing; other. In tension with Coverage.
- Clarity: sentence level and structure. Prose flags: inconsistencies, awkward/confusing phrasing. Structural flags: excessive/unnecessary formatting, insufficient formatting, disorganized structure.
- Tone: voice/register vs what the context warrants. Flags: stiff/robotic; preachy/moralizing/condescending; excessive positivity/flattery/hype; mismatched formality/register; mismatched audience expertise; inconsistent voice.
- Follow-up (categorical): if included, Helped / Neutral / Hurt; if not included, Correct omission / Neutral / Gap.

**Appendix:** put yourself in the user's seat; if unsure, use best judgment and note the uncertainty in the explanation. Never judge by length alone; concise and complete beats verbose and unfocused.

**How to apply:** when the user pastes a Rudder task, return per response: 8 attribute ratings with flags, overall 1-5, rationale ("the response"), then preference + explanation ("@Response_A"/"@Response_B"). Write rationales in plain human prose with no em dashes, hedging or buzzwords, per Project Geranium tell rules.

**Reviewer feedback (2026-09-30):** in each per-response rationale, explicitly name the attributes (e.g. "For Coverage, ...", "Correctness is flagged because ...") and tie each example to its attribute. Any attribute scored below 5 must have a matching failure-mode flag selected (e.g. Coverage 4 for skipped items -> "Misses specific requirement(s)").
Reviewer also wants the preference explanation to name attributes throughout, not just a closing "X drove the preference" line; walk each attribute (even or not) with its example.
Also: open each rationale and the preference by naming the core attributes with the biggest impact on helpfulness for that prompt (e.g. "The core attributes here are Correctness and Constraint Following"), then support each with a quoted example from the response.
Reviewer (task 005): every attribute scored below 5 needs a flag, including Coverage and Clarity. Name at least 2 attributes in a rationale when 2+ are flagged, each tied to a response example.
