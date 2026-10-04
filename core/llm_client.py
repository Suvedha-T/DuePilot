import os
import json
import logging
from typing import Optional, Dict, Any, Type, Tuple
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("duepilot.llm")

# Model configuration
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        # Try streamlit secrets if available
        if not self.api_key:
            try:
                import streamlit as st
                if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
                    self.api_key = st.secrets["GEMINI_API_KEY"]
            except Exception:
                pass

        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self._client = None
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize google.genai Client: {e}")
                self._client = None

    def is_available(self) -> bool:
        return bool(self._client and self.api_key)

    def generate_json(
        self,
        prompt: str,
        schema_class: Type[BaseModel]
    ) -> Tuple[Optional[BaseModel], Optional[str]]:
        from core.verification import OutputVerifier

        if not self.is_available():
            return None, "Gemini API key not configured or client unavailable."

        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config
            )

            raw_text = response.text or ""
            validated, err = OutputVerifier.parse_and_validate(raw_text, schema_class)
            if validated:
                return validated, None

            # Retry once with repair prompt
            repair_prompt = f"The previous output had a JSON schema error: {err}.\nPlease fix and return ONLY valid JSON matching this schema:\nPrompt:\n{prompt}\nPrevious Output:\n{raw_text}"
            retry_resp = self._client.models.generate_content(
                model=self.model,
                contents=repair_prompt,
                config=config
            )
            retry_text = retry_resp.text or ""
            val_retry, retry_err = OutputVerifier.parse_and_validate(retry_text, schema_class)
            if val_retry:
                return val_retry, None

            return None, f"Validation failed after retry: {retry_err}"
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return None, str(e)
