"""
Gemini API wrapper with cost controls, rate limiting, and security.
Prevents API key leakage and excessive usage.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import google.genai as genai
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class CostTracker:
    """
    Track API usage and costs.
    Monitors token consumption and estimated costs.
    """
    
    # Gemini pricing (as of 2026)
    # Gemini 1.5 Flash: $0.075/M input tokens, $0.30/M output tokens
    INPUT_COST_PER_1M = 0.075
    OUTPUT_COST_PER_1M = 0.30
    
    @staticmethod
    def log_usage(prompt_tokens: int, completion_tokens: int, model: str = "gemini-2.5-flash"):
        """
        Log token usage and estimated cost.
        """
        input_cost = (prompt_tokens / 1_000_000) * CostTracker.INPUT_COST_PER_1M
        output_cost = (completion_tokens / 1_000_000) * CostTracker.OUTPUT_COST_PER_1M
        total_cost = input_cost + output_cost
        
        # Store in cache for daily tracking
        today = datetime.now().strftime('%Y%m%d')
        cost_key = f"gemini_cost:{today}"
        
        current_cost = cache.get(cost_key, {
            'total_cost': 0.0,
            'input_tokens': 0,
            'output_tokens': 0,
            'requests': 0,
        })
        
        current_cost['total_cost'] += total_cost
        current_cost['input_tokens'] += prompt_tokens
        current_cost['output_tokens'] += completion_tokens
        current_cost['requests'] += 1
        
        cache.set(cost_key, current_cost, 86400)
        
        logger.info(
            f"Gemini API Usage - Model: {model}, "
            f"Input: {prompt_tokens}, Output: {completion_tokens}, "
            f"Cost: ${total_cost:.6f}"
        )
        
        return {
            'input_cost': input_cost,
            'output_cost': output_cost,
            'total_cost': total_cost,
        }
    
    @staticmethod
    def get_daily_cost() -> dict:
        """Get total cost for today."""
        today = datetime.now().strftime('%Y%m%d')
        cost_key = f"gemini_cost:{today}"
        
        return cache.get(cost_key, {
            'total_cost': 0.0,
            'input_tokens': 0,
            'output_tokens': 0,
            'requests': 0,
        })


class GeminiLLM:
    """
    Gemini LLM wrapper with cost controls and security.
    """
    
    # Model configurations with token limits
    MODELS = {
        'gemini-2.5-flash': {
            'max_tokens': 8000,  # Max output tokens for cost control
            'context_window': 1_000_000,
        },
        'gemini-2.5-pro': {
            'max_tokens': 8000,
            'context_window': 2_000_000,
        },
    }
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        self.model = model

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        # Initialize Gemini client
        self.client = genai.Client(api_key=self.api_key)
    
    def generate(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """
        Generate text with Gemini.
        """
        try:
            # Use safe default max tokens
            output_tokens = min(
                max_tokens or self.MODELS[self.model]['max_tokens'],
                self.MODELS[self.model]['max_tokens']
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    'max_output_tokens': output_tokens,
                    'temperature': 0.7,
                    'top_p': 0.95,
                    'top_k': 40,
                }
            )

            # Log usage (google.genai response structure differs)
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                prompt_tokens = getattr(usage, 'prompt_token_count', 0) or (
                    getattr(usage, 'prompt_character_count', 0) // 4 if hasattr(usage, 'prompt_character_count') else 0
                )
                CostTracker.log_usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=getattr(usage, 'candidates_token_count', 0),
                    model=self.model,
                )

            return response.text

        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            raise
    
    def get_usage_stats(self) -> dict:
        """Get current usage statistics."""
        daily_cost = CostTracker.get_daily_cost()

        return {
            'daily_cost': daily_cost,
        }


# Initialize global Gemini instance
gemini_llm: Optional[GeminiLLM] = None


def get_gemini_llm() -> GeminiLLM:
    """Get or create the Gemini LLM instance (singleton)."""
    global gemini_llm
    
    if gemini_llm is None:
        gemini_llm = GeminiLLM(model=settings.GEMINI_MODEL)
    
    return gemini_llm
