"""
LangGraph state machine for the Agentic RAG system.
This defines the agent's reasoning loop and decision-making process.
"""

from typing import List, Dict, Any, Optional, TypedDict
from datetime import datetime
import json
from langgraph.graph import StateGraph, START, END
import os

from .tools import (
    vector_search_tool,
    hybrid_search_tool,
    web_search_tool,
    grade_documents_tool,
)


# Define the Agent State as a TypedDict for LangGraph
class AgentState(TypedDict, total=False):
    """State object for the RAG agent."""
    question: str
    conversation_history: List[Dict[str, str]]
    retrieved_documents: List[Dict[str, Any]]
    graded_documents: List[Dict[str, Any]]
    generation: str
    reasoning_trace: List[str]
    current_step: str
    loop_count: int
    document_id: int
    collection_id: int
    use_web_search: bool
    rewrite_count: int
    cited_sources: List[Dict[str, Any]]


def route_query(state: AgentState) -> dict:
    """
    Route the user's query to the appropriate tool or directly to generation.
    Decides: "Do I need vector search, web search, or can I answer directly?"
    """
    state["current_step"] = "routing_query"
    state["reasoning_trace"].append(f"[ROUTE] Analyzing query: '{state['question']}'")
    
    # Simple heuristic: if question contains keywords like "web", "latest", "news", use web search
    web_keywords = ["latest", "recent", "news", "today", "current", "web"]
    if any(keyword in state["question"].lower() for keyword in web_keywords):
        state["use_web_search"] = True
        state["reasoning_trace"].append("[ROUTE] → Web search needed for current information")
    else:
        state["reasoning_trace"].append("[ROUTE] → Document search will be used")
        
    return {"use_web_search": state.get("use_web_search", False), "current_step": state["current_step"], "reasoning_trace": state["reasoning_trace"]}


def rewrite_query(state: AgentState) -> dict:
    """
    Refine the user's query to be more effective for searching.
    Uses an LLM to rephrase vague questions.
    Falls back to Groq if Gemini is rate-limited.
    """
    from .unified_llm import get_unified_llm
    
    state["current_step"] = "rewriting_query"
    state.setdefault("rewrite_count", 0)
    state["rewrite_count"] += 1
    
    if state["rewrite_count"] > 2:
        state["reasoning_trace"].append("[REWRITE] Max rewrite attempts reached")
        return {"current_step": state["current_step"], "rewrite_count": state["rewrite_count"], "reasoning_trace": state["reasoning_trace"]}
    
    try:
        llm = get_unified_llm()
        
        prompt = f"""You are a query optimization expert. 
The user's original question is: "{state['question']}"

Rewrite this question to be more specific and clear for document search. 
Return ONLY the rewritten question, nothing else."""
        
        response = llm.generate(prompt)
        original = state["question"]
        state["question"] = response['text'].strip()
        provider = response['provider'].value
        state["reasoning_trace"].append(f"[REWRITE] '{original}' → '{state['question']}' (via {provider})")
        
    except Exception as e:
        state["reasoning_trace"].append(f"[REWRITE] Failed: {str(e)}")
        
    return {"question": state["question"], "current_step": state["current_step"], "rewrite_count": state["rewrite_count"], "reasoning_trace": state["reasoning_trace"]}


def retrieve_documents(state: AgentState) -> dict:
    """
    Retrieve relevant document chunks using hybrid search (semantic + keyword).
    """
    state["current_step"] = "retrieving_documents"
    state["reasoning_trace"].append("[RETRIEVE] Starting document search...")
    
    try:
        # Use hybrid search for better results
        state["retrieved_documents"] = hybrid_search_tool.invoke({
            "query": state["question"], 
            "document_id": state.get("document_id"),
            "collection_id": state.get("collection_id"),
            "top_k": 5
        })
        
        state["reasoning_trace"].append(
            f"[RETRIEVE] Found {len(state['retrieved_documents'])} relevant chunks"
        )
        
        if len(state["retrieved_documents"]) == 0:
            state["reasoning_trace"].append("[RETRIEVE] No documents found, will try web search")
            state["use_web_search"] = True
            
    except Exception as e:
        state["reasoning_trace"].append(f"[RETRIEVE] Error: {str(e)}")
        state["use_web_search"] = True
        
    return {"retrieved_documents": state.get("retrieved_documents", []), "use_web_search": state.get("use_web_search", False), "current_step": state["current_step"], "reasoning_trace": state["reasoning_trace"]}


