# Enhancement Plan - v2 Multi-Document Evaluation Implementation

**Date:** May 7, 2026  
**Status:** Ready to Execute  
**Target Timeline:** 5-8 weeks

---

## Executive Summary

This plan outlines the implementation of v2 enhancements to the RAG application. The project will evolve from single-document retrieval to a **multi-document collection-based system** with an **evaluation harness** for measuring quality.

**Key Milestone:** After Phase 4, the feature is shippable. After Phase 6, the evaluation system is shippable.

---

## What's Already Working (Do NOT Redo)

The existing application has:
- ✅ Django 6 + DRF backend with JWT auth
- ✅ PDF extraction, chunking (1000 chars), embedding (384-dim via sentence-transformers)
- ✅ Postgres + pgvector for vector storage
- ✅ LangGraph RAG agent with hybrid search (vector + BM25)
- ✅ Gemini → Groq LLM fallback
- ✅ React + Vite frontend with SSE streaming
- ✅ Celery + Redis async processing
- ✅ End-to-end validated happy path

**Your job:** Build on this foundation without breaking it.

---

## The v2 Enhancement Plan

### **Phase 0: Setup & Safety Nets (0.5 days)**

**What we're doing:** Prepare the repository for major changes without risk of data loss.

**Specific tasks:**
1. Create git branch `v2-multidoc-eval`
2. Backup the dev database (`pg_dump`)
3. Run baseline test suite (confirm green)
4. Add new dependencies to `requirements.txt`: `ragas`, `datasets`, `langchain-community` (don't install yet)
5. Create `eval/` and `planning_docs/` directories
6. Copy this documentation suite into the repo for version control

**Success criteria:** Branch exists, backup file on disk, baseline tests pass.

---

### **Phase 1: Database Schema for Collections (1-2 days)**

**What we're doing:** Introduce the concept of "Collections" — groupings of documents per user — and track page numbers.

**Specific tasks:**

**1.1 Model changes** — Edit `rag/models.py`:
- Add `Collection` model: `user`, `name`, `description`, `created_at`
- Add `Document.collection` (FK to Collection, nullable initially)
- Add `Document.page_count` (to track total pages)
- Add `DocumentChunk.page_number` (for citation accuracy)
- Add `ChatConversation.collection` (FK to Collection, nullable initially)
- Keep `Document.user` and `ChatConversation.document` for backward compatibility

**1.2 Migrations** — Run and test:
- `python manage.py makemigrations` (creates initial schema)
- Write a **data migration** to:
  - Create "Default" collection for each existing user
  - Backfill all existing Documents into their user's Default collection
  - Backfill all existing Conversations into the corresponding collection
- Write follow-up migration to make `.collection` fields non-nullable
- `python manage.py migrate` (apply all)

**1.3 Admin** — Register `Collection` in Django admin for manual testing/debugging.

**Success criteria:** Migrations run clean on both fresh and existing DBs. Every Document and Conversation has a non-null collection.

---

### **Phase 2: Page-Aware Chunking (1 day)**

**What we're doing:** When PDFs are uploaded, chunks now record which page they came from (no chunks span page boundaries).

**Specific tasks:**
- Refactor `rag/tasks.py`, replace `extract_text_from_pdf` + `chunk_text` with `extract_chunks_with_pages` 
- Chunks break at page boundaries (never span pages)
- Set `Document.page_count` after extraction
- Populate `DocumentChunk.page_number` on bulk insert
- Test with a multi-page PDF upload; verify page numbers are stored correctly

**Success criteria:** New uploads have page numbers on every chunk. Old uploads remain functional with `page_number=NULL`.

---

### **Phase 3: Collections REST API (1-2 days)**

**What we're doing:** Expose collections and documents as REST endpoints. Uploads now require a target collection.

**Specific tasks:**

**3.1 Serializers** — New serializers in `rag/serializers.py`:
- `CollectionSerializer` (id, name, description, created_at, document_count)
- `CollectionDetailSerializer` (same + nested document list)
- Update `DocumentSerializer` with `collection`, `page_count` fields

**3.2 Views** — New views in `rag/views.py`:
- `CollectionListCreateView` — GET (list user's collections), POST (create new)
- `CollectionDetailView` — GET (with documents), PATCH (update name), DELETE (cascade)
- Modify `DocumentUploadView` to require `collection_id` in request body
- Validate collection belongs to requesting user

**3.3 URLs** — Add routes in `rag/urls.py`:
```
POST   /api/collections/          → create collection
GET    /api/collections/          → list user's collections
GET    /api/collections/<id>/     → get collection + its docs
PATCH  /api/collections/<id>/     → rename collection
DELETE /api/collections/<id>/     → delete collection
```

**3.4 Manual testing** — Use curl to:
- Create a collection
- Upload 3 PDFs to it
- Verify they appear grouped under the collection

**Success criteria:** Collections API works end-to-end via HTTP. Documents are properly scoped to collections.

---

### **Phase 4: Multi-Document Retrieval & Citations (2-3 days)**

**What we're doing:** The retrieval and generation system now works across multiple documents within a collection and produces citations.

**Specific tasks:**

**4.1 Retrieval** — Update `rag/services.py` and `rag/tools.py`:
- Modify `_vector_search_impl` and `hybrid_search_tool` to filter by `collection_id`
- Enrich search results with `document_id`, `document_title`, `page_number`

**4.2 Agent** — Update `rag/graph.py`:
- Add `collection_id` to `AgentState`
- Update `retrieve_documents` node to pass collection_id to search
- Rewrite `generate_answer` prompt with numbered citation instructions: `[1]`, `[2]`, etc.
- Implement post-processor `extract_and_validate_citations` to verify citations match retrieved chunks

**4.3 API** — Update `rag/views.py`:
- Modify `ChatQuerySerializer` to accept `collection_id`
- Update `ChatView` to pass collection_id through the pipeline
- Return sources in SSE payload with structured metadata (document, page, text snippet)

**4.4 Data migration** — Migrate existing conversations to belong to collections.

**4.5 Frontend** — React components in `frontend/src/`:
- Collections list page with create/delete UI
- Upload dialog: select target collection
- Chat UI: render `[1]`, `[2]` citation markers as clickable pills
- Side panel showing clicked source (document title, page number, snippet)
- Footer under AI message showing "Sources: Document A (page 3), Document B (page 1)"
- PDF viewer with `#page=N` deep-link support

**4.6 Integration test** — End-to-end:
- Upload 3 research papers to a collection
- Ask a multi-document question (e.g., "Compare approach A vs B")
- Verify the AI answer includes `[1]`, `[2]`, `[3]` citations
- Verify clicking each citation shows the correct source

**Success criteria:** Multi-document retrieval works. Citations are present and validated. Frontend renders sources nicely.

---

### **Phase 5: Evaluation Harness Setup (1-2 days)**

**What we're doing:** Build the infrastructure to measure RAG quality using standard metrics.

**Specific tasks:**

**5.1 Environment** — Install evaluation libraries:
```bash
pip install ragas datasets langchain-community
```

**5.2 Evaluation corpus** — Create `eval/` directory structure:
```
eval/
  __init__.py
  corpus/                    ← 3-5 sample PDFs
  seed_corpus.py            ← Script to load corpus
  test_set.json             ← Hand-written 40 Q/A pairs
  metrics.py                ← Compute recall@5, MRR, RAGAS scores
  run_eval.py               ← Main eval script
```

**5.3 Test set** — Hand-write 40 question-answer pairs in `eval/test_set.json`:
- 15 single-document questions (answer from 1 paper)
- 15 multi-document questions (answer requires synthesis from 2+ papers)
- 10 synthesis questions (requires reasoning across papers)

Format:
```json
[
  {"question": "...", "reference_answer": "...", "documents": ["paper1.pdf", "paper2.pdf"]},
  ...
]
```

**5.4 Seed script** — `eval/seed_corpus.py`:
- Load corpus PDFs into a new "Eval Corpus" collection
- Print collection ID for use in eval script

**5.5 Metrics** — `eval/metrics.py`:
- Recall@5: % of relevant chunks retrieved in top 5
- MRR: Mean Reciprocal Rank of first relevant chunk
- RAGAS faithfulness: Does the answer hallucinate or contradict sources?
- RAGAS answer_relevancy: Does the answer address the question?
- Judge LLM: use Groq (free tier, many calls needed)

**5.6 Main eval script** — `eval/run_eval.py`:
- For each test question:
  - Call agent directly (no HTTP, in-process)
  - Retrieve chunks, check recall@5 and MRR
  - Generate answer, compute RAGAS scores
  - Log results
- Write summary to `results/<timestamp>.json` and `results/<timestamp>.md`

**5.7 Sanity check** — Run evaluation on ~3 test questions; manually inspect answers to ensure they make sense.

**Success criteria:** Eval harness runs without errors. 3 sample answers are reasonable and scores seem sensible.

---

### **Phase 6: Ablation Study (1-2 days)**

**What we're doing:** Measure the impact of each RAG component (hybrid search vs vector-only, grading, query rewriting, etc.).

**Specific tasks:**

**6.1 Graph configurability** — Update `rag/graph.py`:
- Add `config` parameter to `create_rag_graph()`:
  ```python
  config = {
    'use_hybrid_search': True,    # vs vector-only
    'use_grading': True,          # vs no grading
    'use_rewrite': True,          # vs no rewriting
    'max_rewrites': 2,
  }
  ```
- Wire flags into `retrieve_documents` and conditional edges

**6.2 Ablation runner** — `eval/run_ablations.py`:
- Loop over config combinations (2³ = 8 variants)
- For each config, run full evaluation on test set
- Collect metrics (recall@5, MRR, faithfulness, answer_relevancy)
- Generate comparison table showing impact of each flag

**6.3 Report** — Write 1-page interpretation:
- Which flags have the biggest impact?
- Any surprising findings?
- Recommend production config

**Success criteria:** Ablation table is complete and readable. Findings make sense (e.g., grading should improve faithfulness).

---

### **Phase 7: Stretch Goals (If Time Permits)**

These are optional; consider skipping if timeline is tight.

- [ ] Cross-encoder re-ranking (use a smaller model to re-rank top-K chunks)
- [ ] Inline PDF preview with chunk highlighting
- [ ] RAGAS `context_precision` and `context_recall` metrics
- [ ] Token-by-token streaming generation in frontend

---

## Implementation Order

Follow **exactly this order** — each phase depends on the previous one:

```
Phase 0 (0.5 days)
  ↓
Phase 1 (1-2 days)
  ↓
Phase 2 (1 day)
  ↓
Phase 3 (1-2 days)
  ↓
Phase 4 (2-3 days)  ← Feature is shippable after this
  ↓
Phase 5 (1-2 days)
  ↓
Phase 6 (1-2 days)  ← Evaluation is complete after this
  ↓
Phase 7 (optional, stretch)
```

---

## Key Decisions Already Made

1. **Collection-scoped retrieval** — Not cross-collection. Simpler authorization and evaluation scoping.
2. **Page-per-chunk** — Chunks never span page boundaries. Honest citations.
3. **Post-hoc citation validation** — Validate citations in Python after LLM generation. LLMs hallucinate citation numbers.
4. **Groq for evaluation** — Use Groq's free tier as the judge LLM (many calls needed, Gemini costs more).
5. **Keep `Document.user`** — Alongside the new `Document.collection`. Faster user-scoped queries.

---

## Success Criteria Checklist

- [ ] Phase 0: Branch exists, backup on disk, baseline tests pass
- [ ] Phase 1: Migrations run clean, collections are created, no data loss
- [ ] Phase 2: New uploads have page numbers, old uploads still work
- [ ] Phase 3: Collections API works over HTTP, documents group properly
- [ ] Phase 4: Multi-doc retrieval works, citations are rendered and validated
- [ ] Phase 5: Eval harness runs, 3 spot-checked answers are reasonable
- [ ] Phase 6: Ablation table generated, findings interpreted
- [ ] Phase 7: Stretch goals (optional)

---

## Next Immediate Actions

1. **Start Phase 0.1** — Create the `v2-multidoc-eval` branch
   ```bash
   git checkout -b v2-multidoc-eval
   git push origin v2-multidoc-eval
   ```

2. **Start Phase 0.2** — Backup dev DB
   ```bash
   pg_dump -U postgres rag_db > backup_pre_v2.sql
   ```

3. **Start Phase 0.3** — Run baseline tests
   ```bash
   python manage.py test
   ```

4. **Start Phase 0.4** — Update `requirements.txt` with new dependencies and commit

5. **Move to Phase 1** — Begin schema changes

---

## Notes for Execution

- **Commit often** — After each logical step, commit with a descriptive message.
- **Test incrementally** — Don't wait until the end to test; test each phase before moving on.
- **Manual testing** — Use curl, Django shell, and frontend UI to verify behavior.
- **Update COMPLETION.md** — At the end of each session, update the status tracker.
- **Keep documentation in sync** — As you make decisions, update the decisions log.

---

## Risk Mitigation

- **Risk:** Database migrations break existing data.  
  **Mitigation:** Run migrations on a backup copy first. Validate with data migrations that populate defaults.

- **Risk:** Frontend breaks during API changes.  
  **Mitigation:** Update API and frontend in Phase 4 together. Keep version compatibility in mind.

- **Risk:** Evaluation metrics don't make sense.  
  **Mitigation:** Spot-check 3 answers manually in Phase 5 before rolling out full eval.

---

## Questions to Keep in Mind

- After Phase 4, are existing users' conversations still accessible? (Yes, via backfill migrations.)
- Do old PDFs (uploaded before Phase 2) work with the new system? (Yes, page_number is NULL but retrieval still works.)
- Can the evaluation harness run offline without the Django server? (Yes, by design.)
- What if Phase 5 metrics are terrible? (Acceptable — Phase 4 still ships. Use Phase 6 to debug via ablation.)

---

**Status:** Ready to begin. See COMPLETION.md for session-by-session progress tracking.
