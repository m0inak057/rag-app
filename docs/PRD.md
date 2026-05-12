# Product Requirements Document (PRD)

**Project:** Agentic Document Intelligence System — v2 Upgrade
**Document version:** 1.0
**Status:** Draft, ready to execute
**Owner:** Final-year B.Tech project

---

## 1. Background

The current system (`rag-app`) is a single-document agentic RAG application built on Django + LangGraph + pgvector. A user uploads a PDF, asks questions, and a LangGraph state machine orchestrates retrieval (hybrid: vector + BM25), self-grading of retrieved chunks, query rewriting on failure, optional web fallback (Tavily), and answer generation (Gemini → Groq fallback). Reasoning steps stream to a React frontend over SSE.

It works. But it has two gaps that hold it back from being a strong final-year project:

1. **It can only reason within a single document at a time.** Users cannot upload a corpus and ask questions that span multiple sources. There are also no inline citations — answers are not verifiable.
2. **There is no measurement.** Architectural choices (hybrid search, grading loop, rewriting) are claimed to help but never tested. There are no numbers to show in a report or viva.

This PRD covers the v2 upgrade to close both gaps.

---

## 2. Goals

### 2.1 Primary goals

- **G1.** Enable users to upload a **corpus** (multiple documents) and ask questions that retrieve and reason across **all of them**.
- **G2.** Every AI answer must include **inline citations** of the form `[1]`, `[2]`, etc., where each citation links back to the exact source chunk (document + page + chunk text).
- **G3.** Build an **evaluation harness** that measures retrieval and answer quality on a fixed test set, so architectural choices can be validated with numbers.
- **G4.** Produce a **comparison table** in the final report showing measured deltas for: vector-only vs hybrid, with-grading vs without, with-rewrite vs without, with-rerank vs without (rerank only if time permits).

### 2.2 Non-goals (v2)

- Re-ranking with a cross-encoder. *(Optional stretch, not committed.)*
- Fine-tuning embeddings.
- Multi-user collaboration on a shared corpus.
- Real-time co-editing or annotation.
- Mobile app.
- Voice input.
- Switching the embedding model.

---

## 3. Target user and primary use case

A student or researcher uploads 5–15 PDFs (e.g., research papers on a topic, or chapters of a textbook, or company policy docs) into a **collection**. They then chat with the collection: ask questions, get answers grounded in the corpus, click any citation in the answer to jump to the source chunk in the source document.

---

## 4. User stories

| ID | As a... | I want to... | So that... |
|----|---------|--------------|------------|
| US-1 | user | create a named collection of documents | I can group related PDFs (e.g., "ML papers", "Constitution chapters") |
| US-2 | user | upload multiple PDFs into a collection | I can chat with all of them at once |
| US-3 | user | ask a question scoped to a collection | the agent searches across every doc in it |
| US-4 | user | see citations like `[1]`, `[2]` in the AI answer | I can verify which source each claim came from |
| US-5 | user | click a citation | I jump to the source chunk (with document title + page number visible) |
| US-6 | developer | run an evaluation script against a fixed test set | I can measure retrieval recall, faithfulness, answer relevance |
| US-7 | developer | toggle architectural features (hybrid, grading, rewrite) via flags | I can run ablation studies and compare results |
| US-8 | developer | get a results table (markdown or CSV) from the eval script | I can paste it directly into the project report |

---

## 5. Functional requirements

### FR-1: Collection model

- A `Collection` belongs to a `User`, has a name and description.
- A `Document` belongs to **one** `Collection` (foreign key) instead of (or in addition to) belonging directly to a user.
- Listing endpoints exist for collections.
- A user can rename or delete a collection (deleting cascades to documents and chunks).

### FR-2: Multi-document upload

- Upload endpoint accepts a `collection_id`.
- Multiple documents per collection are supported. Each is processed by Celery independently.
- Collection-level status reflects aggregate state ("3 of 5 ready").

### FR-3: Multi-document retrieval

- Hybrid search must accept a `collection_id` instead of (or in addition to) `document_id`.
- Search returns chunks across **all** ready documents in the collection.
- Each chunk result must carry: chunk text, document_id, document title, and page number.

### FR-4: Page number tracking

- When extracting text from a PDF, store **page number per chunk**.
- `DocumentChunk` model gains a `page_number` field (integer).
- Chunking is page-aware: each chunk records the page it primarily came from. (Simplest approach: chunk per page, then split long pages.)

### FR-5: Citations in the answer

- The `generate_answer` node must:
  - Receive numbered context blocks: `[1] (DocTitle, p.7): <text>`, `[2] (DocTitle, p.12): <text>`, etc.
  - Be prompted to cite using `[N]` markers inline in the answer wherever a claim is supported.
