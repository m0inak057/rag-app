# 🧠 Agentic RAG — Document Intelligence System

A production-grade **Retrieval-Augmented Generation** system that goes beyond simple "embed → search → answer" pipelines. Built around a **LangGraph state machine**, it reasons over your documents using a multi-step agent loop with query rewriting, hybrid search, document grading, cross-encoder re-ranking, and web search fallback — all streamed to the user in real-time.

---

## ✨ What Makes This Different?

Most RAG tutorials follow a 3-step linear pipeline: embed the query, vector search, stuff context into a prompt. **This project replaces that with an agentic graph** where each step can influence what happens next:

| Feature | Typical RAG | This Project |
|---|:---:|:---:|
| Retrieval | Vector search only | **Hybrid search** (semantic + BM25 keyword) |
| Ranking | Raw similarity scores | **3-stage ranking**: vector → BM25 fusion → cross-encoder re-rank |
| Query handling | Single-shot | **Query expansion** (3 variants) + **LLM rewriting** (up to 2 retries) |
| Relevance check | None | **LLM-based document grading** with feedback loop |
| Fallback | None | **Automatic web search** via Tavily when local docs fail |
| Citations | Often hallucinated | **Post-generation citation validation** — invalid refs stripped |
| UX | Synchronous response | **Real-time SSE streaming** of agent reasoning trace |
| Evaluation | Manual testing | **Built-in ablation study framework** with Recall, MRR, Faithfulness metrics |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite)                      │
│   Login → Dashboard → Upload PDFs → Chat with Streaming Trace       │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ SSE / REST
┌────────────────────────────────▼────────────────────────────────────┐
│                     DJANGO REST API (DRF + JWT)                     │
│   /api/auth/  │  /api/documents/  │  /api/chat/  │  /api/collections│
└───────┬────────────────┬──────────────────┬────────────────────────┘
        │                │                  │
   ┌────▼────┐    ┌──────▼──────┐    ┌──────▼──────────────────────┐
   │  Celery  │    │  pgvector   │    │     LangGraph Agent         │
   │  Worker  │    │  (384-dim)  │    │                             │
   │          │    │             │    │  route → retrieve → grade   │
   │ PDF ETL: │    │  Hybrid     │    │    ↕         ↕              │
   │ Extract  │    │  Search:    │    │  rewrite ← (not relevant)  │
   │ Chunk    │    │  Vector +   │    │    ↓                        │
   │ Embed    │    │  BM25 +     │    │  web_search (fallback)      │
   │ Store    │    │  CrossEnc   │    │    ↓                        │
   └────┬─────┘    └──────┬──────┘    │  generate → validate_cites  │
        │                 │           └──────────────────────────────┘
        │                 │
   ┌────▼─────────────────▼──────┐    ┌────────────────────┐
   │   PostgreSQL + pgvector     │    │   Google Gemini     │
   │   (Document chunks +        │    │   (LLM generation,  │
   │    384-dim embeddings)      │    │    grading, rewrite) │
   └─────────────────────────────┘    └────────────────────┘
```

### Agent Flow (LangGraph State Machine)

```
START → route_query ─┬─→ retrieve_documents ─→ grade_documents ─┬─→ generate_answer → validate_citations → END
                     │                                           │
                     │        ┌── rewrite_query (max 2×) ←──────┘ (if not relevant)
                     │        └──→ retrieve_documents ───→ ...
                     │
                     └─→ web_search ─→ generate_answer → validate_citations → END
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Django 6 + DRF | REST API, auth, file handling |
| **Auth** | SimpleJWT | Token-based authentication |
| **Database** | PostgreSQL 16 + pgvector | Relational data + vector similarity search |
| **LLM** | Google Gemini 2.5 Flash | Answer generation, document grading, query rewriting |
| **Agent Framework** | LangGraph | State machine orchestrating the reasoning loop |
| **Embeddings** | `all-MiniLM-L6-v2` (384-dim) | Local embedding model via sentence-transformers |
| **Keyword Search** | BM25 (rank-bm25) | Keyword scoring for hybrid retrieval |
| **Re-ranking** | CrossEncoder (sentence-transformers) | Final re-ranking of retrieved chunks |
| **Web Search** | Tavily API | Fallback for queries not answered by local docs |
| **Task Queue** | Celery + Redis | Async PDF processing (extract → chunk → embed) |
| **Frontend** | React + Vite + Tailwind CSS | SPA with SSE streaming and source viewer |
| **PDF Parsing** | PyMuPDF (fitz) | Fast, accurate text extraction with page tracking |
| **Evaluation** | Custom metrics + RAGAS-style | Recall@K, MRR, Faithfulness, Answer Relevancy |

