import json
import re
from typing import Dict, Any, Optional, Type, Tuple
from pydantic import BaseModel, ValidationError

class OutputVerifier:
    @staticmethod
    def extract_json_block(text: str) -> str:
        """Extracts JSON substring if wrapped in markdown backticks or loose text."""
        text = text.strip()
        # Look for ```json ... ```
        pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
        
        # If text begins with { and ends with }, return as is
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return text[first_brace:last_brace+1].strip()
            
        first_bracket = text.find("[")
        last_bracket = text.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            return text[first_bracket:last_bracket+1].strip()

        return text

    @classmethod
    def parse_and_validate(cls, raw_output: str, schema_class: Type[BaseModel]) -> Tuple[Optional[BaseModel], Optional[str]]:
        clean_text = cls.extract_json_block(raw_output)
        try:
            data = json.loads(clean_text)
            validated = schema_class.model_validate(data)
            return validated, None
        except json.JSONDecodeError as jde:
            # Attempt basic repair: fix trailing commas, unquoted keys
            repaired = cls._basic_json_repair(clean_text)
            try:
                data = json.loads(repaired)
                validated = schema_class.model_validate(data)
                return validated, None
            except Exception as e:
                return None, f"JSON decode failed: {str(jde)}"
        except ValidationError as ve:
            return None, f"Schema validation error: {str(ve)}"
        except Exception as e:
            return None, f"Unexpected validation error: {str(e)}"

    @staticmethod
    def _basic_json_repair(s: str) -> str:
        # Remove trailing commas before closing braces/brackets
        s = re.sub(r',\s*([}\]])', r'\1', s)
        return s