- The streaming response must emit a structured `sources` event containing the array of `{citation_number, document_id, document_title, page_number, chunk_id, text_preview}`.

### FR-6: Citation rendering in frontend

- The chat UI renders `[N]` markers as clickable elements.
- Clicking a marker opens a side panel (or modal) showing: document title, page number, the chunk text, and a "View source PDF" link.
- A "Sources" section below each answer lists all citations used.

### FR-7: Evaluation harness

- A script `eval/run_eval.py` runs against a fixed test set (`eval/test_set.json`).
- Test set format: list of `{question, document_collection, ground_truth_answer, ground_truth_chunks}` items, 30–50 items minimum.
- The script can run the full agent pipeline OR call a configurable retriever-only path.
- Metrics computed:
  - **Retrieval recall@5** — did at least one of the top-5 retrieved chunks match a ground-truth chunk?
  - **Retrieval MRR** — mean reciprocal rank of the first relevant chunk.
  - **Answer faithfulness** (RAGAS) — does the answer make claims grounded in the retrieved context?
  - **Answer relevance** (RAGAS) — does the answer actually address the question?
- Results are written to `eval/results/<timestamp>.json` and `eval/results/<timestamp>.md` (markdown table).

### FR-8: Ablation switches

- The graph must accept a config object (or env-controlled flags) that can disable:
  - Hybrid search (force vector-only).
  - Document grading node.
  - Query rewrite node.
- This makes ablation runs (eval with each feature off) trivial.

### FR-9: Comparison report

- A driver script `eval/run_ablations.py` runs the eval harness under each flag combination and produces a single markdown table with all configs side-by-side.

---

## 6. Non-functional requirements

- **Latency.** Multi-document retrieval should remain under ~3 s for collections up to 15 docs / ~5,000 chunks. Hybrid search BM25 may need to be cached per collection.
- **Backwards compatibility.** Existing single-doc conversations should keep working (or be migrated; see §9).
- **Cost.** Eval runs use Groq (free) by default to avoid burning Gemini budget on test loops.
- **Reproducibility.** Eval runs are deterministic given the same code, models, and test set (set temperature=0 where possible, fix random seeds in chunking).

---

## 7. Success criteria

The v2 is "done" when **all** of these are true:

1. A user can create a collection, upload 5+ PDFs, and ask a question that pulls passages from at least 2 different documents in a single answer.
2. The answer contains numbered citations like `[1]`, `[2]`, and clicking each in the UI shows the correct source chunk + page number.
3. `python eval/run_eval.py` produces a results markdown file with the four metrics filled in.
4. `python eval/run_ablations.py` produces a comparison table showing measured numbers across at least three configurations (full system, no-hybrid, no-grading).
5. The project report contains the comparison table and at least one paragraph interpreting the deltas.

---

## 8. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BM25 across many docs is slow | Medium | Medium | Cache BM25 index per collection in Redis; rebuild on doc upload. |
| Citation hallucination (LLM makes up `[7]`) | High | Medium | Post-process the answer to validate every `[N]` exists; strip invalid ones. |
| Test set is too small to be statistically meaningful | High | Low | Acknowledge limitation in report; aim for 40+ Qs; re-run 3x and report mean. |
| RAGAS requires its own LLM calls = $$ | Medium | Medium | Use Groq for RAGAS judge LLM; cache judgments. |
| Page-number tracking breaks existing chunks | High | Low | Migrate gracefully — old chunks get `page_number=NULL`; treat as "page unknown" in UI. |
| Schema migration loses existing data | Medium | High | Write data migration that creates a default collection per user and links existing documents to it. |

---

## 9. Migration plan

Existing data must not break. On running the v2 migrations:

1. Create a `Collection` named "Default" for each existing user.
2. Reassign every existing `Document` to that user's Default collection.
3. `DocumentChunk.page_number` defaults to `NULL` for old chunks (re-process is optional, not required).
4. Existing single-doc chat endpoints stay working (deprecated but functional) until v3.

---

## 10. Out of scope (explicit)

- Cross-encoder re-ranking (may be added as a stretch goal but is not committed).
- Streaming token-by-token generation (current step-by-step streaming is sufficient).
- Editing or deleting individual chunks via UI.
- Version history of documents.
- OCR for scanned PDFs.

---

## 11. Open questions

1. Should collection deletion be soft-delete (recoverable) or hard-delete? **Decision pending — default to hard-delete for v2.**
2. Should we cap the number of documents per collection? **Soft cap of 25 for v2.**
3. Should we support cross-collection queries? **No — v2 is one collection at a time.**
