#!/usr/bin/env python
"""
Unit test for citation validation function.
Tests extract_and_validate_citations independently.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import re
from typing import List, Dict, Any

# Test data
def create_test_state(answer_text, num_docs=3):
    """Create a mock state for testing."""
    return {
        "generation": answer_text,
        "retrieved_documents": [
            {
                'id': i+1,
                'document_id': 100 + i,
                'document_title': f'Document {i+1}',
                'page_number': i+1,
                'text': f'Content of document {i+1}',
                'combined_score': 0.9 - (i * 0.1),
            }
            for i in range(num_docs)
        ],
        "graded_documents": [],
        "reasoning_trace": [],
        "current_step": "validating_citations",
    }

def extract_and_validate_citations(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-processor to validate and structure citations in the generated answer.
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
            'text_preview': doc.get('text', '')[:200],
        }

    # Find all citations in the answer
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

    # Build structured sources array
    cited_sources = []
    for citation_num in sorted(used_citation_numbers):
        cited_sources.append(citation_map[str(citation_num)])

    state["generation"] = answer
    state["cited_sources"] = cited_sources

    return {
        "generation": state["generation"],
        "cited_sources": cited_sources,
        "current_step": state["current_step"],
        "reasoning_trace": state["reasoning_trace"]
    }


# Test cases
def test_valid_citations():
    """Test with valid citations."""
    print("\n[TEST 1] Valid citations")
    answer = "The transformer [1] uses attention mechanisms [2]. BERT [3] extends this approach."
    state = create_test_state(answer, num_docs=3)

    result = extract_and_validate_citations(state)

    assert result["generation"] == answer, "Answer should not be modified"
    assert len(result["cited_sources"]) == 3, f"Should have 3 cited sources, got {len(result['cited_sources'])}"
    assert result["cited_sources"][0]["citation_number"] == 1
    assert result["cited_sources"][1]["citation_number"] == 2
    assert result["cited_sources"][2]["citation_number"] == 3
    print("  [OK] Valid citations extracted correctly")


def test_invalid_citations():
    """Test with invalid citation numbers."""
    print("\n[TEST 2] Invalid citations (removed)")
    answer = "The transformer [1] is great [5]. This is [7] amazing."
    state = create_test_state(answer, num_docs=3)

    result = extract_and_validate_citations(state)

    # [5] and [7] should be removed
    assert "[5]" not in result["generation"], "[5] should be removed"
    assert "[7]" not in result["generation"], "[7] should be removed"
    assert "[1]" in result["generation"], "[1] should remain"
    assert len(result["cited_sources"]) == 1, f"Should have 1 cited source, got {len(result['cited_sources'])}"
    print("  [OK] Invalid citations removed correctly")


def test_duplicate_citations():
    """Test with duplicate citation numbers."""
    print("\n[TEST 3] Duplicate citations")
    answer = "According to [1] [1], and also [2] [1] shows that..."
    state = create_test_state(answer, num_docs=2)

    result = extract_and_validate_citations(state)

    # Should have sources 1 and 2
    cited_numbers = [s["citation_number"] for s in result["cited_sources"]]
    assert 1 in cited_numbers, "Citation [1] should be present"
    assert 2 in cited_numbers, "Citation [2] should be present"
    assert len(result["cited_sources"]) == 2, f"Should have 2 unique sources, got {len(result['cited_sources'])}"
    print("  [OK] Duplicate citations handled correctly")


def test_no_citations():
    """Test with no citations in answer."""
    print("\n[TEST 4] No citations")
    answer = "This answer has no citations."
    state = create_test_state(answer, num_docs=3)

    result = extract_and_validate_citations(state)

    assert result["generation"] == answer
    assert len(result["cited_sources"]) == 0, "Should have no cited sources"
    print("  [OK] No citations handled correctly")


def test_sequential_citations():
    """Test with sequential citation numbers."""
    print("\n[TEST 5] Sequential citations [1][2][3]")
    answer = "Evidence shows [1][2][3] supports this conclusion."
    state = create_test_state(answer, num_docs=3)

    result = extract_and_validate_citations(state)

    assert len(result["cited_sources"]) == 3
    cited_numbers = [s["citation_number"] for s in result["cited_sources"]]
    assert cited_numbers == [1, 2, 3], f"Expected [1, 2, 3], got {cited_numbers}"
    print("  [OK] Sequential citations parsed correctly")


def test_citation_metadata():
    """Test that citation metadata is correct."""
    print("\n[TEST 6] Citation metadata")
    answer = "From [1] and [2]..."
    state = create_test_state(answer, num_docs=3)

    result = extract_and_validate_citations(state)

    assert len(result["cited_sources"]) == 2

    # Check first source
    source1 = result["cited_sources"][0]
    assert source1["citation_number"] == 1
    assert source1["document_id"] == 100
    assert source1["document_title"] == "Document 1"
    assert source1["page_number"] == 1
    assert "Content of document 1" in source1["text_preview"]

    # Check second source
    source2 = result["cited_sources"][1]
    assert source2["citation_number"] == 2
    assert source2["document_id"] == 101
    assert source2["document_title"] == "Document 2"
    assert source2["page_number"] == 2

    print("  [OK] Citation metadata is correct")


# Run all tests
if __name__ == "__main__":
    print("=" * 60)
    print("Citation Validation Unit Tests")
    print("=" * 60)

    try:
        test_valid_citations()
        test_invalid_citations()
        test_duplicate_citations()
        test_no_citations()
        test_sequential_citations()
        test_citation_metadata()

        print("\n" + "=" * 60)
        print("[SUCCESS] All tests passed!")
        print("=" * 60 + "\n")

    except AssertionError as e:
        print(f"\n[FAILED] {str(e)}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {str(e)}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
