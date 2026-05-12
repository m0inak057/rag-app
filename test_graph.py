import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from rag.graph import create_rag_graph

rag_graph = create_rag_graph()
state = {
    "question": "What is inside the document?",
    "document_id": 1,
    "conversation_history": [],
    "retrieved_documents": [],
    "graded_documents": [],
    "generation": "",
    "reasoning_trace": [],
    "current_step": "",
    "loop_count": 0,
    "use_web_search": False,
    "rewrite_count": 0,
}

print("Invoking graph...")
try:
    result = rag_graph.invoke(state)
    print("Result state:", result)
except Exception as e:
    print("Exception occurred:", type(e), str(e))
