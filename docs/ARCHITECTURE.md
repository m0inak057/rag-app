# Architecture — v2

This document describes the target architecture *after* the v2 upgrade. It contrasts what exists today with what changes, so you always know what to touch and what to leave alone.

---

## 1. System overview

```
┌────────────────────────────────────────────────────────────────┐
│                         React Frontend                          │
│   - Collections page  - Chat UI with [N] citations              │
│   - Source side panel (page-aware)                              │
└──────────────────────────────┬─────────────────────────────────┘
                               │ REST + SSE
                               ▼
┌────────────────────────────────────────────────────────────────┐
│                      Django + DRF API                           │
│   - Auth (JWT)                                                  │
│   - Collections CRUD          - Documents (upload/list)         │
│   - Chat (streaming SSE)      - Eval triggers (optional)        │
└──────────┬──────────────────────────────────┬──────────────────┘
           │                                  │
           ▼                                  ▼
┌──────────────────────┐         ┌────────────────────────────────┐
│  Celery + Redis      │         │       LangGraph Agent          │
│  - Async PDF ETL     │         │   ┌──────────────────────┐     │
│  - Per-page chunking │         │   │  route_query         │     │
│  - Embedding         │         │   │  retrieve (hybrid)   │     │
│  - Page-aware chunks │         │   │  grade_documents     │     │
└──────────┬───────────┘         │   │  rewrite_query       │     │
           │                      │   │  web_search          │     │
           ▼                      │   │  generate_answer     │     │
┌────────────────────────────────┐│   │   (with citations)   │     │
│  Postgres + pgvector           ││   └──────────────────────┘     │
│  - users, collections, docs    │└────────────┬───────────────────┘
│  - document_chunks (+ page)    │             │
│  - conversations, messages     │             ▼
└────────────────────────────────┘ ┌────────────────────────────────┐
                                   │   LLM Layer (unified)          │
                                   │   Gemini → Groq fallback       │
                                   └────────────────────────────────┘

Offline (developer-side, runs from CLI):
┌────────────────────────────────────────────────────────────────┐
│  Evaluation Harness                                             │
│  eval/run_eval.py    eval/run_ablations.py                      │
│  - Loads test set    - Toggles graph flags                      │
│  - Calls retrieval / agent directly (no HTTP)                   │
│  - Computes recall@5, MRR, faithfulness, answer relevance       │
│  - Writes results/<timestamp>.{json,md}                         │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. Data model changes

### What exists today

```
User
 └─ Document (title, file, status, chunks_count, error_message)
     └─ DocumentChunk (text, embedding[384])
 └─ ChatConversation (user, document)
     └─ ChatMessage (role, content, reasoning_trace, sources)
```

### What v2 looks like

```
User
 └─ Collection                       ← NEW
     ├─ name, description, created_at
     └─ Document
         ├─ collection (FK)          ← NEW (replaces user FK as primary owner)
         ├─ user (FK, kept for queries)
         ├─ title, file, status, chunks_count, error_message, page_count   ← page_count NEW
         └─ DocumentChunk
             ├─ text, embedding[384]
             └─ page_number          ← NEW

 └─ ChatConversation
     ├─ collection (FK)              ← NEW (replaces document FK)
     └─ ChatMessage
         ├─ role, content, reasoning_trace
         └─ sources (JSON, structured: see below)   ← richer schema
```

**`ChatMessage.sources` JSON shape (v2):**

```json
[
  {
    "citation_number": 1,
    "chunk_id": 487,
    "document_id": 12,
    "document_title": "Attention Is All You Need",
    "page_number": 3,
    "text_preview": "The Transformer follows this overall architecture using stacked self-attention..."
  },
  { "citation_number": 2, "...": "..." }
]
```

### Migration notes

- Add `Collection` table.
- Add `collection_id` (nullable initially) to `Document` and `ChatConversation`.
- Data migration: for each existing user, create a "Default" collection and assign all of their documents and conversations to it.
- After data migration: make `collection_id` non-nullable on `Document` and `ChatConversation`.
- Add `page_number` (nullable) to `DocumentChunk`. Existing rows stay `NULL`; treated as "page unknown".

---

## 3. Component-by-component

### 3.1 PDF ingestion (`rag/tasks.py`)

**Today:** opens the PDF, concatenates all page text into one string, chunks the string by character count.

**v2:** opens the PDF, iterates **page by page**. For each page:
- Extract page text.
- Chunk that text (1000 char windows, 200 char overlap).
- Each chunk stores `page_number = page.number + 1`.

This means a chunk never spans pages, which makes citations honest.

```python
def extract_chunks_with_pages(file_path):
    doc = fitz.open(file_path)
    page_chunks = []
    for page in doc:
        text = page.get_text()
        if not text.strip():
            continue
        for chunk in chunk_text(text, 1000, 200):
            page_chunks.append({"text": chunk, "page_number": page.number + 1})
    doc.close()
    return page_chunks
