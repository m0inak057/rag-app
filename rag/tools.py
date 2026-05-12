"""
Tool functions for the RAG agent.
These tools are the "skills" the agent can use to answer questions.
"""

from typing import Optional, List
from django.contrib.auth.models import User
from pgvector.django import CosineDistance
from rank_bm25 import BM25Okapi
import json
from .models import DocumentChunk, Document
from langchain.tools import tool
import os

# Embedding model (we'll initialize this in services.py)
embedding_model = None

def set_embedding_model(model):
    """Set the embedding model to use for vector search."""
    global embedding_model
    embedding_model = model


def _vector_search_impl(query: str, document_id: int = None, collection_id: int = None, top_k: int = 5) -> List[dict]:
    """
    Plain (non-@tool) implementation of vector search.
    Called internally by both vector_search_tool and hybrid_search_tool
    to avoid @tool-on-@tool invocation issues.
    """
    if embedding_model is None:
        raise ValueError("Embedding model not initialized. Call set_embedding_model() first.")
        
    if not document_id and not collection_id:
        raise ValueError("Must provide either document_id or collection_id")

    # Embed the query
    query_embedding = embedding_model.encode(query, convert_to_tensor=False).tolist()

    # Query the database for similar chunks
    queryset = DocumentChunk.objects.all()
    if document_id:
        queryset = queryset.filter(document_id=document_id)
    if collection_id:
        queryset = queryset.filter(document__collection_id=collection_id)

    chunks = queryset.annotate(
        distance=CosineDistance('embedding', query_embedding)
    ).order_by('distance')[:top_k]

    results = []
    for chunk in chunks:
        # Pre-fetch related document for title and ID
        doc = chunk.document
        results.append({
            'id': chunk.id,
            'document_id': doc.id,
            'document_title': doc.title,
            'page_number': chunk.page_number,
            'text': chunk.text,
            'relevance_score': 1 - float(chunk.distance),  # Convert distance to similarity
        })

    return results


@tool
def vector_search_tool(query: str, document_id: int = None, collection_id: int = None, top_k: int = 5) -> List[dict]:
    """
    Search for relevant document chunks using semantic similarity (vector embeddings).

    Args:
        query: The user's question or search query
        document_id: The ID of the document to search within
        collection_id: The ID of the collection to search within
        top_k: Number of top results to return (default: 5)

    Returns:
        List of relevant chunks with their metadata
    """
    try:
        return _vector_search_impl(query, document_id=document_id, collection_id=collection_id, top_k=top_k)
    except Exception as e:
        raise ValueError(f"Vector search failed: {str(e)}")


@tool
def hybrid_search_tool(query: str, document_id: int = None, collection_id: int = None, top_k: int = 5) -> List[dict]:
    """
    Perform hybrid search combining semantic (vector) and keyword (BM25) search.

    Args:
        query: The user's question or search query
        document_id: The ID of the document to search within
        collection_id: The ID of the collection to search within
        top_k: Number of top results to return (default: 5)

    Returns:
        List of relevant chunks ranked by combined score
    """
    try:
        if not document_id and not collection_id:
            raise ValueError("Must provide either document_id or collection_id")

        # Step 1: Get all chunks from the document/collection
        queryset = DocumentChunk.objects.select_related('document')
        if document_id:
            queryset = queryset.filter(document_id=document_id)
        if collection_id:
            queryset = queryset.filter(document__collection_id=collection_id)
            
        all_chunks = list(queryset)

        if not all_chunks:
            return []

        # Step 2: Semantic search — call plain helper directly (not the @tool wrapper)
        vector_results = _vector_search_impl(query, document_id=document_id, collection_id=collection_id, top_k=len(all_chunks))
        vector_scores = {r['id']: r['relevance_score'] for r in vector_results}
        
        # Step 3: Keyword search (BM25)
        texts = [chunk.text for chunk in all_chunks]
        bm25 = BM25Okapi([text.split() for text in texts])
        bm25_scores = bm25.get_scores(query.split())
        
        # Normalize BM25 scores to 0-1 range
        max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1
        bm25_scores_normalized = [score / max_bm25 for score in bm25_scores]
        
        # Step 4: Combine scores (50% vector, 50% keyword)
        combined_results = []
        for idx, chunk in enumerate(all_chunks):
            vector_score = vector_scores.get(chunk.id, 0)
            bm25_score = bm25_scores_normalized[idx]
            combined_score = 0.5 * vector_score + 0.5 * bm25_score
            
            combined_results.append({
                'id': chunk.id,
                'document_id': chunk.document.id,
                'document_title': chunk.document.title,
                'page_number': chunk.page_number,
                'text': chunk.text,
                'vector_score': vector_score,
                'bm25_score': bm25_score,
                'combined_score': combined_score,
            })
        
        # Sort and return top_k
        combined_results.sort(key=lambda x: x['combined_score'], reverse=True)
        return combined_results[:top_k]

    except Exception as e:
        logger.error(f"Hybrid search failed: {str(e)}")
        return []


