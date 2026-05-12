from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
import json

from .models import Document, ChatConversation, ChatMessage, Collection
from .serializers import (
    DocumentSerializer,
    ChatQuerySerializer,
    ChatConversationSerializer,
    UserRegistrationSerializer,
    CollectionSerializer,
    CollectionDetailSerializer,
)
from .tasks import process_document_task
from .graph import AgentState
from .tools import set_embedding_model
from sentence_transformers import SentenceTransformer

# Lazy-load embedding model (only when first used)
_embedding_model = None
_rag_graph = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        set_embedding_model(_embedding_model)
    return _embedding_model

def get_rag_graph():
    global _rag_graph
    if _rag_graph is None:
        from .graph import create_rag_graph
        _rag_graph = create_rag_graph()
    return _rag_graph


class DocumentUploadView(generics.CreateAPIView):
    """
    POST /api/documents/upload/

    Upload a PDF file to a specific collection. Processing happens asynchronously.
    """
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        # The collection is validated in the serializer to belong to the user
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        document = serializer.instance

        try:
            task = process_document_task.delay(document.id)
            
            return Response(
                {
                    "message": "Document uploaded! Processing started in background.",
                    "document": serializer.data,
                    "task_id": task.id,
                    "status": "processing",
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as e:
            document.delete() # Clean up if task queuing fails
            return Response(
                {"error": f"Failed to queue document processing: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DocumentListView(generics.ListAPIView):
    """
    GET /api/documents/

    Returns all documents uploaded by the authenticated user.
    Includes their processing status.
    """
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user).order_by('-uploaded_at')


class ChatView(APIView):
    """
    POST /api/chat/

    Send a question about an uploaded document and get an AI-powered answer.
    Uses the LangGraph agentic system for sophisticated reasoning.

    Request body (JSON):
    {
        "question": "What are the key findings?",
        "document_id": 1,
        "conversation_id": null   // optional, omit to start new chat
    }

    Response (streaming):
    Streams reasoning steps and final answer in real-time using Server-Sent Events.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Handle chat queries with streaming response."""
        # 1. Validate the request
        serializer = ChatQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question = serializer.validated_data['question']
        document_id = serializer.validated_data.get('document_id')
        collection_id = serializer.validated_data.get('collection_id')
        conversation_id = serializer.validated_data.get('conversation_id')

        # 2. Check access
        document = None
        collection = None
        
        if document_id:
            try:
                document = Document.objects.get(id=document_id, user=request.user)
                if document.status != 'ready':
                    return Response(
                        {"error": f"Document is not ready. Status: {document.status}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Document.DoesNotExist:
                return Response(
                    {"error": "Document not found or you don't have access."},
                    status=status.HTTP_404_NOT_FOUND,
                )
                
        if collection_id:
            try:
                collection = Collection.objects.get(id=collection_id, user=request.user)
            except Collection.DoesNotExist:
                return Response(
                    {"error": "Collection not found or you don't have access."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # 3. Get or create conversation
        try:
            if conversation_id:
                conversation = ChatConversation.objects.get(
                    id=conversation_id,
                    user=request.user,
                )
                if document_id and conversation.document_id != document_id:
                    return Response({"error": "Conversation document mismatch."}, status=status.HTTP_400_BAD_REQUEST)
                if collection_id and conversation.collection_id != collection_id:
                    return Response({"error": "Conversation collection mismatch."}, status=status.HTTP_400_BAD_REQUEST)
            else:
                conversation, _ = ChatConversation.objects.get_or_create(
                    user=request.user,
                    document=document,
                    collection=collection,
                )
        except ChatConversation.DoesNotExist:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 4. Stream the agent's response
        return StreamingHttpResponse(
            self.stream_agent_response(
                question,
                document_id,
                collection_id,
                conversation,
                request.user,
            ),
            content_type='text/event-stream',
        )

    def stream_agent_response(self, question, document_id, collection_id, conversation, user):
        """
        Generator function that yields streaming events as the agent processes the query.
        Uses Server-Sent Events (SSE) format.
        """
        # Initialize agent state as dictionary
        state: AgentState = {
            "question": question,
            "document_id": document_id,
            "collection_id": collection_id,
            "conversation_history": [],
            "retrieved_documents": [],
            "graded_documents": [],
            "generation": "",
            "reasoning_trace": [],
            "current_step": "",
            "loop_count": 0,
            "use_web_search": False,
            "rewrite_count": 0,
            "cited_sources": [],
        }
        
        # Load conversation history (last 5 messages for context)
        history = ChatMessage.objects.filter(
            conversation=conversation
        ).order_by('-created_at')[:5]
        
        for msg in reversed(history):
            state["conversation_history"].append({
                'role': msg.role,
                'content': msg.content,
            })
        
        try:
            # Run the agentic graph
            rag_graph = get_rag_graph()
            result = rag_graph.invoke(state)

            # Yield streaming updates
            for step in result["reasoning_trace"]:
                yield f"data: {json.dumps({'type': 'reasoning', 'content': step})}\n\n"

            # Yield the final answer with cited sources
            cited_sources = result.get("cited_sources", [])
            yield f"data: {json.dumps({'type': 'answer', 'content': result['generation'], 'sources': cited_sources})}\n\n"

            # Save to database
            user_message = ChatMessage.objects.create(
                conversation=conversation,
                role='user',
                content=question,
            )

            ai_message = ChatMessage.objects.create(
                conversation=conversation,
                role='ai',
                content=result["generation"],
                reasoning_trace=result["reasoning_trace"],
                sources=cited_sources,
            )

            # Yield success
            yield f"data: {json.dumps({'type': 'complete', 'message_id': ai_message.id, 'sources': ai_message.sources})}\n\n"

        except Exception as e:
            # Yield error
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


class ConversationListView(generics.ListAPIView):
    """
    GET /api/conversations/

    Returns all conversations for the authenticated user.
    """
    serializer_class = ChatConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatConversation.objects.filter(
            user=self.request.user
        ).order_by('-created_at')


class ConversationDetailView(generics.RetrieveAPIView):
    """
    GET /api/conversations/<id>/

    Returns a specific conversation with all its messages.
    """
    serializer_class = ChatConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatConversation.objects.filter(user=self.request.user)


class UsageStatsView(APIView):
    """
    GET /api/usage-stats/
    
    Returns Gemini API usage statistics and cost tracking.
    Helps monitor API usage and prevent unexpected charges.
    Includes info about fallback to Groq if Gemini is exhausted.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        from .unified_llm import get_unified_llm
        
        try:
            llm = get_unified_llm()
            llm_status = llm.get_status()
            summary = llm.get_daily_summary()
            
            return Response(
                {
                    "status": llm_status,
                    "daily_summary": summary,
                    "message": "Gemini API: Primary provider | Groq API: Fallback (free, unlimited)",
                },
                status=status.HTTP_200_OK,
            )
        
        except Exception as e:
            return Response(
                {"error": f"Failed to retrieve usage stats: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LLMProviderStatusView(APIView):
    """
    GET /api/llm-provider-status/
    
    Shows current LLM provider and fallback information.
    Useful for debugging and understanding which API is being used.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        from .unified_llm import get_unified_llm
        
        try:
            llm = get_unified_llm()
            provider_status = llm.get_status()
            
            return Response(
                {
                    "primary_provider": provider_status['primary_provider'],
                    "fallback_provider": provider_status['fallback_provider'],
                    "current_provider": provider_status['current_provider'],
                    "gemini_available": provider_status['gemini_available'],
                    "groq_available": provider_status['groq_available'],
                    "gemini_stats": provider_status.get('gemini_stats', None),
                    "description": "Uses Gemini API for responses. If Gemini hits rate limits or budget, automatically falls back to free Groq API.",
                },
                status=status.HTTP_200_OK,
            )
        
        except Exception as e:
            return Response(
                {"error": f"Failed to retrieve provider status: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RegisterView(APIView):
    """
    POST /api/auth/register/

    Register a new user account.

    Request body (JSON):
    {
        "username": "john",
        "email": "john@example.com",      // optional
        "password": "securepass123",
        "password_confirm": "securepass123"
    }

    Response:
    {
        "message": "Account created successfully.",
        "username": "john",
        "access": "<jwt_access_token>",
        "refresh": "<jwt_refresh_token>"
    }
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Issue JWT tokens automatically so user is logged in after registering
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Account created successfully.",
                "username": user.username,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class CollectionListCreateView(generics.ListCreateAPIView):
    """
    GET: List all collections for the authenticated user.
    POST: Create a new collection for the authenticated user.
    """
    serializer_class = CollectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Collection.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CollectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve a single collection with its documents.
    PATCH: Update a collection's name or description.
    DELETE: Delete a collection and all its documents.
    """
    serializer_class = CollectionDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        return Collection.objects.filter(user=self.request.user)