```

### 3.2 Retrieval (`rag/tools.py`)

**Today:** `hybrid_search_tool(query, document_id, top_k)` filters chunks by a single document.

**v2:** `hybrid_search_tool(query, collection_id, top_k)` filters chunks by all documents in the collection. Document_id is no longer the scoping key; collection_id is.

Each result now carries:

```python
{
    'id': chunk.id,
    'text': chunk.text,
    'document_id': chunk.document_id,
    'document_title': chunk.document.title,
    'page_number': chunk.page_number,
    'vector_score': ...,
    'bm25_score': ...,
    'combined_score': ...,
}
```

**BM25 caching.** Today BM25 is rebuilt on every query. With many documents per collection, rebuild this once per upload and store the tokenized corpus in Redis under key `bm25:collection:<id>`. Invalidate on any new doc upload to that collection.

### 3.3 LangGraph (`rag/graph.py`)

The graph topology is **unchanged** — same nodes, same edges. Internals change:

- `AgentState` swaps `document_id: int` for `collection_id: int`.
- `retrieve_documents` calls hybrid search by collection.
- `generate_answer` is the most-changed node (see §3.4).
- A new optional config dict gets passed in: `{"hybrid_enabled": True, "grading_enabled": True, "rewrite_enabled": True}`. Conditional edges check these.

**Ablation flags.** Implement by short-circuiting nodes:
- `hybrid_enabled = False` → `retrieve_documents` calls plain vector search instead of hybrid.
- `grading_enabled = False` → graph routes `retrieve_documents → generate_answer` directly.
- `rewrite_enabled = False` → grading-fail goes straight to `generate_answer` (with whatever was retrieved).

### 3.4 Answer generation with citations (`rag/graph.py`, `generate_answer` node)

**Today's prompt** dumps chunks under `[Source 1]`, `[Source 2]` headers but does not require the model to cite, and the UI doesn't render anything special.

**v2 prompt** (template):

```
You are a research assistant answering questions strictly from the provided sources.

You MUST cite sources inline using [N] markers, where N is the source number,
right after every claim you make. If a claim is supported by multiple sources, cite all of them, e.g. [1][3].

Do not invent citations. If you cannot answer from the sources, say so.

Sources:
[1] (Document: "Attention Is All You Need", page 3)
<chunk text>

[2] (Document: "BERT: Pre-training of Deep Bidirectional Transformers", page 2)
<chunk text>

...

Question: <user question>

Answer:
```

**Post-processing step.** After generation, parse the answer for every `[N]` token. Validate that N is within `1..len(sources)`. Strip any invalid markers. Build the structured `sources` JSON only with citation numbers actually used by the answer.

### 3.5 Streaming protocol (`rag/views.py`, `ChatView`)

The SSE event types stay the same: `reasoning`, `answer`, `complete`, `error`. The `answer` event payload now includes the structured `sources` array so the frontend can render citations.

```json
{
  "type": "answer",
  "content": "The Transformer is based entirely on self-attention [1]. It avoids recurrence...",
  "sources": [ { "citation_number": 1, "document_title": "...", "page_number": 3, ... }, ... ]
}
```

### 3.6 Frontend (`frontend/src`)

**New page:** Collections — list, create, rename, delete. Clicking a collection opens its chat.

**Updated chat UI:**
- Replace `[N]` substrings in the rendered answer with clickable `<sup>` (or pill) elements.
- Side panel slides in on click, showing the source chunk preview, document title, page number, and a "Open PDF" button (PDF opens in a new tab via the existing `file` URL on `Document`).
- A "Sources" footer under each AI message lists all citations used, in order.

PDF page navigation in the new tab can use a hash fragment: `<file_url>#page=<N>` — most browsers support this for PDFs.