def grade_documents(state: AgentState) -> dict:
    """
    Evaluate if the retrieved documents are relevant to the question.
    If not relevant, trigger a new search or rewrite the query.
    """
    state["current_step"] = "grading_documents"
    state["reasoning_trace"].append("[GRADE] Evaluating document relevance...")
    
    try:
        grade_result = grade_documents_tool.invoke({
            "documents": state["retrieved_documents"],
            "query": state["question"]
        })
        
        state["graded_documents"] = grade_result['relevant_documents']
        relevance = grade_result['relevance_score']
        
        state["reasoning_trace"].append(
            f"[GRADE] Relevance score: {relevance:.2f} "
            f"({len(state['graded_documents'])}/{len(state['retrieved_documents'])} relevant)"
        )
    except Exception as e:
        state["reasoning_trace"].append(f"[GRADE] Error: {str(e)}, proceeding with available docs")
        state["graded_documents"] = state["retrieved_documents"]
        
    return {"graded_documents": state.get("graded_documents", []), "current_step": state["current_step"], "reasoning_trace": state["reasoning_trace"]}


def web_search(state: AgentState) -> dict:
    """
    Perform web search when local documents are not sufficient.
    """
    state["current_step"] = "web_search"
    state["reasoning_trace"].append("[WEB] Performing web search...")
    
    try:
        web_results = web_search_tool.invoke({"query": state["question"]})
        
        # Convert web results to document-like format
        state["retrieved_documents"] = [
            {
                'id': idx,
                'text': f"{result['title']}\n{result['snippet']}",
                'url': result.get('url'),
                'combined_score': result.get('relevance_score', 0),
                'source': 'web',
            }
            for idx, result in enumerate(web_results)
        ]
        
        state["reasoning_trace"].append(
            f"[WEB] Found {len(web_results)} web results"
        )
        
    except Exception as e:
        state["reasoning_trace"].append(f"[WEB] Error: {str(e)}")
        
    return {"retrieved_documents": state.get("retrieved_documents", []), "current_step": state["current_step"], "reasoning_trace": state["reasoning_trace"]}


def generate_answer(state: AgentState) -> dict:
    """
    Generate the final answer based on retrieved documents and conversation history.
    Uses Gemini if budget allows, falls back to free Groq if needed.
    """
    from .unified_llm import get_unified_llm
    
    state["current_step"] = "generating_answer"
    state["reasoning_trace"].append("[GENERATE] Compiling context and generating answer...")
    
    try:
        llm = get_unified_llm()
        
        # Compile context from retrieved documents
        docs_to_use = state.get("graded_documents") if state.get("graded_documents") else state.get("retrieved_documents", [])
        context_text = "\n\n".join([
            f"[Source {idx+1}] [{doc.get('document_title', 'Unknown')} (Page {doc.get('page_number', '?')})]\n{doc['text'][:500]}"
            for idx, doc in enumerate(docs_to_use[:5])
        ])
        
        # Build conversation history string
        history_text = ""
        if state.get("conversation_history"):
            history_text = "\nConversation History:\n"
            for msg in state["conversation_history"][-3:]:  # Last 3 messages for context
                history_text += f"- {msg['role']}: {msg['content'][:200]}\n"
        
        # Construct the prompt
        user_prompt = f"""You are a helpful AI assistant that answers questions based on provided documents.
Please answer the user's question clearly and concisely.

CRITICAL INSTRUCTIONS FOR CITATIONS:
Every time you use information from the provided context, you MUST cite the source using its designated number in brackets, e.g., [1] or [2].
- DO NOT use the document title as the citation (e.g., NOT "According to [Document A]..."). Only use the bracketed numbers.
- If you synthesize from multiple sources, cite all of them, e.g., "The approach varies [1][3]".
- If you're unsure or the answer is not in the context, say so.

{history_text}

Context Documents:
{context_text}

User Question: {state['question']}

Please provide your answer below with bracketed citations."""
        
        response = llm.generate(user_prompt)
        state["generation"] = response['text']
        provider = response['provider'].value
        switched = response.get('switched', False)
        
        if switched:
            state["reasoning_trace"].append(f"[GENERATE] 🔄 Switched to Groq API (Gemini limit reached)")
        else:
            state["reasoning_trace"].append(f"[GENERATE] Answer generated via {provider}")
        
    except Exception as e:
        state["generation"] = f"Error generating answer: {str(e)}"
        state["reasoning_trace"].append(f"[GENERATE] Error: {str(e)}")
        
    return {"generation": state.get("generation", ""), "current_step": state["current_step"], "reasoning_trace": state["reasoning_trace"]}