@tool
def web_search_tool(query: str) -> List[dict]:
    """
    Search the web for information when the answer is not in local documents.
    Uses Tavily API for real-time information retrieval.
    
    Args:
        query: The search query
    
    Returns:
        List of search results with title, snippet, and URL
    """
    from tavily import TavilyClient
    
    api_key = os.getenv('TAVILY_API_KEY')
    if not api_key:
        raise ValueError("TAVILY_API_KEY not found in environment variables")
    
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=5)
        
        results = []
        for result in response.get('results', []):
            results.append({
                'title': result.get('title', ''),
                'snippet': result.get('snippet', ''),
                'url': result.get('url', ''),
                'relevance_score': result.get('score', 0),
            })
        
        return results
    
    except Exception as e:
        raise ValueError(f"Web search failed: {str(e)}")


@tool
def document_analyzer_tool(text: str, task: str = "summarize") -> str:
    """
    Analyze or summarize a document chunk using an LLM.
    Falls back to Groq if Gemini is rate-limited.
    
    Args:
        text: The text to analyze
        task: The task to perform (e.g., "summarize", "extract_key_points")
    
    Returns:
        The result of the analysis
    """
    from .unified_llm import get_unified_llm
    
    try:
        llm = get_unified_llm()
        
        if task == "summarize":
            prompt = f"Summarize the following text in 2-3 sentences:\n\n{text}"
        elif task == "extract_key_points":
            prompt = f"Extract the key points from the following text:\n\n{text}"
        else:
            prompt = f"Analyze the following text:\n\n{text}"
        
        response = llm.generate(prompt)
        return response['text']
    
    except Exception as e:
        raise ValueError(f"Document analysis failed: {str(e)}")


@tool
def grade_documents_tool(documents: List[dict], query: str) -> dict:
    """
    Grade the relevance of retrieved documents to the user's query.
    Uses an LLM to determine if documents are relevant.
    Falls back to Groq if Gemini is rate-limited.
    
    Args:
        documents: List of document chunks with their text
        query: The user's query
    
    Returns:
        A dict with 'relevant_documents', 'irrelevant_documents', and 'relevance_score'
    """
    from .unified_llm import get_unified_llm
    
    try:
        llm = get_unified_llm()
        
        relevant_docs = []
        irrelevant_docs = []
        
        for doc in documents:
            # Create a grading prompt
            prompt = f"""You are a grading assistant. Your job is to assess the relevance of a document to a user query.

User Query: {query}

Document:
{doc['text'][:500]}

Is this document relevant to the query? Answer with ONLY "YES" or "NO", nothing else."""
            
            response = llm.generate(prompt)
            answer = response['text'].strip().upper()
            
            if answer.startswith("YES"):
                relevant_docs.append(doc)
            else:
                irrelevant_docs.append(doc)
        
        return {
            'relevant_documents': relevant_docs,
            'irrelevant_documents': irrelevant_docs,
            'relevance_score': len(relevant_docs) / len(documents) if documents else 0,
        }
    
    except Exception as e:
        raise ValueError(f"Document grading failed: {str(e)}")