### 3.7 Evaluation harness (`eval/`)

**Layout:**

```
eval/
├── test_set.json              # 40 Q/A items
├── corpus/                    # PDFs used by the test set
│   ├── paper1.pdf
│   └── ...
├── run_eval.py                # Runs once, writes results
├── run_ablations.py           # Loops over flag combinations
├── metrics.py                 # recall@5, MRR, RAGAS wrappers
├── seed_corpus.py             # Loads the corpus into a "Eval" collection
└── results/                   # Output dir
    ├── 2026-05-07_full.md
    ├── 2026-05-07_no_hybrid.md
    └── 2026-05-07_ablations.md
```

**`test_set.json` item schema:**

```json
{
  "id": "q1",
  "question": "What is the multi-head attention mechanism?",
  "expected_documents": ["Attention Is All You Need.pdf"],
  "expected_chunks_contain": [
    "multi-head attention allows the model to jointly attend"
  ],
  "ground_truth_answer": "Multi-head attention runs the attention function h times in parallel, with different learned projections, then concatenates the results."
}
```

**Pipeline (`run_eval.py`):**

```
1. Load test_set.json
2. For each item:
   a. Run the agent (via Python import, not HTTP) on the eval collection.
   b. Capture: retrieved_chunks, final_answer.
   c. Compute recall@5 = 1 if any expected_chunks_contain substring is in any retrieved chunk else 0.
   d. Compute reciprocal rank = 1 / (rank of first relevant chunk) or 0.
   e. Hand (question, retrieved_chunks, final_answer, ground_truth_answer) to RAGAS.
3. Aggregate means; write JSON + markdown table.
```

**RAGAS metrics used (v2):**
- `faithfulness` — grounded in retrieved context (no hallucinations).
- `answer_relevancy` — answers what was asked.

(Skip context_precision / context_recall in v2 — they require manual ground-truth chunks for every Q. Recall@5 + MRR already cover retrieval quality.)

**Ablation runner (`run_ablations.py`):**

```python
configs = [
    ("full",        {"hybrid": True,  "grading": True,  "rewrite": True}),
    ("no_hybrid",   {"hybrid": False, "grading": True,  "rewrite": True}),
    ("no_grading",  {"hybrid": True,  "grading": False, "rewrite": True}),
    ("no_rewrite",  {"hybrid": True,  "grading": True,  "rewrite": False}),
]
for name, cfg in configs:
    run_eval(cfg, output_name=name)
build_combined_table(configs)
```

---

## 4. Key design decisions and rationale

| Decision | Rationale |
|---|---|
| Collection is a separate model, not just a tag | Cleaner authorization, easier cascade deletes, easier per-collection BM25 cache. |
| One chunk per page (not cross-page) | Citations are honest. A chunk citing "p.5" actually came from p.5 only. |
| Citation numbering is per-answer, not global | LLM finds it easy to handle `[1]..[k]`. Global IDs would confuse it. |
| Validate citations post-hoc, don't trust LLM | LLMs hallucinate `[7]` even when only 5 sources exist. Strip invalid markers in code. |
| Eval calls the graph in-process, not via HTTP | Faster, deterministic, no auth tokens needed, easier to swap flags. |
| Ablation by config flag, not by editing code | Keeps a single source of truth; future researchers can re-run identical experiments. |
| RAGAS judge runs on Groq | Free; eval runs need ~80–160 LLM calls (40 Qs × 2–4 metrics). Don't burn Gemini budget. |

---

## 5. What stays the same (do not touch)

- JWT auth flow.
- `unified_llm.py` Gemini → Groq fallback logic.
- Celery worker setup.
- pgvector cosine distance ordering.
- SSE event protocol.
- Embedding model (`all-MiniLM-L6-v2`, 384-dim).
- Web search (Tavily) tool.

The v2 changes are scoped tightly. Any temptation to refactor unrelated code should be deferred to v3.
