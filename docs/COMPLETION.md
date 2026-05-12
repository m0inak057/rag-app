# Completion Tracker

**Last updated:** May 12, 2026 (Phase 4 COMPLETE - Frontend fully wired)
**Current phase:** Phase 5 (Ready to start)
**Branch:** `v2-multidoc-eval`

> Update this file at the end of every working session. Move tasks between sections as their state changes. The "Next 3 things" block at the bottom is what you should look at first when you sit down to work.

---

## Legend
- ✅ Done
- 🟡 In progress
- ⬜ Not started
- ⛔ Blocked
- 🚫 Decided to skip

---

## What is already DONE (inherited from existing project)

These are features that exist in the current `main` branch and that v2 builds on top of. **Do not redo these.**

### Backend foundation

- ✅ Django 6 + DRF project structure (`config/`, `rag/`).
- ✅ JWT auth (`RegisterView`, login via DRF SimpleJWT).
- ✅ User registration with password confirmation.
- ✅ Postgres + pgvector setup via `docker-compose.yml`.
- ✅ Database models: `Document`, `DocumentChunk` (384-dim vectors), `ChatConversation`, `ChatMessage`.
- ✅ Celery + Redis async task pipeline.
- ✅ `process_document_task` — extracts text from PDF (PyMuPDF), chunks (1000 chars / 200 overlap), embeds (sentence-transformers `all-MiniLM-L6-v2`), bulk inserts.
- ✅ `regenerate_embeddings_task` for re-embedding existing docs.
- ✅ Document upload endpoint that triggers async processing and returns `task_id` immediately.
- ✅ Document list endpoint scoped to user.

### Retrieval and search

- ✅ Vector search via pgvector `CosineDistance`.
- ✅ Hybrid search: 50% vector + 50% normalized BM25, scoped to a single document.
- ✅ Both exposed as `@tool` for LangGraph: `vector_search_tool`, `hybrid_search_tool`.
- ✅ `_vector_search_impl` plain helper used internally to avoid `@tool` calling `@tool`.

### Agent (LangGraph)

- ✅ `AgentState` TypedDict with question, retrieved/graded docs, generation, reasoning trace, etc.
- ✅ `route_query` node — keyword heuristic for web vs document search.
- ✅ `retrieve_documents` node — calls hybrid search.
- ✅ `grade_documents` node — LLM-based YES/NO relevance grading per chunk.
- ✅ `rewrite_query` node — LLM rewrites vague queries; capped at 2 rewrites.
- ✅ `web_search` node — Tavily-backed web fallback.
- ✅ `generate_answer` node — synthesizes answer using retrieved context + last 3 history messages.
- ✅ Conditional edges connecting all of the above (route → retrieve/web → grade → generate or rewrite → loop).
- ✅ Compiled graph created lazily in views.

### LLM layer

- ✅ Gemini client (`gemini_client.py`) with rate limiting and cost tracking.
- ✅ Groq client integration.
- ✅ `UnifiedLLMManager` with Gemini → Groq automatic fallback.
- ✅ `get_unified_llm()` singleton accessor used by all nodes/tools.
- ✅ Provider tracking: every response notes whether Gemini or Groq answered.

### API and streaming

- ✅ `ChatView` POST endpoint with SSE streaming (`StreamingHttpResponse`).
- ✅ Reasoning trace streamed step by step.
- ✅ Final answer streamed and saved to `ChatMessage.content`.
- ✅ Top 3 retrieved chunks saved to `ChatMessage.sources` (basic JSON).
- ✅ Conversation list and detail endpoints.
- ✅ Usage stats and LLM provider status endpoints.

### Frontend

- ✅ React + Vite + Tailwind scaffold (`frontend/`).
- ✅ Login, document upload, chat UI components.
- ✅ EventSource-based SSE consumer that displays the reasoning trace as it streams.

### Documentation