---

## 📁 Project Structure

```
RAG_APP/
├── config/                     # Django project configuration
│   ├── settings.py             # Database, Celery, Gemini, JWT config
│   ├── celery.py               # Celery app initialization
│   ├── urls.py                 # Root URL routing + auth endpoints
│   └── wsgi.py / asgi.py
│
├── rag/                        # Core RAG application
│   ├── models.py               # Collection, Document, DocumentChunk, Chat models
│   ├── graph.py                # ★ LangGraph state machine (the agent brain)
│   ├── tools.py                # ★ Agent tools: vector search, hybrid search, BM25, web search, grading
│   ├── services.py             # ETL pipeline: PDF extraction, chunking, embedding
│   ├── gemini_client.py        # Gemini API wrapper with cost tracking
│   ├── unified_llm.py          # LLM manager (singleton pattern)
│   ├── tasks.py                # Celery async tasks for document processing
│   ├── views.py                # API views: upload, chat (SSE streaming), collections
│   ├── serializers.py          # DRF serializers
│   ├── urls.py                 # App URL routing
│   └── tests.py                # Django test suite
│
├── eval/                       # Evaluation & benchmarking framework
│   ├── run_ablations.py        # ★ Ablation study: test 4 RAG configurations
│   ├── run_eval.py             # Full evaluation runner
│   ├── metrics.py              # Recall@K, MRR, Faithfulness, Answer Relevancy
│   ├── seed_corpus.py          # Seed test documents into the DB
│   ├── test_set.json           # 40-question evaluation dataset
│   ├── corpus/                 # Test PDFs for evaluation
│   └── results/                # Evaluation output (JSON)
│
├── frontend/                   # React SPA
│   ├── src/
│   │   ├── components/
│   │   │   ├── Login.jsx       # JWT authentication
│   │   │   ├── Dashboard.jsx   # Tab navigation (Chat, Upload, Documents, Collections)
│   │   │   ├── Chat.jsx        # ★ Chat UI with SSE streaming + source viewer panel
│   │   │   ├── DocumentUpload.jsx  # Drag-and-drop PDF upload
│   │   │   ├── DocumentList.jsx    # Document browser
│   │   │   └── CollectionList.jsx  # Collection manager
│   │   └── services/
│   │       └── api.js          # Axios instance with auth interceptor
│   ├── vite.config.js          # Dev server with /api proxy
│   └── tailwind.config.js
│
├── docker-compose.yml          # PostgreSQL (pgvector) + Redis
├── requirements.txt            # Python dependencies
├── manage.py                   # Django CLI
└── run.sh                      # One-command startup script
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **Docker & Docker Compose** (for PostgreSQL + Redis)
- **Google Gemini API key** — [Get one here](https://aistudio.google.com/app/apikeys)
- *(Optional)* **Tavily API key** for web search fallback — [Get one here](https://tavily.com)

### 1. Clone & Setup Environment

```bash
git clone https://github.com/m0inak057/rag-app.git
cd rag-app

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Required: Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Web search fallback
TAVILY_API_KEY=your_tavily_api_key_here

# Optional: Hugging Face (for model downloads)
HF_TOKEN=your_hf_token_here
```

### 4. Start Infrastructure (PostgreSQL + Redis)

```bash
docker-compose up -d
```

This spins up:
- **PostgreSQL 16** with pgvector extension on port `5433`
- **Redis 7** on port `6379`

### 5. Initialize the Database

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Start All Services

**Option A — One command (Linux/Mac):**
```bash
bash run.sh
```

**Option B — Manual (recommended for Windows):**

Terminal 1 — Django server:
```bash
python manage.py runserver
```

Terminal 2 — Celery worker:
```bash
celery -A config worker -l info
```

Terminal 3 — Frontend dev server:
```bash
cd frontend
npm install
npm run dev
```

### 7. Open the App

- **Frontend**: [http://localhost:5173](http://localhost:5173)
- **API Root**: [http://localhost:8000](http://localhost:8000)
- **Django Admin**: [http://localhost:8000/admin](http://localhost:8000/admin)

---

## 📡 API Reference

All endpoints require JWT authentication (except auth endpoints).

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register/` | Register a new user |
| `POST` | `/api/auth/token/` | Login → get access + refresh tokens |
| `POST` | `/api/auth/token/refresh/` | Refresh an expired access token |

