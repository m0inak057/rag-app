"""
Unified LLM Manager using Gemini API

Primary provider: Gemini API (with cost controls)
"""

import os
import logging
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime

from django.core.cache import cache
from django.conf import settings

from .gemini_client import GeminiLLM, CostTracker

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Available LLM providers."""
    GEMINI = "gemini"


class UnifiedLLMManager:
    """
    Unified LLM manager using Gemini API.

    Strategy:
    - Uses Gemini API for all LLM operations
    - Tracks usage and costs
    """

    def __init__(self):
        self.gemini_llm: Optional[GeminiLLM] = None
        self.current_provider: Optional[LLMProvider] = None
        self._initialize()

    def _initialize(self):
        """Initialize Gemini LLM client."""
        try:
            self.gemini_llm = GeminiLLM(
                api_key=os.getenv('GEMINI_API_KEY'),
                model=settings.GEMINI_MODEL,
            )
            logger.info("✅ Gemini API initialized")
        except Exception as e:
            logger.warning(f"⚠️ Gemini initialization failed: {str(e)}")
            self.gemini_llm = None
    
    def generate(self, prompt: str, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate response exclusively using Gemini API.
        """
        if self.gemini_llm:
            try:
                response_text = self.gemini_llm.generate(prompt, max_tokens)
                self.current_provider = LLMProvider.GEMINI
                
                logger.info(f"✅ Using Gemini API")
                return {
                    'text': response_text,
                    'provider': LLMProvider.GEMINI,
                    'tokens_used': None,
                    'cost': None,
                    'switched': False,
                }
            except Exception as e:
                logger.error(f"❌ Gemini error: {str(e)}")
                raise Exception(f"Gemini API failed: {str(e)}")
                
        raise Exception("Gemini API is not configured. Please set GEMINI_API_KEY.")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of Gemini provider."""
        status = {
            'primary_provider': 'Gemini API',
            'current_provider': self.current_provider.value if self.current_provider else None,
            'gemini_available': self.gemini_llm is not None,
        }

        # Add Gemini usage stats if available
        if self.gemini_llm:
            try:
                stats = self.gemini_llm.get_usage_stats()
                status['gemini_stats'] = stats
            except Exception as e:
                logger.warning(f"Failed to get Gemini stats: {str(e)}")

        return status
    
    def get_daily_summary(self) -> Dict[str, Any]:
        """
        Get daily usage summary.
        Shows Gemini API cost tracking.
        """
        today = datetime.now().strftime('%Y-%m-%d')

        summary = {
            'date': today,
            'gemini_used_today': False,
            'gemini_cost': 0.0,
            'total_cost': 0.0,
        }

        # Check Gemini usage
        if self.gemini_llm:
            daily_cost_data = CostTracker.get_daily_cost()
            if daily_cost_data['requests'] > 0:
                summary['gemini_used_today'] = True
                summary['gemini_cost'] = daily_cost_data['total_cost']
                summary['total_cost'] += daily_cost_data['total_cost']

        return summary


# Global instance
_unified_llm_manager: Optional[UnifiedLLMManager] = None


def get_unified_llm() -> UnifiedLLMManager:
    """Get or create the unified LLM manager (singleton)."""
    global _unified_llm_manager
    
    if _unified_llm_manager is None:
        _unified_llm_manager = UnifiedLLMManager()
    
    return _unified_llm_manager


def setup_unified_llm():
    """Initialize the unified LLM manager."""
    manager = get_unified_llm()
    return manager.get_status()
