"""
AI validation service for healthcare claims.

This service is responsible for:
- Calling the LLM with structured output
- Validating responses against strict schema
- Handling failures gracefully
- Never crashing the request

Key principles:
- AI is advisory only
- Fail safely with manual review fallback
- No hallucination passes validation
- All decisions are traceable
"""
import json
import logging
from typing import Dict, Any, Optional
from openai import OpenAI

from app.models.ai_validation_models import (
    AIValidationResult,
    SAFE_FALLBACK_RESPONSE,
)
from app.services.validation.prompt import build_validation_prompt, get_prompt_version
from app.utils.hashing import hash_ai_validation_input

# Re-export for backward compatibility
compute_input_hash = hash_ai_validation_input


# Setup logging
logger = logging.getLogger(__name__)


class AIValidationService:
    """
    Service for AI-powered claim validation.
    
    This is a separate service to keep AI logic out of API routes.
    All LLM interaction happens here, with strict schema enforcement.
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gpt-4o-mini"):
        """
        Initialize the AI validation service.
        
        Args:
            api_key: OpenAI API key (if None, will use env var)
            model_name: Name of the model to use
        """
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key) if api_key else OpenAI()
        self.max_retries = 2
        self.timeout = 30  # seconds
    
    def validate_claim(
        self, 
        claim_data: Dict[str, Any], 
        deterministic_result: Dict[str, Any]
    ) -> AIValidationResult:
        """
        Run AI validation on a claim.
        
        This is the main entry point. It:
        1. Builds the prompt
        2. Calls the LLM with retries
        3. Validates the response
        4. Returns structured result or safe fallback
        
        Args:
            claim_data: The claim input data
            deterministic_result: Results from deterministic validation
            
        Returns:
            AIValidationResult (either from AI or safe fallback)
        """
        logger.info(f"Starting AI validation with model {self.model_name}")
        
        try:
            # Build the prompt
            prompt = build_validation_prompt(claim_data, deterministic_result)
            
            # Call LLM with retries
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"AI validation attempt {attempt + 1}/{self.max_retries}")
                    result = self._call_llm(prompt)
                    
                    # If we got a valid result, return it
                    if result:
                        logger.info(f"AI validation succeeded: status={result.status}, confidence={result.confidence}")
                        return result
                        
                except Exception as e:
                    logger.warning(f"AI validation attempt {attempt + 1} failed: {str(e)}")
                    if attempt == self.max_retries - 1:
                        # Last attempt failed, will fall through to safe fallback
                        logger.error("All AI validation attempts exhausted")
            
            # If we get here, all retries failed
            logger.error("AI validation failed after all retries, returning safe fallback")
            return SAFE_FALLBACK_RESPONSE
            
        except Exception as e:
            # Unexpected error, log and return safe fallback
            logger.error(f"Unexpected error in AI validation: {str(e)}", exc_info=True)
            return SAFE_FALLBACK_RESPONSE
    
    def _call_llm(self, prompt: str) -> Optional[AIValidationResult]:
        """
        Call the LLM and parse the response.
        
        Uses OpenAI's structured output feature to enforce schema.
        
        Args:
            prompt: The complete prompt
            
        Returns:
            AIValidationResult if successful, None if failed
        """
        try:
            # Call OpenAI with structured output
            # Using response_format with json_schema to enforce structure
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI assistant for healthcare claim validation. You must respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                timeout=self.timeout,
                temperature=0.3  # Low temperature for consistency
            )
            
            # Extract the response
            content = response.choices[0].message.content
            
            if not content:
                logger.error("LLM returned empty response")
                return None
            
            # Parse JSON
            try:
                response_json = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"LLM response is not valid JSON: {str(e)}")
                return None
            
            # Validate against Pydantic schema
            # This will raise ValidationError if schema doesn't match
            try:
                result = AIValidationResult(**response_json)
                return result
            except Exception as e:
                logger.error(f"LLM response failed schema validation: {str(e)}")
                logger.error(f"Response was: {response_json}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling LLM: {str(e)}")
            return None
    
    def get_model_name(self) -> str:
        """Return the model name for audit tracking"""
        return self.model_name
    
    def get_prompt_version(self) -> str:
        """Return the prompt version for audit tracking"""
        return get_prompt_version()
