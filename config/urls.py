"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,   # POST /api/auth/token/       -> Login (get tokens)
    TokenRefreshView,      # POST /api/auth/token/refresh/ -> Refresh access token
)
from rag.views import RegisterView

class RootView(APIView):
    """Welcome endpoint with API links"""
    def get(self, request):
        return Response({
            'message': '🎯 Agentic RAG API is running!',
            'api_endpoints': {
                'documents': '/api/documents/',
                'chat': '/api/chat/',
                'usage_stats': '/api/usage-stats/',
                'provider_status': '/api/llm-provider-status/',
            },
            'auth': {
                'login': '/api/auth/token/',
                'refresh': '/api/auth/token/refresh/',
            }
        })

urlpatterns = [
    path('', RootView.as_view(), name='root'),
    path('admin/', admin.site.urls),

    # --- Authentication Endpoints ---
    # Login with username/password -> returns access + refresh tokens
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    # Use a valid refresh token -> get a new access token
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Register a new user account
    path('api/auth/register/', RegisterView.as_view(), name='register'),

    # --- RAG App Endpoints ---
    # All URLs from rag/urls.py will be prefixed with /api/
    # e.g., GET  /api/documents/
    # e.g., POST /api/documents/upload/
    path('api/', include('rag.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
# The last line makes Django serve uploaded files (PDF) during development.
