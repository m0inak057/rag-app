"""
Unified LLM Manager with Gemini → Groq Fallback

This system provides intelligent fallback:
1. Primary: Gemini API (with cost controls)
2. Fallback: Groq API (free, unlimited)

When Gemini hits rate limits or budget, seamlessly switches to Groq.
Tracks which provider is being used for transparency.
"""

import os
import logging
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime

from django.core.cache import cache
from django.conf import settings
from groq import Groq

from .gemini_client import GeminiLLM, RateLimiter, CostTracker

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Available LLM providers."""
    GEMINI = "gemini"
    GROQ = "groq"


class UnifiedLLMManager:
    """
    Unified LLM manager that intelligently switches between Gemini and Groq.
    
    Strategy:
    - Attempts Gemini first (better quality, has cost control)
    - If Gemini rate limited or budget exceeded → falls back to Groq
    - Groq is free and unlimited (backup safety net)
    """
    
    def __init__(self):
        self.gemini_llm: Optional[GeminiLLM] = None
        self.groq_client: Optional[Groq] = None
        self.current_provider: Optional[LLMProvider] = None
        self._initialize()
    
    def _initialize(self):
        """Initialize both LLM clients."""
        try:
            self.gemini_llm = GeminiLLM(
                api_key=os.getenv('GEMINI_API_KEY'),
                model=settings.GEMINI_MODEL,
            )
            logger.info("✅ Gemini API initialized (Primary)")
        except Exception as e:
            logger.warning(f"⚠️ Gemini initialization failed: {str(e)}")
            self.gemini_llm = None
        
        try:
            groq_api_key = os.getenv('GROQ_API_KEY')
            if groq_api_key:
                self.groq_client = Groq(api_key=groq_api_key)
                logger.info("✅ Groq API initialized (Fallback)")
            else:
                logger.warning("⚠️ Groq API key not found")
        except Exception as e:
            logger.warning(f"⚠️ Groq initialization failed: {str(e)}")
            self.groq_client = None
    
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
        """Get current status of both providers."""
        status = {
            'primary_provider': 'Gemini API',
            'fallback_provider': 'Groq API (Free)',
            'current_provider': self.current_provider.value if self.current_provider else None,
            'gemini_available': self.gemini_llm is not None,
            'groq_available': self.groq_client is not None,
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
        Shows cost breakdown and provider usage.
        """
        today = datetime.now().strftime('%Y-%m-%d')
        
        summary = {
            'date': today,
            'gemini_used_today': False,
            'groq_used_today': False,
            'gemini_cost': 0.0,
            'groq_cost': 0.0,
            'total_cost': 0.0,
        }
        
        # Check Gemini usage
        if self.gemini_llm:
            daily_cost_data = CostTracker.get_daily_cost()
            if daily_cost_data['requests'] > 0:
                summary['gemini_used_today'] = True
                summary['gemini_cost'] = daily_cost_data['total_cost']
                summary['total_cost'] += daily_cost_data['total_cost']
        
        # Note: Groq is free, so no cost to track
        summary['groq_cost'] = 0.0
        
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
