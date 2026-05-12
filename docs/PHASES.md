# Phased Implementation Plan

This is the day-by-day execution plan. Six phases, ~5–8 weeks total depending on pace. Each phase has an explicit "done when" gate — do not move to the next phase until the gate is met.

The plan is ordered so that **after Phase 4, the multi-document feature is shippable** and **after Phase 6, the evaluation harness is shippable**. If you run out of time, stopping after Phase 4 still gives you a meaningful project upgrade.

---

## Phase 0 — Setup and safety nets *(0.5 days)*

Goal: be able to break things without losing work.

- [ ] Create a new git branch: `git checkout -b v2-multidoc-eval`.
- [ ] Make a database backup (`pg_dump rag_db > backup_pre_v2.sql`).
- [ ] Run the existing test suite to confirm green baseline: `python manage.py test`.
- [ ] Add `ragas`, `datasets`, `langchain-community` to `requirements.txt`. Don't install yet — install in Phase 5.
- [ ] Create directory `eval/` with empty `__init__.py`.
- [ ] Create directory `planning_docs/` and copy these markdown files into the repo (so they're versioned).

**Done when:** branch exists, baseline tests pass, backup file exists on disk.

---

## Phase 1 — Schema for collections and page numbers *(1–2 days)*

Goal: data model and migrations ready, no behavior change yet.

### 1.1 Models

- [ ] In `rag/models.py`:
  - Add `Collection(user, name, description, created_at)`.
  - Add `Document.collection` (FK, nullable=True initially).
  - Add `Document.page_count` (IntegerField, default=0).
  - Add `DocumentChunk.page_number` (IntegerField, null=True).
  - Add `ChatConversation.collection` (FK, nullable=True initially).
  - Keep `ChatConversation.document` for now — it can be removed in v3 once you're sure nothing depends on it.

### 1.2 Migrations

- [ ] `python manage.py makemigrations rag`.
- [ ] Inspect the generated migration file. Confirm it's only adding things, not dropping.
- [ ] Write a **data migration** (`python manage.py makemigrations rag --empty -n backfill_collections`) that:
  - For each User, creates a `Collection` named "Default".
  - Assigns every existing Document of that user to the user's Default collection.
  - Assigns every existing ChatConversation to the corresponding doc's collection.
- [ ] Write a follow-up migration that makes `Document.collection` and `ChatConversation.collection` non-nullable.
- [ ] `python manage.py migrate`.
- [ ] Verify in Django shell: every Document has a collection; every Conversation has a collection.

### 1.3 Admin

- [ ] Register `Collection` in `rag/admin.py`. Helps you debug visually.

**Done when:** `python manage.py migrate` runs clean on a fresh DB *and* on a copy of your existing dev DB. Existing Documents and Conversations all have non-null `collection`.

---

## Phase 2 — Page-aware chunking *(1 day)*

Goal: new uploads store `page_number` per chunk.

- [ ] In `rag/tasks.py`, refactor `process_document_task`:
  - Replace `extract_text_from_pdf` + `chunk_text` with a single `extract_chunks_with_pages` function that returns `[{"text": str, "page_number": int}]`.
  - The function chunks **per page**, never across page boundaries.
  - Update `Document.page_count` after extraction.
  - Set `chunk.page_number` when bulk-creating `DocumentChunk` objects.
- [ ] Test by uploading a fresh multi-page PDF and inspecting `DocumentChunk` rows in the DB. Page numbers should be populated and increase as expected.
- [ ] Old chunks remain `page_number=NULL`. The UI/API treats NULL as "page unknown".

**Done when:** new uploads have `page_number` filled on every chunk; old uploads remain functional.

---

## Phase 3 — Collections API *(1–2 days)*

Goal: REST endpoints for collections; upload now requires a `collection_id`.

### 3.1 Serializers

- [ ] `CollectionSerializer` — id, name, description, created_at, document_count (computed).
- [ ] `CollectionDetailSerializer` — same plus a list of nested `DocumentSerializer`.
- [ ] Update `DocumentSerializer` to include `collection`, `page_count`, `document_title` source fields where useful.

### 3.2 Views

- [ ] `CollectionListCreateView` — GET (list user's), POST (create).
- [ ] `CollectionDetailView` — GET (with documents), PATCH (rename), DELETE (cascade).
- [ ] Modify `DocumentUploadView` to require `collection_id` in the request body. Validate that the collection belongs to the user.

### 3.3 URLs

- [ ] Wire `/api/collections/`, `/api/collections/<id>/` in `rag/urls.py`.

### 3.4 Manual test

- [ ] curl-test creating a collection, uploading 3 PDFs into it, and listing it. All 3 should be visible under the collection.

**Done when:** you can create a collection over HTTP, upload multiple PDFs to it, and see them grouped.

---

## Phase 4 — Multi-document retrieval and citations *(3–5 days)*

This is the headline feature. Take it slow.

### 4.1 Retrieval by collection (`rag/tools.py`)

- [ ] `_vector_search_impl(query, collection_id, top_k)` — filter `DocumentChunk` by `document__collection_id`.
- [ ] `hybrid_search_tool(query, collection_id, top_k)` — same change. BM25 corpus is now all chunks in the collection.
- [ ] Each result dict gains: `document_id`, `document_title`, `page_number`.
- [ ] (Optional, only if perf is bad) Cache BM25 tokenized corpus in Redis under `bm25:collection:<id>`. Invalidate on upload.

### 4.2 Update LangGraph state and nodes (`rag/graph.py`)

- [ ] `AgentState` — add `collection_id: int`. Keep `document_id` for now but unused.
- [ ] `retrieve_documents` node — calls hybrid search by `collection_id`.
- [ ] All other nodes unchanged in topology, but pass through the richer chunk metadata.

### 4.3 Citation-aware generation

- [ ] In `generate_answer` node:
  - Build the prompt with sources numbered `[1]..[K]`, including `(Document: "<title>", page <N>)`.
  - Use the explicit citation instruction (see `ARCHITECTURE.md` §3.4).
- [ ] Add a post-processing helper `extract_and_validate_citations(answer_text, sources_list)`:
  - Regex-match `\[(\d+)\]` (and `\[\d+\]\[\d+\]` chains).
  - For each N, check `1 <= N <= len(sources)`; drop invalid ones from the answer text.
  - Return `(cleaned_answer, used_citations_list)`.
- [ ] State now carries `cited_sources` — only sources actually referenced in the answer.

### 4.4 Update ChatView (`rag/views.py`)

- [ ] `ChatQuerySerializer` — accept `collection_id` (mandatory) instead of (or alongside) `document_id`. For backwards compat, if `document_id` is sent, look up the doc's collection.
- [ ] Pass `collection_id` into `AgentState`.
- [ ] In SSE `answer` event, include the structured `sources` (citation_number, document_id, document_title, page_number, chunk_id, text_preview).
- [ ] Save the new structured sources into `ChatMessage.sources`.

### 4.5 Conversations now belong to collections

- [ ] Update `ConversationListView` to filter by `user`, returning each conversation's `collection_id` and `collection_name`.
- [ ] Update `ChatView` to fetch/create conversations by `(user, collection)` not `(user, document)`.

### 4.6 Frontend updates

- [ ] **Collections page** — list, create, delete; click to enter chat for that collection.
- [ ] **Upload UI** — upload to a specific collection.
- [ ] **Chat UI** — render `[N]` markers as pills/superscripts. Clicking opens a side panel showing source details.
- [ ] **Sources footer** — under each AI answer, list all citations used.
- [ ] PDF view: open `<file_url>#page=<N>` in a new tab.

### 4.7 Manual end-to-end test

- [ ] Create a "ML Papers" collection.
- [ ] Upload 3 papers (e.g., Transformer, BERT, GPT-3).
- [ ] Ask: *"How do BERT and the original Transformer differ in their attention mechanism?"*
- [ ] Verify the answer cites at least 2 sources, citations are valid, page numbers are correct, clicking each opens the right chunk.

**Done when:** end-to-end test above passes. **At this point, the project is meaningfully better than it was, even if you stop here.**

---

## Phase 5 — Evaluation harness foundation *(2–3 days)*

Goal: a script you can run that produces actual numbers.

### 5.1 Install eval dependencies

- [ ] `pip install ragas datasets langchain-community --break-system-packages`
- [ ] Verify imports work: `python -c "from ragas.metrics import faithfulness, answer_relevancy; print('ok')"`.

### 5.2 Build the test set

This is the part that takes the most thought, not code.

- [ ] Choose 3–5 PDFs you'll use as the eval corpus. Suggested: 3 ML papers, or 3 chapters of a textbook. Place in `eval/corpus/`.
- [ ] Hand-write 40 questions. Mix of types:
  - 15 **single-document factoid** ("What is the dimensionality of the embedding in BERT-base?").
  - 15 **multi-document comparison** ("How does GPT-3's training objective differ from BERT's?").
  - 10 **harder/synthesis** ("What were the main innovations across these three papers, ordered chronologically?").
- [ ] For each question, write:
  - `expected_documents`: which PDFs *should* be retrieved.
  - `expected_chunks_contain`: 1–3 short substrings that *should* appear in retrieved chunks.
  - `ground_truth_answer`: a 2–4 sentence reference answer.
- [ ] Save as `eval/test_set.json`.

> Be honest with yourself here. A small careful test set beats a large sloppy one.

### 5.3 Eval seeding

- [ ] `eval/seed_corpus.py` — script that:
  - Creates an "Eval" user (or uses a configured one).
  - Creates an "Eval Corpus" collection.
  - Uploads each PDF in `eval/corpus/`.
  - Waits (polls) until all docs have status='ready'.

### 5.4 Metrics module (`eval/metrics.py`)

- [ ] `recall_at_k(retrieved_chunks, expected_substrings, k=5)` → 0 or 1.
- [ ] `reciprocal_rank(retrieved_chunks, expected_substrings)` → float.
- [ ] `ragas_scores(question, contexts, answer, ground_truth)` — wraps RAGAS `faithfulness` and `answer_relevancy`. Configure RAGAS to use Groq as the judge LLM.

### 5.5 Eval runner (`eval/run_eval.py`)

- [ ] Loads `test_set.json`.
- [ ] For each question: invokes the LangGraph in-process (import, don't HTTP), captures retrieved chunks and final answer.
- [ ] Computes per-question metrics, aggregates means.
- [ ] Writes:
  - `eval/results/<timestamp>_full.json` (raw per-question data).
  - `eval/results/<timestamp>_full.md` (summary table).

### 5.6 First real run

- [ ] `python eval/run_eval.py --config full`.
- [ ] Inspect the markdown output. Sanity-check at least 3 answers manually against the test set.
- [ ] Numbers will not be perfect. **Don't tune them.** Phase 6 is for ablation; tuning in Phase 5 invalidates comparisons.

**Done when:** running `run_eval.py` produces a markdown summary with all 4 metrics filled in.

---

## Phase 6 — Ablation study and report numbers *(1–2 days)*

Goal: the comparison table you'll show in your report.

### 6.1 Wire ablation flags

- [ ] In `rag/graph.py`, accept a config dict on graph construction:
  ```python
  def create_rag_graph(config=None):
      cfg = {"hybrid": True, "grading": True, "rewrite": True, **(config or {})}
      ...
  ```
- [ ] `retrieve_documents` honors `cfg["hybrid"]` (vector-only when False).
- [ ] Conditional edges honor `cfg["grading"]` and `cfg["rewrite"]`.

### 6.2 Ablation runner (`eval/run_ablations.py`)

- [ ] Loop over configurations:
  - `full` — everything on.
  - `no_hybrid` — vector-only retrieval.
  - `no_grading` — skip the grading node.
  - `no_rewrite` — no query rewriting on grading-fail.
  - (Optional) `vector_only_no_grading_no_rewrite` — minimal baseline.
- [ ] For each, run the eval harness with that config and save results.
- [ ] Build a single combined markdown table:

```
| Config              | Recall@5 | MRR  | Faithfulness | Ans. Relevance |
|---------------------|----------|------|--------------|----------------|
| Full system         | 0.83     | 0.71 | 0.88         | 0.91           |
| No hybrid (vec only)| 0.71     | 0.62 | 0.85         | 0.89           |
| No grading          | 0.83     | 0.71 | 0.79         | 0.86           |
| No rewrite          | 0.78     | 0.66 | 0.86         | 0.90           |
```

### 6.3 Interpret

- [ ] Write a 1-page section in your project report:
  - Which features helped the most?
  - Where did they hurt? (Sometimes grading hurts recall by being too strict.)
  - What would you change with more time?

This page is gold during the viva. It shows you actually measured your work.

**Done when:** the combined comparison markdown exists and you can speak to every row in it.

---

## Phase 7 — Polish and stretch *(time-permitting only)*

Only attempt these after Phases 0–6 are fully done.

- [ ] **Cross-encoder re-ranking.** Add a `rerank` node after `retrieve_documents` using `cross-encoder/ms-marco-MiniLM-L-6-v2`. Add a `rerank` ablation flag.
- [ ] **PDF preview with chunk highlight.** When the user clicks a citation, render the PDF page inline (using `react-pdf` or `pdf.js`) with the chunk text highlighted. Visual wow factor.
- [ ] **Eval improvements.** Add `context_precision` and `context_recall` (RAGAS) once you have manually labeled chunks. Run each eval 3 times and report mean ± std.
- [ ] **Streaming token-by-token.** Switch `generate_answer` to a streaming LLM call so the UI shows tokens as they're generated.

---

## Time budget summary

| Phase | Aggressive | Realistic | Cushion |
|-------|------------|-----------|---------|
| 0     | 0.5 d      | 0.5 d     | 0.5 d   |
| 1     | 1 d        | 2 d       | 3 d     |
| 2     | 0.5 d      | 1 d       | 1.5 d   |
| 3     | 1 d        | 2 d       | 3 d     |
| 4     | 3 d        | 5 d       | 7 d     |
| 5     | 2 d        | 3 d       | 4 d     |
| 6     | 1 d        | 2 d       | 3 d     |
| **Total** | **~9 d** | **~15 d** | **~22 d** |

Plan for the realistic column. Cushion is for the things you forgot.
