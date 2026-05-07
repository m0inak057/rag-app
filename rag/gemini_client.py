"""
Gemini API wrapper with cost controls, rate limiting, and security.
Prevents API key leakage and excessive usage.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from functools import wraps
import time
import threading

import google.generativeai as genai
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter to prevent API key abuse.
    Tracks requests per minute and daily usage.
    """
    
    def __init__(self, requests_per_minute: int = 60, daily_limit: int = 1000):
        self.requests_per_minute = requests_per_minute
        self.daily_limit = daily_limit
        self.lock = threading.Lock()
    
    def is_allowed(self, key: str = "gemini_global") -> bool:
        """
        Check if a request is allowed based on rate limits.
        """
        with self.lock:
            # Check per-minute limit
            minute_key = f"rate_limit:minute:{key}:{datetime.now().strftime('%Y%m%d%H%M')}"
            minute_count = cache.get(minute_key, 0)
            
            if minute_count >= self.requests_per_minute:
                logger.warning(f"Rate limit exceeded (per minute) for {key}")
                return False
            
            cache.set(minute_key, minute_count + 1, 60)  # Expire after 60 seconds
            
            # Check daily limit
            day_key = f"rate_limit:daily:{key}:{datetime.now().strftime('%Y%m%d')}"
            day_count = cache.get(day_key, 0)
            
            if day_count >= self.daily_limit:
                logger.warning(f"Rate limit exceeded (daily) for {key}")
                return False
            
            cache.set(day_key, day_count + 1, 86400)  # Expire after 24 hours
            
            return True
    
    def get_remaining_requests(self, key: str = "gemini_global") -> dict:
        """Get remaining requests for the day."""
        day_key = f"rate_limit:daily:{key}:{datetime.now().strftime('%Y%m%d')}"
        day_count = cache.get(day_key, 0)
        
        return {
            'used_today': day_count,
            'remaining_today': max(0, self.daily_limit - day_count),
            'max_daily': self.daily_limit,
        }


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
        self.rate_limiter = RateLimiter(
            requests_per_minute=settings.GEMINI_RPM,
            daily_limit=settings.GEMINI_DAILY_LIMIT,
        )
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        # Configure Gemini
        genai.configure(api_key=self.api_key)
    
    def generate(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """
        Generate text with Gemini with cost controls.
        """
        # Rate limits disabled per request
        # if not self.rate_limiter.is_allowed():
        #     raise Exception("Rate limit exceeded. Try again later.")
        
        try:
            # Use safe default max tokens
            output_tokens = min(
                max_tokens or self.MODELS[self.model]['max_tokens'],
                self.MODELS[self.model]['max_tokens']
            )
            
            model_instance = genai.GenerativeModel(self.model)
            
            response = model_instance.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=output_tokens,
                    temperature=0.7,
                    top_p=0.95,
                    top_k=40,
                ),
                safety_settings=[
                    {
                        "category": genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        "threshold": genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                    },
                    {
                        "category": genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        "threshold": genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                    },
                    {
                        "category": genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        "threshold": genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                    },
                    {
                        "category": genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        "threshold": genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                    },
                ],
            )
            
            # Log usage
            usage = response.usage_metadata
            CostTracker.log_usage(
                prompt_tokens=usage.prompt_character_count // 4,  # Rough estimate
                completion_tokens=usage.candidates_token_count,
                model=self.model,
            )
            
            return response.text
        
        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            raise
    
    def get_usage_stats(self) -> dict:
        """Get current usage statistics."""
        daily_cost = CostTracker.get_daily_cost()
        remaining = self.rate_limiter.get_remaining_requests()
        
        return {
            'daily_cost': daily_cost,
            'remaining_requests_today': remaining['remaining_today'],
            'max_daily_requests': remaining['max_daily'],
        }


# Initialize global Gemini instance
gemini_llm: Optional[GeminiLLM] = None


def get_gemini_llm() -> GeminiLLM:
    """Get or create the Gemini LLM instance (singleton)."""
    global gemini_llm
    
    if gemini_llm is None:
        gemini_llm = GeminiLLM(model=settings.GEMINI_MODEL)
    
    return gemini_llm


def rate_limit_endpoint(func):
    """
    Decorator to add rate limiting to API endpoints.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        llm = get_gemini_llm()
        
        if not llm.rate_limiter.is_allowed():
            from rest_framework.response import Response
            from rest_framework import status
            return Response(
                {
                    "error": "Rate limit exceeded. Please try again later.",
                    "usage": llm.get_usage_stats(),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        
        return func(*args, **kwargs)
    
    return wrapper
