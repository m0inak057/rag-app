# Engineering Rules

These are the rules of engagement for the v2 work. They exist to prevent the common student-project failure modes: scope creep, broken main branch, untested code, and "I'll measure it later" syndrome.

---

## Workflow rules

**R1. One branch, one purpose.**
All v2 work happens on `v2-multidoc-eval`. No drive-by refactors of unrelated code. If you find a bug in something else, file a TODO note and move on.

**R2. Commit at every checkbox.**
Every checkbox in `PHASES.md` should map to roughly one commit. Commit messages follow `phase-N: <what changed>`, e.g. `phase-2: page-aware chunking in process_document_task`. This creates a natural rollback path.

**R3. Don't break the dev server.**
After every commit, run `python manage.py runserver` and `python manage.py test` and confirm both still work. If they don't, fix it before the next commit.

**R4. Migrations are forward-only and reversible.**
Never edit a migration after it's been run. If a migration needs fixing, write a new one. Always test migrations on a copy of your real DB before running on it.

**R5. The main branch keeps working.**
Do not merge `v2-multidoc-eval` into main until Phase 4 is complete and end-to-end tested. Until then, main is your safety net.

---

## Code rules

**R6. Don't change the embedding model.**
The DB has 384-dim vectors. Changing the model means re-embedding everything. Out of scope for v2.

**R7. Don't refactor `unified_llm.py` or `gemini_client.py`.**
These work. Touching them risks breaking the fallback logic that keeps the app online when Gemini limits hit. The eval harness imports from them, doesn't modify them.

**R8. Use the existing tools, don't write new ones, unless explicitly required.**
The graph already has 5 tools. Phase 4 changes their inputs (collection_id), not their identity. Resist the urge to add a 6th tool.

**R9. Citation validation runs in code, not in the prompt.**
Do not trust the LLM to "only cite valid sources". Validate `[N]` markers in Python, drop invalid ones. This is non-negotiable.

**R10. Backwards compat for the API where cheap.**
If a request comes in with `document_id` instead of `collection_id`, look up the doc's collection and proceed. Don't 400. The frontend will be migrated, but old API consumers (e.g., your own test scripts) shouldn't break.

**R11. No new direct LLM calls outside `unified_llm.py`.**
If you need an LLM call (in eval or anywhere else), go through the unified manager. The one exception: RAGAS internally configures its own judge LLM — that's fine, it's a library boundary.

**R12. Async work goes in Celery, not in views.**
If you find yourself adding a slow operation in a view, stop and put it in `tasks.py`. The whole point of the existing architecture is that views stay snappy.

---

## Data rules

**R13. Never delete data without a migration.**
If you decide to drop `ChatConversation.document` (the FK), it goes through a migration. Never edit the DB directly.

**R14. Page numbers are 1-indexed in the UI, 1-indexed in the DB.**
PyMuPDF uses 0-indexed `page.number`. Add 1 when storing. Avoid the off-by-one debate.

**R15. Old chunks have NULL page_number; UI must handle this.**
Show "page unknown" or omit the page number rather than crashing or showing "page None".

**R16. Test set is read-only after Phase 5.3.**
Once you start running ablations, freeze `test_set.json`. Editing it mid-experiment invalidates all prior results. If you must change it (e.g., a question is broken), re-run *all* configurations on the new set.

---

## Evaluation rules

**R17. The eval set is small. Don't over-claim.**
40 questions is enough to show direction, not enough to make strong scientific claims. In your report, say "trends suggest" not "we prove".

**R18. Run eval on Groq, not Gemini.**
Eval runs hit the LLM many times. Use the free tier. Set the env var or config flag to force Groq for eval.

**R19. Don't tune to the test set.**
Once you've seen the test set numbers, resist the urge to change prompts to make them go up. That's overfitting. If you must change something architectural, document the change and re-run all ablations.

**R20. Report numbers to 2 decimal places.**
`0.83` not `0.8294821`. Spurious precision looks unserious.

**R21. Report negative results too.**
If grading hurts faithfulness, say so. A surprising negative result is more interesting in a viva than a clean positive one. Examiners can smell when numbers have been cherry-picked.

---

## Frontend rules

**R22. Citation rendering is a pure function of the AI message payload.**
Given the message text and the `sources` array, the rendering should be deterministic. No fetching extra data at render time.

**R23. Source side panel is a controlled component.**
Open/close state lives in React state. URL doesn't change when opening the panel. Keep it simple.

**R24. PDF opens in a new tab via `<file_url>#page=<N>`.**
Don't ship a custom PDF viewer in v2. Browser-native is enough.

---

## Documentation rules

**R25. Update `COMPLETION.md` at the end of every working session.**
Mark what got done, what's next, what's blocked. Future-you will thank present-you.

**R26. The PRD is the source of truth.**
If you discover the PRD is wrong, update the PRD before changing code. Don't let the code and the PRD drift apart.

**R27. Every architectural decision goes into `ARCHITECTURE.md`.**
If you decide something not covered there (e.g., "BM25 cache TTL is 1 hour"), add a line to ARCHITECTURE under "Design decisions". Future you and your evaluator both benefit.

---

## Anti-patterns to avoid

- **"Let me also add X while I'm here."** No. Finish the current phase.
- **"I'll write tests later."** Maybe. But manual end-to-end test at the end of every phase is non-negotiable.
- **"The numbers don't look good, let me tweak the prompt."** Tweak before running eval, not after seeing results.
- **"I'll just edit the migration."** Never. Write a new one.
- **"I'll skip the data migration; the dev DB is empty anyway."** Until it isn't, and you've lost a week of test conversations.
- **"Let me try this new vector DB I just heard about."** Out of scope. pgvector stays.
- **"I'll add a tiny re-ranker, just 5 minutes."** It's never 5 minutes. It goes in Phase 7.