import re

def extract_and_validate_citations(state: AgentState) -> dict:
    """
    Post-processor to validate and structure citations in the generated answer.

    Actions:
    1. Extract all [N] citations from the answer
    2. Validate they match the source documents provided
    3. Remove invalid citations
    4. Build structured sources array with metadata
    5. Store only sources that are actually cited
    """
    state["current_step"] = "validating_citations"
    answer = state.get("generation", "")

    docs_to_use = state.get("graded_documents", []) or state.get("retrieved_documents", [])
    docs_to_use = docs_to_use[:5]  # Only support up to 5 sources

    # Build a map of citation_number -> document metadata
    citation_map = {}
    for idx, doc in enumerate(docs_to_use):
        citation_num = idx + 1
        citation_map[str(citation_num)] = {
            'citation_number': citation_num,
            'chunk_id': doc.get('id'),
            'document_id': doc.get('document_id'),
            'document_title': doc.get('document_title', 'Unknown'),
            'page_number': doc.get('page_number'),
            'text_preview': doc.get('text', '')[:200],  # First 200 chars as preview
        }

    # Find all citations in the answer (patterns like [1], [2], [1][3], etc.)
    all_citations = re.findall(r'\[(\d+)\]', answer)

    # Track invalid and valid citations
    invalid_citations = []
    used_citation_numbers = set()

    for citation_num in all_citations:
        if citation_num not in citation_map:
            invalid_citations.append(f"[{citation_num}]")
            answer = answer.replace(f"[{citation_num}]", "")
        else:
            used_citation_numbers.add(int(citation_num))

    # Build structured sources array with only cited sources
    cited_sources = []
    for citation_num in sorted(used_citation_numbers):
        cited_sources.append(citation_map[str(citation_num)])

    # Log validation results
    if invalid_citations:
        state["reasoning_trace"].append(f"[VALIDATE] Removed invalid citations: {', '.join(invalid_citations)}")

    state["reasoning_trace"].append(f"[VALIDATE] Found {len(cited_sources)} valid citations: {list(used_citation_numbers)}")

    # Store structured sources in state
    state["generation"] = answer
    state["cited_sources"] = cited_sources

    return {
        "generation": state["generation"],
        "cited_sources": cited_sources,
        "current_step": state["current_step"],
        "reasoning_trace": state["reasoning_trace"]
    }


# Build the StateGraph
def create_rag_graph():
    """
    Create and compile the RAG agent graph.
    
    Graph flow:
    1. route_query: Decides between document search, web search, or direct generation
    2. retrieve_documents: Performs semantic + keyword search
    3. grade_documents: Evaluates relevance of retrieved docs
    4. rewrite_query: Refines the query if needed
    5. web_search: Fallback to web search if local docs aren't good
    6. generate_answer: Creates the final response using retrieved context
    """
    
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("route_query", route_query)
    workflow.add_node("rewrite_query", rewrite_query)
    workflow.add_node("retrieve_documents", retrieve_documents)
    workflow.add_node("grade_documents", grade_documents)
    workflow.add_node("web_search", web_search)
    workflow.add_node("generate_answer", generate_answer)
    workflow.add_node("validate_citations", extract_and_validate_citations)
    
    # Add edges
    workflow.add_edge(START, "route_query")
    
    # From route_query
    workflow.add_conditional_edges(
        "route_query",
        lambda state: "web_search" if state.get("use_web_search", False) else "retrieve_documents"
    )
    
    # From retrieve_documents
    workflow.add_conditional_edges(
        "retrieve_documents",
        lambda state: "web_search" if state.get("use_web_search", False) else "grade_documents"
    )
    
    # From grade_documents
    workflow.add_conditional_edges(
        "grade_documents",
        lambda state: "generate_answer" if len(state.get("graded_documents", [])) > 0 else "rewrite_query"
    )
    
    # From rewrite_query
    workflow.add_conditional_edges(
        "rewrite_query",
        lambda state: "generate_answer" if state.get("rewrite_count", 0) > 2 else "retrieve_documents"
    )
    
    # From web_search
    workflow.add_edge("web_search", "generate_answer")
    
    # From generate_answer to validate_citations
    workflow.add_edge("generate_answer", "validate_citations")
    
    # From validate_citations
    workflow.add_edge("validate_citations", END)
    
    # Compile the graph
    return workflow.compile()


# Create the compiled graph instance (lazy-loaded in views.py)
# rag_graph = create_rag_graph()
