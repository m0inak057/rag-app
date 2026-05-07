# Project Plan: The Agentic Document Intelligence System

Welcome to your advanced RAG project! This plan outlines the steps to build a sophisticated, agentic system that can reason across documents, use tools, and self-correct. This approach moves beyond a simple RAG chain into a modern, stateful AI application.

## Core Architecture & Technology Stack

Our system will be built around a "state machine" managed by **LangGraph**, with Django serving as the application backbone.

1.  **Backend**:
    - **`Django` & `DRF`**: For user management, API endpoints, and handling file uploads.
    - **`LangGraph`**: The "brain" of our operation. We'll build a graph-based state machine that orchestrates the agent's reasoning loop.
    - **`Celery` & `Redis`**: For asynchronous processing of document uploads, ensuring the UI remains responsive.

2.  **The Data & Retrieval Layer**:
    - **`PostgreSQL` + `pgvector`**: The primary database for storing application data and document vector embeddings.
    - **Hybrid Search**: We will implement both semantic (vector) and keyword (full-text) search for superior retrieval accuracy.
    - **Re-ranking**: An optional but powerful step using a library like `sentence-transformers` (cross-encoders) or `Cohere` to improve context quality before generation.

3.  **The Agent's "Tool Belt" (Capabilities)**:
    - **`vector_search_tool`**: Queries the `pgvector` store for document context.
    - **`web_search_tool`**: Uses an external API (e.g., **Tavily** or DuckDuckGo) for real-time information when the answer isn't in the local documents.
    - **`document_analyzer_tool`**: A potential future tool for complex summarization tasks.

4.  **Frontend**:
    - **`React (Vite)` + `TailwindCSS`**: For a modern, responsive user interface.
    - **Server-Sent Events (SSE)**: To stream the agent's "thoughts" and reasoning steps to the user in real-time.

---

## Step-by-Step Execution Plan

### Phase 1: Environment & Backend Foundation
1.  **Install Dependencies**:
    - Update the environment with new libraries: `langchain`, `langgraph`, `langchain-openai`, `tavily-python`, `celery`, `redis`, `rank_bm25`.
2.  **Integrate Celery & Redis**:
    - Add `redis` to the `docker-compose.yml` file.
    - Configure Celery in your Django project to offload heavy tasks.
3.  **Database Setup**:
    - Ensure the `pgvector` extension is enabled in your PostgreSQL database.
    - Update Django's `DATABASES` settings to connect to the Postgres instance.

### Phase 2: The Data Pipeline (Async ETL)
1.  **Modify Upload Endpoint**:
    - The `DocumentUploadView` will no longer process the document in the request-response cycle.
    - Instead, it will create a `Document` object with a "processing" status and trigger a Celery background task.
2.  **Create Celery Task**:
    - This task will perform the ETL (Extract, Transform, Load) process:
        - **Extract**: Use `PyMuPDF` to get text from the uploaded PDF.
        - **Chunk**: Split the text into smaller, overlapping chunks.
        - **Embed**: Use `sentence-transformers` to create vector embeddings for each chunk.
        - **Store**: Save the chunks and their embeddings to the `DocumentChunk` model.
        - **Update Status**: Once complete, update the `Document` status to "ready".

### Phase 3: Building the Agent's Toolbelt
1.  **Define Tool Functions** (in `rag/tools.py`):
    - `vector_search_tool`: A function that takes a query string, embeds it, and queries the `DocumentChunk` model using `pgvector`'s similarity search.
    - `web_search_tool`: A function that takes a query and uses the Tavily API to search the web.
2.  **Hybrid Search Logic**:
    - Enhance the `vector_search_tool` to also perform a keyword search (e.g., using Django's ORM `__icontains` or a more advanced full-text search).
    - Combine and de-duplicate the results from both searches.

### Phase 4: Constructing the Agentic Graph (LangGraph)
This is the core of the new architecture and will be implemented in `rag/services.py` or a new `rag/graph.py`.
1.  **Define Agent State**: Create a state object that will be passed between nodes. It should include `question`, `conversation_history`, `retrieved_documents`, `generation`, etc.
2.  **Define Graph Nodes**:
    - **`route_query`**: A router that decides which tool to use (vector search, web search, or just generate an answer).
    - **`retrieve_documents`**: A node that calls the `vector_search_tool`.
    - **`grade_documents`**: A node that checks if the retrieved documents are relevant to the question. If not, it can trigger a new search or a web search.
    - **`generate_answer`**: The generation node. It synthesizes the final answer based on the retrieved context and conversation history.
    - **`rewrite_query`**: A node that refines the user's question to be more effective for searching.
3.  **Define Graph Edges**:
    - Connect the nodes with conditional logic. For example, the edge from `grade_documents` will either go to `generate_answer` (if documents are good) or back to `rewrite_query` or `retrieve_documents` (if they are bad).
4.  **Compile the Graph**: Compile the nodes and edges into a runnable `LangGraph` application.

### Phase 5: API Layer & Frontend Integration
1.  **Update `ChatView`**:
    - The `ChatView` will now invoke the compiled `LangGraph` agent.
    - It will be refactored to use `StreamingHttpResponse` to stream the agent's state changes (e.g., "Retrieving documents...", "Grading relevance...") to the frontend as Server-Sent Events (SSE).
2.  **Frontend Development**:
    - Set up a React project using Vite.
    - Implement the UI for login, document upload, and the chat interface.
    - Use the `EventSource` API on the frontend to listen for the SSE stream from the Django backend.
    - Dynamically display the agent's reasoning steps as they are received.
    - Implement traceability by allowing users to see which document chunks were used for an answer.

### Phase 6: Advanced Enhancements
1.  **Conversational Memory**:
    - Modify the agent state and the `generate_answer` node to include the history from the `ChatMessage` model, allowing for follow-up questions.
2.  **Re-ranking**:
    - Add a new node to the graph after `retrieve_documents` that uses a cross-encoder to re-rank the search results for better context quality.
3.  **Human-in-the-loop**:
    - (Optional) Add a special state to the graph where the agent can pause and wait for user input if it encounters ambiguity.

This updated plan provides a clear path to building a highly impressive and modern AI application. Shall we proceed with **Phase 1: Installing the new dependencies**?
