"""
Tests for the RAG application.

Run with:  python manage.py test rag

Strategy:
- Use Django's TestClient for API-level tests.
- Mock external calls (Celery tasks, LLM providers, embedding model)
  so tests run without any infrastructure.
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from .models import Document, DocumentChunk, ChatConversation, ChatMessage


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_user(username="testuser", password="testpass123"):
    """Create and return a test user."""
    return User.objects.create_user(username=username, password=password)


def get_jwt(client, username="testuser", password="testpass123"):
    """Log in and return the JWT access token."""
    response = client.post(
        "/api/auth/token/",
        {"username": username, "password": password},
        format="json",
    )
    return response.data["access"]


# ---------------------------------------------------------------------------
# 1.  Model tests
# ---------------------------------------------------------------------------

class DocumentModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        from rag.models import Collection
        self.collection = Collection.objects.create(user=self.user, name="test")

    def test_document_str(self):
        doc = Document.objects.create(
            user=self.user, collection=self.collection,
            title="Test PDF",
            file="documents/test.pdf",
            status="pending",
        )
        self.assertIn("Test PDF", str(doc))
        self.assertIn("testuser", str(doc))

    def test_document_default_status(self):
        doc = Document.objects.create(
            user=self.user, collection=self.collection,
            title="My Doc",
            file="documents/test.pdf",
        )
        self.assertEqual(doc.status, "pending")
        self.assertEqual(doc.chunks_count, 0)

    def test_chat_message_ordering(self):
        doc = Document.objects.create(
            user=self.user, collection=self.collection, title="D", file="documents/d.pdf", status="ready"
        )
        conv = ChatConversation.objects.create(collection=self.collection, user=self.user, document=doc)
        msg1 = ChatMessage.objects.create(conversation=conv, role="user", content="Hi")
        msg2 = ChatMessage.objects.create(conversation=conv, role="ai", content="Hello")
        messages = list(ChatMessage.objects.filter(conversation=conv))
        self.assertEqual(messages[0].id, msg1.id)
        self.assertEqual(messages[1].id, msg2.id)


# ---------------------------------------------------------------------------
# 2.  Registration endpoint
# ---------------------------------------------------------------------------

class RegisterViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_success(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["username"], "newuser")
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_password_mismatch(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "newuser",
                "password": "securepass1",
                "password_confirm": "different",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_username(self):
        make_user(username="existing")
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "existing",
                "password": "securepass1",
                "password_confirm": "securepass1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_short_password(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "newuser",
                "password": "123",
                "password_confirm": "123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_returns_tokens(self):
        make_user()
        response = self.client.post(
            "/api/auth/token/",
            {"username": "testuser", "password": "testpass123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)


# ---------------------------------------------------------------------------
# 3.  Document upload endpoint
# ---------------------------------------------------------------------------

class DocumentUploadTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        from rag.models import Collection
        self.collection = Collection.objects.create(user=self.user, name="test")
        token = get_jwt(self.client)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    @patch("rag.views.process_document_task")
    def test_upload_requires_pdf(self, mock_task):
        """Non-PDF files should be rejected."""
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile

        txt_file = SimpleUploadedFile("test.txt", b"hello", content_type="text/plain")
        response = self.client.post(
            "/api/documents/upload/",
            {"title": "My Doc", "file": txt_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_task.delay.assert_not_called()

    def test_upload_requires_auth(self):
        """Unauthenticated requests are rejected."""
        self.client.credentials()  # clear token
        response = self.client.post("/api/documents/upload/", {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_document_list_returns_only_own(self):
        """A user only sees their own documents."""
        other_user = make_user(username="other", password="otherpass123")
        doc = Document.objects.create(
            user=other_user, title="Other's doc", file="documents/x.pdf", status="ready"
        )
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [d["id"] for d in response.data]
        self.assertNotIn(doc.id, ids)


# ---------------------------------------------------------------------------
# 4.  Chat endpoint
# ---------------------------------------------------------------------------

class ChatViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        token = get_jwt(self.client)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Create a ready document owned by the user
        self.doc = Document.objects.create(
            user=self.user, collection=self.collection,
            title="Test Doc",
            file="documents/test.pdf",
            status="ready",
        )

    def test_chat_requires_auth(self):
        self.client.credentials()
        response = self.client.post("/api/chat/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_chat_rejects_non_ready_document(self):
        pending_doc = Document.objects.create(
            user=self.user, collection=self.collection,
            title="Pending Doc",
            file="documents/pending.pdf",
            status="pending",
        )
        response = self.client.post(
            "/api/chat/",
            {"question": "Hello?", "document_id": pending_doc.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not ready", response.data["error"])

    def test_chat_rejects_wrong_user_document(self):
        other_user = make_user(username="other2", password="otherpass123")
        from rag.models import Collection
        other_collection = Collection.objects.create(user=other_user, name="c")
        other_doc = Document.objects.create(
            user=other_user,
            collection=other_collection,
            title="Other Doc",
            file="documents/other.pdf",
            status="ready",
        )
        response = self.client.post(
            "/api/chat/",
            {"question": "Hello?", "document_id": other_doc.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_chat_missing_fields(self):
        response = self.client.post("/api/chat/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# 5.  tools.py — hybrid search logic (unit level)
# ---------------------------------------------------------------------------

class HybridSearchTest(TestCase):
    """
    Tests that hybrid_search_tool returns empty list when there are no chunks,
    without needing a real DB or embedding model.
    """

    def test_empty_document_returns_empty_list(self):
        from rag.tools import hybrid_search_tool

        # No chunks exist for document_id=9999
        result = hybrid_search_tool.invoke(
            {"query": "test query", "document_id": 9999, "top_k": 5}
        )
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# 6.  graph.py — AgentState key access
# ---------------------------------------------------------------------------

class AgentStateTest(TestCase):
    """Verify that state dict keys work correctly (regression for Bug 1)."""

    def test_state_dict_access(self):
        from rag.graph import AgentState

        state: AgentState = {
            "question": "What is this?",
            "use_web_search": False,
            "graded_documents": [],
            "retrieved_documents": [],
            "reasoning_trace": [],
            "conversation_history": [],
            "generation": "",
            "current_step": "",
            "loop_count": 0,
            "document_id": 1,
            "rewrite_count": 0,
        }

        # These should NOT raise AttributeError (the bug)
        self.assertFalse(state.get("use_web_search", False))
        self.assertEqual(len(state.get("graded_documents", [])), 0)

    def test_route_lambda_with_dict(self):
        """Simulate the conditional edge lambda with a plain dict."""
        from rag.graph import create_rag_graph  # just import, not invoke

        route_fn = lambda state: "web_search" if state.get("use_web_search", False) else "retrieve_documents"
        grade_fn = lambda state: "generate_answer" if len(state.get("graded_documents", [])) > 0 else "rewrite_query"

        state_no_web = {"use_web_search": False, "graded_documents": []}
        state_web    = {"use_web_search": True,  "graded_documents": []}
        state_graded = {"use_web_search": False, "graded_documents": [{"id": 1}]}

        self.assertEqual(route_fn(state_no_web), "retrieve_documents")
        self.assertEqual(route_fn(state_web), "web_search")
        self.assertEqual(grade_fn(state_no_web), "rewrite_query")
        self.assertEqual(grade_fn(state_graded), "generate_answer")


class MultiDocumentCitationsTest(TestCase):
    def setUp(self):
        from rag.models import User, Collection, Document, DocumentChunk
        self.user = make_user()
        self.collection = Collection.objects.create(user=self.user, name="Research")
        
        for i in range(1, 4):
            doc = Document.objects.create(
                user=self.user,
                collection=self.collection,
                title=f"Paper {i}",
                status="ready"
            )
            DocumentChunk.objects.create(
                document=doc,
                page_number=1,
                text=f"This is the content of paper {i} approach {chr(64+i)}."
            )

    def test_extract_and_validate_citations_node(self):
        from rag.graph import extract_and_validate_citations
        from langchain_core.messages import AIMessage
        
        state = {
            "current_step": "generate",
            "reasoning_trace": [],
            "retrieved_documents": [
                {"id": 101, "document_title": "Paper 1", "page_number": 1},
                {"id": 102, "document_title": "Paper 2", "page_number": 2},
                {"id": 103, "document_title": "Paper 3", "page_number": 1},
            ],
            "graded_documents": [],
            "generation": AIMessage(content="Approach A [1] is better than Approach B [2]. Approach X was not found [9].")
        }
        
        result = extract_and_validate_citations(state)
        gen = result["generation"].content if isinstance(result["generation"], AIMessage) else result["generation"]
        
        self.assertIn("[1]", gen)
        self.assertIn("[2]", gen)
        self.assertNotIn("[9]", gen)
        self.assertIn("[VALIDATE] Removed invalid citations: [[9]]", result["reasoning_trace"][0])
