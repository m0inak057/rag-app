"""
RAG Pipeline Services

This module contains TWO pipelines:

  📄 ETL Pipeline (Phase 3 - Upload):
     Upload PDF → Extract Text → Chunk Text → Embed → Store in DB

  💬 RAG Pipeline (Phase 4 - Chat):
     User Question → Embed Question → Vector Search → Build Prompt → LLM Answer
"""

import fitz  # PyMuPDF — fast and accurate PDF text extraction
from sentence_transformers import SentenceTransformer
from pgvector.django import CosineDistance
from django.conf import settings
from .models import Document, DocumentChunk, ChatConversation, ChatMessage

# ─────────────────────────────────────────────────────────
# Load models/clients ONCE when the server starts
# ─────────────────────────────────────────────────────────
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')


# ═══════════════════════════════════════════════════════════
#  ETL PIPELINE (Phase 3)
# ═══════════════════════════════════════════════════════════

def extract_chunks_with_pages(file_path: str, chunk_size: int = 1000, overlap: int = 200) -> list[dict]:
    """
    Extracts text from a PDF and chunks it page by page.
    Each chunk includes the page number it came from.
    Chunks do not span across page boundaries.
    """
    chunks_with_pages = []
    doc = fitz.open(file_path)
    
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        if not text.strip():
            continue

        page_chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]
            if chunk_text.strip():
                page_chunks.append(chunk_text.strip())
            start += chunk_size - overlap
        
        for chunk in page_chunks:
            chunks_with_pages.append({
                "text": chunk,
                "page_number": page_num + 1  # 1-based page number
            })
            
    doc.close()
    return chunks_with_pages


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """
    Splits a large text into smaller overlapping chunks.

    Why overlapping? If a sentence is at the boundary of two chunks,
    the overlap ensures it appears fully in at least one chunk.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks


def process_document(document) -> int:
    """
    Full ETL: Extract text → Chunk → Embed → Store in DocumentChunk table.
    Returns the number of chunks created.
    """
    file_path = document.file.path
    
    # Use the new page-aware chunking function
    chunks_with_pages = extract_chunks_with_pages(file_path)

    if not chunks_with_pages:
        raise ValueError(f"No text could be extracted from '{document.title}'. "
                         "The PDF might be image-based or empty.")

    # Separate texts and page numbers for embedding
    texts = [item['text'] for item in chunks_with_pages]
    embeddings = embedding_model.encode(texts, show_progress_bar=True)

    chunk_objects = [
        DocumentChunk(
            document=document,
            text=item['text'],
            page_number=item['page_number'],
            embedding=embedding.tolist(),
        )
        for item, embedding in zip(chunks_with_pages, embeddings)
    ]
    
    DocumentChunk.objects.bulk_create(chunk_objects)
    
    # Update page count on the document
    doc = fitz.open(file_path)
    document.page_count = len(doc)
    doc.close()
    document.save()
    
    return len(chunk_objects)


# ═══════════════════════════════════════════════════════════
#  RAG PIPELINE (Phase 4)
# ═══════════════════════════════════════════════════════════

def retrieve_relevant_chunks(question: str, document_id: int = None, collection_id: int = None, top_k: int = 5) -> list[DocumentChunk]:
    """
    STEP 1 & 2 of RAG: Embed the question and find the most similar chunks.

    How it works:
      1. The user's question is converted to a 384-dim vector
      2. We search the DocumentChunk table for chunks belonging to
         this document or collection, ordered by cosine similarity (closest first)
      3. Return the top K most relevant chunks

    Args:
        question:      The user's question string
        document_id:   Which document to search within (optional if collection_id provided)
        collection_id: Which collection to search within (optional if document_id provided)
        top_k:         How many chunks to retrieve (default: 5)

    Returns:
        A list of DocumentChunk objects, most relevant first.
    """
    if not document_id and not collection_id:
        raise ValueError("Must provide either document_id or collection_id")

    # Embed the question using the SAME model used during ETL
    question_embedding = embedding_model.encode(question).tolist()

    # Query the DB: find chunks from this document or collection, sorted by similarity
    # CosineDistance = 0 means identical, CosineDistance = 2 means opposite
    queryset = DocumentChunk.objects.all()
    if document_id:
        queryset = queryset.filter(document_id=document_id)
    if collection_id:
        queryset = queryset.filter(document__collection_id=collection_id)

    relevant_chunks = (
        queryset
        .order_by(CosineDistance('embedding', question_embedding))
        [:top_k]
    )

    return list(relevant_chunks)


def build_prompt(question: str, chunks: list[DocumentChunk], chat_history: list[dict] = None) -> list[dict]:
    """
    STEP 3 of RAG: Assemble the prompt with context + chat history.

    The prompt tells the LLM:
      - What role it plays (helpful assistant)
      - The context from the document (retrieved chunks)
      - The conversation history (so it can remember previous messages)
      - The user's current question
    """
    # Combine the text of all retrieved chunks into one context block
    context = "\n\n---\n\n".join([chunk.text for chunk in chunks])

    # System message: sets the LLM's behavior
    system_message = {
        "role": "system",
        "content": (
            "You are a helpful AI assistant that answers questions based STRICTLY "
            "on the provided document context. If the answer is not found in the "
            "context, say 'I couldn't find this information in the document.' "
            "Do not make up information.\n\n"
            f"## Document Context:\n{context}"
        ),
    }

    # Build the messages list
    messages = [system_message]

    # Add chat history (previous Q&A in this conversation)
    if chat_history:
        for msg in chat_history:
            messages.append({
                "role": "user" if msg["role"] == "user" else "assistant",
                "content": msg["content"],
            })

    # Add the current question
    messages.append({"role": "user", "content": question})

    return messages


def generate_answer(question: str, document_id: int = None, collection_id: int = None, conversation_id: int = None, user=None) -> dict:
    """
    The MAIN RAG function. Orchestrates the full pipeline:

      1. Get or create a conversation
      2. Retrieve relevant chunks from the document
      3. Build the prompt with context + history
      4. Send to Groq LLM
      5. Save Q&A to chat history
      6. Return the answer

    Args:
        question:        The user's question
        document_id:     Which document to query against (optional)
        collection_id:   Which collection to query against (optional)
        conversation_id: Existing conversation ID (None = start new conversation)
        user:            The authenticated user

    Returns:
        A dict with the answer, conversation_id, and sources.
    """
    if not document_id and not collection_id:
        raise ValueError("Must provide either document_id or collection_id")

    # ── Step 1: Get or create conversation ──
    document = None
    collection = None
    if document_id:
        document = Document.objects.get(id=document_id, user=user)
    if collection_id:
        from .models import Collection
        collection = Collection.objects.get(id=collection_id, user=user)

    if conversation_id:
        conversation = ChatConversation.objects.get(
            id=conversation_id, user=user
        )
        if document:
            assert conversation.document == document
        if collection:
            assert conversation.collection == collection
    else:
        conversation = ChatConversation.objects.create(
            user=user, document=document, collection=collection
        )

    # ── Step 2: Retrieve relevant chunks ──
    chunks = retrieve_relevant_chunks(question, document_id=document_id, collection_id=collection_id, top_k=5)

    if not chunks:
        return {
            "answer": "No relevant information found in the document.",
            "conversation_id": conversation.id,
            "sources": [],
        }

    # ── Step 3: Get chat history for context ──
    previous_messages = ChatMessage.objects.filter(
        conversation=conversation
    ).values('role', 'content')[:20]  # Last 20 messages max

    chat_history = list(previous_messages) if previous_messages else None

    # ── Step 4: Build prompt and call Groq LLM ──
    messages = build_prompt(question, chunks, chat_history)

    response = groq_client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=messages,
        temperature=0.3,        # Lower = more factual, less creative
        max_tokens=1024,
    )

    answer = response.choices[0].message.content

    # ── Step 5: Save Q&A to chat history ──
    ChatMessage.objects.create(
        conversation=conversation,
        role='user',
        content=question,
    )
    ChatMessage.objects.create(
        conversation=conversation,
        role='ai',
        content=answer,
    )

    # ── Step 6: Return the response ──
    return {
        "answer": answer,
        "conversation_id": conversation.id,
        "sources": [
            {
                "chunk_id": chunk.id,
                "text_preview": chunk.text[:200] + "...",
                "document_id": chunk.document.id,
                "document_title": chunk.document.title,
                "page_number": chunk.page_number,
            }
            for chunk in chunks
        ],
    }
