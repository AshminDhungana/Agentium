"""Response validation for LLM structured outputs."""
import json
import re
from typing import Any, Dict, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError


class ResponseValidator:
    """
    Validates LLM response text against a Pydantic model.

    Handles:
    - Direct JSON strings
    - JSON inside markdown code fences (```json ... ```)
    - Strict Pydantic validation with detailed error reporting
    """

    @staticmethod
    def _extract_json(content: str) -> str:
        """Extract JSON from markdown code fences or return as-is."""
        # Try to find ```json ... ``` pattern
        fence_pattern = r'```(?:json)?\s*\n(.*?)\n```'
        matches = re.findall(fence_pattern, content, re.DOTALL)
        if matches:
            # Use the last match (most likely the intended response)
            return matches[-1].strip()

        # Try to find ``` ... ``` without language hint
        fence_pattern_generic = r'```\s*\n(.*?)\n```'
        matches = re.findall(fence_pattern_generic, content, re.DOTALL)
        if matches:
            return matches[-1].strip()

        return content.strip()

    @staticmethod
    def validate(
        model: Type[BaseModel],
        content: str,
        *,
        strict: bool = True,
    ) -> Tuple[Optional[BaseModel], Optional[Dict[str, Any]]]:
        """
        Validate content against model.

        Args:
            model: Pydantic model class to validate against
            content: Raw response text from LLM
            strict: If True, use strict validation (reject extra fields)

        Returns:
            (parsed_model_instance, None) if valid
            (None, error_dict) if invalid

        error_dict structure:
            {
                "type": "schema_validation_error",
                "message": "Response does not match expected schema",
                "details": [...],  # Pydantic ValidationError.errors()
                "raw_content": str  # original content for debugging
            }
        """
        # Extract JSON from markdown fences if present
        json_str = ResponseValidator._extract_json(content)

        try:
            # Parse and validate using Pydantic
            parsed = model.model_validate_json(json_str, strict=strict)
            return parsed, None
        except ValidationError as e:
            error_dict = {
                "type": "schema_validation_error",
                "message": "Response does not match expected schema",
                "details": e.errors(),
                "raw_content": content,  # Keep original for debugging
            }
            return None, error_dict
        except json.JSONDecodeError as e:
            error_dict = {
                "type": "schema_validation_error",
                "message": f"Invalid JSON: {str(e)}",
                "details": [{"loc": (), "msg": str(e), "type": "json_decode_error"}],
                "raw_content": content,
            }
            return None, error_dict