### Collections

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/collections/` | List all collections |
| `POST` | `/api/collections/` | Create a new collection |
| `GET` | `/api/collections/:id/` | Get collection with documents |
| `PATCH` | `/api/collections/:id/` | Update collection |
| `DELETE` | `/api/collections/:id/` | Delete collection and all documents |

### Documents

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/documents/` | List all uploaded documents |
| `POST` | `/api/documents/upload/` | Upload a PDF (async processing via Celery) |

### Chat (Streaming)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat/` | Send a question → receive SSE stream |

**Request body:**
```json
{
  "question": "What are the main findings?",
  "document_id": 1,
  "collection_id": null,
  "conversation_id": null
}
```

**SSE response stream:**
```
data: {"type": "reasoning", "content": "[ROUTE] Analyzing query..."}
data: {"type": "reasoning", "content": "[RETRIEVE] Found 5 chunks (hybrid)"}
data: {"type": "reasoning", "content": "[GRADE] Relevance: 0.80 (4/5 relevant)"}
data: {"type": "reasoning", "content": "[GENERATE] Answer generated via gemini"}
data: {"type": "reasoning", "content": "[VALIDATE] Found 3 valid citations: [1, 2, 3]"}
data: {"type": "answer", "content": "The main findings [1] show that...", "sources": [...]}
data: {"type": "complete", "message_id": 42, "sources": [...]}
```

### Monitoring

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/usage-stats/` | Gemini API usage and cost tracking |
| `GET` | `/api/llm-provider-status/` | Current LLM provider status |

---

## 🔬 Evaluation Framework

The `eval/` directory contains a complete benchmarking system to measure RAG quality.

### Metrics

| Metric | What It Measures |
|---|---|
| **Recall@K** | Did we retrieve at least one chunk containing the expected information? |
| **MRR** | Mean Reciprocal Rank — how high is the first relevant result? |
| **Faithfulness** | How grounded is the generated answer in the retrieved context? |
| **Answer Relevancy** | How well does the answer address the original question? |

### Ablation Study

Tests 4 configurations to measure each component's contribution:

| Config | Hybrid Search | Grading | Query Rewriting |
|---|:---:|:---:|:---:|
| **A — Full** | ✅ | ✅ | ✅ |
| **B — No Rewrite** | ✅ | ✅ | ❌ |
| **C — Hybrid Only** | ✅ | ❌ | ❌ |
| **D — Vector Only** | ❌ | ❌ | ❌ |

**Run the ablation study:**
```bash
python eval/run_ablations.py
```

Results are saved to `eval/results/` as timestamped JSON files with a comparison table printed to stdout.

---

## 💰 Cost Management

The app uses **Gemini 2.5 Flash** — one of the most cost-effective LLMs available:

- **Input**: ~$0.075 per 1M tokens
- **Output**: ~$0.30 per 1M tokens
- **Typical query cost**: < $0.001

Built-in cost controls:
- Token usage logged per request via `CostTracker`
- Daily cost monitoring via `/api/usage-stats/`
- Max output tokens capped at 8,000 per request

---

## 🧩 Key Design Decisions

1. **Local embeddings** — `all-MiniLM-L6-v2` runs on-device (no API calls for embeddings), keeping costs near-zero for the retrieval layer.

2. **pgvector over dedicated vector DBs** — Using PostgreSQL's pgvector extension means documents, chunks, embeddings, users, and chat history all live in one database. No Pinecone/Weaviate/Qdrant dependency.

3. **Hybrid search with score fusion** — 70% vector similarity + 30% BM25 keyword score, followed by cross-encoder re-ranking. This catches both semantically similar and keyword-matching chunks.

4. **LangGraph over LangChain chains** — A state machine is more debuggable and flexible than a linear chain. Each node can inspect the full state and route to any other node.

5. **SSE streaming** — The agent's reasoning trace streams in real-time, so users see `[ROUTE]`, `[RETRIEVE]`, `[GRADE]`, `[GENERATE]` steps live — not just a loading spinner.

6. **Citation validation as a dedicated graph node** — Hallucinated citation numbers (e.g., `[7]` when only 5 sources exist) are stripped post-generation before reaching the user.

---

## 📜 License

This project is for educational and portfolio purposes.

---

## 🤝 Contributing

Pull requests and issues are welcome. For major changes, please open an issue first to discuss what you would like to change.