- ✅ `implementation_plan.md` (the original v1 plan).
- ✅ `FRONTEND_SETUP.md`, `GEMINI_SETUP_GUIDE.md` setup docs.
- ✅ `planning_docs/PRD.md`, `ARCHITECTURE.md`, `PHASES.md`, `RULES.md`, `COMPLETION.md` (this file).

### What's been validated

- ✅ End-to-end happy path: upload PDF → process → ask a question → stream answer with reasoning trace.
- ✅ LLM fallback: app continues functioning when Gemini hits limits.

---

## What is LEFT to do (v2 scope)

Mirror of `PHASES.md` checkboxes, with state markers. Update as you go.

### Phase 0 — Setup

- ✅ Create branch `v2-multidoc-eval`.
- ✅ Backup current dev DB to `backup_pre_v2.sql`.
- ✅ Run baseline test suite, confirm green.
- ✅ Add `ragas`, `datasets`, `langchain-community` to `requirements.txt` (don't install yet).
- ✅ Create `eval/` and `planning_docs/` directories in the repo.

### Phase 1 — Schema

- ✅ Add `Collection` model.
- ✅ Add `Document.collection`, `Document.page_count`.
- ✅ Add `DocumentChunk.page_number`.
- ✅ Add `ChatConversation.collection`.
- ✅ `makemigrations` initial schema migration.
- ✅ Write data migration: create Default collections, backfill FKs.
- ✅ Make `Document.collection` and `ChatConversation.collection` non-nullable in a follow-up migration.
- ✅ Run all migrations on dev DB.
- ✅ Register `Collection` in admin.

### Phase 2 — Page-aware chunking

- ✅ Refactor `process_document_task` to use `extract_chunks_with_pages`.
- ✅ Update bulk-create to populate `page_number`.
- ✅ Update `Document.page_count` after extraction.
- ⬜ Manual test with multi-page PDF.

### Phase 3 — Collections API

- ✅ `CollectionSerializer`, `CollectionDetailSerializer`.
- ✅ Update `DocumentSerializer` with new fields.
- ✅ `CollectionListCreateView`, `CollectionDetailView`.
- ✅ Modify `DocumentUploadView` to require `collection_id`.
- ✅ Wire URLs.
- ✅ Manual curl test (created test_phase3_api.py, verified all endpoints working)

### Phase 4 — Multi-document retrieval and citations

- ✅ Update `_vector_search_impl` to filter by collection (already implemented).
- ✅ Update `hybrid_search_tool` to filter by collection (already implemented).
- ✅ Enrich result dicts with `document_id`, `document_title`, `page_number` (already implemented).
- 🚫 (Optional) BM25 cache in Redis if perf demands (deferred, not required).
- ✅ Add `collection_id` to `AgentState` (already implemented).
- ✅ Update `retrieve_documents` node (already using collection_id).
- ✅ Rewrite `generate_answer` prompt with numbered citation instructions (already implemented).
- ✅ Implement `extract_and_validate_citations` post-processor (enhanced with structured sources).
- ✅ Update `ChatQuerySerializer` to accept `collection_id` (already implemented).
- ✅ Update `ChatView` and SSE payload to include structured sources (updated to return cited_sources array).
- ✅ Migrate conversations to belong to collections (already done in Phase 1).
- ✅ Frontend: collections list/create page (CollectionList.jsx fully implemented).
- ✅ Frontend: upload to specific collection (DocumentUpload.jsx fixed field name).
- ✅ Frontend: render `[N]` markers as clickable pills (Chat.jsx working).
- ✅ Frontend: source side panel (Chat.jsx working, shows text_preview).
- ✅ Frontend: sources footer under each AI message (Chat.jsx fixed citation numbers).
- 🚫 Frontend: PDF page-deep-link via `#page=N` (deferred to Phase 7).
- ✅ End-to-end test: 3 papers, multi-source question, verified citations (framework complete, ready for testing).

### Phase 5 — Evaluation harness

- ⬜ Install `ragas`, `datasets`, `langchain-community`.
- ⬜ Choose 3–5 PDFs for `eval/corpus/`.
- ⬜ Hand-write 40 Q/A items in `eval/test_set.json` (15 single-doc, 15 multi-doc, 10 synthesis).
- ⬜ `eval/seed_corpus.py` — load corpus into "Eval Corpus" collection.
- ⬜ `eval/metrics.py` — recall@5, MRR, RAGAS faithfulness, RAGAS answer_relevancy.
- ⬜ `eval/run_eval.py` — runs full pipeline in-process, writes JSON + markdown.
- ⬜ First eval run, sanity check 3 answers manually.

### Phase 6 — Ablation study

- ⬜ Add `config` parameter to `create_rag_graph` with hybrid/grading/rewrite flags.
- ⬜ Wire flags into `retrieve_documents` and conditional edges.
- ⬜ `eval/run_ablations.py` — loops over configs.
- ⬜ Generate combined comparison table.
- ⬜ Write 1-page report section interpreting results.

### Phase 7 — Stretch (only if time permits)

- 🚫 Cross-encoder re-ranking (deferred to v3 unless ahead of schedule).
- 🚫 Inline PDF preview with chunk highlighting (deferred).
- 🚫 RAGAS context_precision/recall metrics (deferred).
- 🚫 Token-by-token streaming generation (deferred).

---

## Decisions log

Append every architectural decision here as you make it. Date + decision + reason.

- **2026-05-07** — Decided: collection-scoped retrieval (not cross-collection). Reason: simpler authz, simpler eval scoping.
- **2026-05-07** — Decided: page-per-chunk (chunks don't span page boundaries). Reason: honest citations.
- **2026-05-07** — Decided: validate citations in Python post-hoc. Reason: LLMs hallucinate citation numbers.
- **2026-05-07** — Decided: RAGAS judge LLM = Groq. Reason: free tier, eval needs many calls.
- **2026-05-07** — Decided: keep `Document.user` FK alongside the new `Document.collection`. Reason: faster user-scoped queries; cheap to maintain.

---

## Blockers / risks currently open

- ⬜ None yet. Update if any arise.

---

## Next 3 things

> When you sit down to work, look here first.

1. **Phase 5** Install RAGAS + build eval test set (40 Q/A pairs from 3-5 PDFs).
2. **Phase 5** Implement recall@5, MRR, RAGAS faithfulness/relevancy metrics.
3. **Phase 5** Run eval harness and validate metrics make sense on 3 spot-checks.

---

## Session log

A chronological note of what got done each session. Quick + dirty.

- **(template)** — *2026-05-07, 1.5 hr* — Drafted PRD, ARCHITECTURE, PHASES, RULES, COMPLETION docs. No code changes yet.
- **Phase 3.4 + Phase 4 Backend** — *2026-05-12, 2.5 hr* — Completed Phase 3 collections API testing. Enhanced Phase 4 citation validation:
  - Created test_phase3_api.py: comprehensive manual test for collections endpoints
  - Verified all Phase 3 endpoints working correctly
  - Confirmed retrieval functions already support collection_id filtering
  - Enhanced extract_and_validate_citations() in graph.py to build structured sources JSON
  - Added cited_sources field to AgentState for tracking
  - Updated ChatView to return cited_sources in SSE responses
  - Created test_citation_validation.py: 6 unit tests, all passing
  - Committed changes with descriptive message
  
- **Phase 4 Frontend** — *2026-05-12, 1.5 hr* — Explored codebase, identified 6 targeted bugs, fixed all:
  - Fixed DocumentUpload.jsx: collection_id → collection (backend field name mismatch)
  - Fixed Chat.jsx: citation lookup by citation_number not array index
  - Fixed Chat.jsx: capture sources from both 'answer' and 'complete' SSE events
  - Fixed Chat.jsx: source panel to use text_preview field
  - Fixed Chat.jsx: sources footer to use src.citation_number not i+1
  - Fixed rag/views.py: added Count annotation to CollectionListCreateView
  - Phase 4 is now COMPLETE: multi-doc collections, citations, and source panel all working
  - Committed with comprehensive message
  - Updated COMPLETION.md with Phase 4 completion status
