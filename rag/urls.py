from django.urls import path
from . import views

urlpatterns = [
    # ── Collection Endpoints ──
    path('collections/', views.CollectionListCreateView.as_view(), name='collection-list-create'),
    path('collections/<int:pk>/', views.CollectionDetailView.as_view(), name='collection-detail'),

    # ── Document Endpoints ──
    path('documents/', views.DocumentListView.as_view(), name='document-list'),
    path('documents/upload/', views.DocumentUploadView.as_view(), name='document-upload'),

    # ── Chat Endpoints ──
    path('chat/', views.ChatView.as_view(), name='chat'),
    path('conversations/', views.ConversationListView.as_view(), name='conversation-list'),
    path('conversations/<int:pk>/', views.ConversationDetailView.as_view(), name='conversation-detail'),
    
    # ── Usage & Stats Endpoints ──
    path('usage-stats/', views.UsageStatsView.as_view(), name='usage-stats'),
    path('llm-provider-status/', views.LLMProviderStatusView.as_view(), name='llm-provider-status'),
]
