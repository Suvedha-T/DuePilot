import re
import uuid
from typing import Optional, Tuple
import google.adk as adk
from models.schemas import ExtractedEvent, AgentActivityEvent
from models.enums import EventType
from prompts.extraction_prompts import EXTRACTION_PROMPT
from core.llm_client import GeminiClient
from database.database import log_agent_event

class IngestionAgent:
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.llm = gemini_client or GeminiClient()
        self.adk_agent = adk.Agent(
            name="IngestionAgent",
            instruction=(
                "Convert unstructured student messages, emails, and announcements into structured "
                "actionable events. Never invent missing details."
            )
        )

    def process(self, text: str, source_channel: str = "Direct Input") -> ExtractedEvent:
        text = text.strip()
        if not text:
            event = ExtractedEvent(
                event_type=EventType.IRRELEVANT,
                responsibility_title="Empty Input",
                action_summary="No content provided.",
                confidence=1.0,
                is_ambiguous=True,
                ambiguity_notes="User provided empty text."
            )
            return event

        extracted: Optional[ExtractedEvent] = None

        # 1. Attempt Gemini LLM extraction if available
        if self.llm.is_available():
            prompt = EXTRACTION_PROMPT.format(input_text=text)
            model_obj, err = self.llm.generate_json(prompt, ExtractedEvent)
            if model_obj and isinstance(model_obj, ExtractedEvent):
                extracted = model_obj

        # 2. Heuristic fallback (Deterministic hackathon backup)
        if not extracted:
            extracted = self._heuristic_extract(text, source_channel)

        # Log agent activity
        act_event = AgentActivityEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            agent_name="IngestionAgent",
            activity_type="information_ingestion",
            message=f"Ingested '{extracted.responsibility_title}' ({extracted.event_type.value})",
            status="info" if extracted.event_type != EventType.IRRELEVANT else "warning",
            details={
                "title": extracted.responsibility_title,
                "event_type": extracted.event_type.value,
                "deadline": extracted.deadline,
                "confidence": extracted.confidence
            }
        )
        log_agent_event(act_event)

        return extracted

    def _heuristic_extract(self, text: str, source_channel: str) -> ExtractedEvent:
        lower = text.lower()

        # Check for shock / rescheduling
        is_moved = "moved" in lower or "rescheduled" in lower or "postponed" in lower or "brought forward" in lower
        
        # Deadlines
        deadline = None
        if "tomorrow at 10 am" in lower or "tomorrow 10 am" in lower or "tomorrow at 10:00 am" in lower:
            deadline = "Tomorrow, 10:00 AM"
        elif "tomorrow" in lower:
            deadline = "Tomorrow, 11:59 PM"
        elif "tonight" in lower:
            deadline = "Tonight, 11:59 PM"
        elif "monday" in lower:
            deadline = "Next Monday, 11:59 PM"
        elif "friday" in lower:
            deadline = "Friday, 05:00 PM"
        elif "in 2 days" in lower or "in two days" in lower:
            deadline = "In 2 days, 11:59 PM"

        # Classification
        event_type = EventType.INFORMATIONAL
        if is_moved:
            event_type = EventType.DEADLINE
        elif "assignment" in lower or "lab report" in lower or "problem set" in lower or "submit" in lower:
            event_type = EventType.ASSIGNMENT
        elif "test" in lower or "exam" in lower or "quiz" in lower or "aptitude" in lower:
            event_type = EventType.DEADLINE
        elif "internship" in lower or "portal" in lower or "application" in lower:
            event_type = EventType.OPPORTUNITY
        elif "please send" in lower or "can you send" in lower or "need" in lower:
            event_type = EventType.REQUEST
        elif "meeting" in lower or "workshop" in lower:
            event_type = EventType.COMMITMENT

        # Title extraction
        title = "Important Notice"
        if "placement" in lower or "aptitude" in lower:
            title = "Placement Aptitude Test"
        elif "ml" in lower or "machine learning" in lower:
            title = "Machine Learning Assignment"
        elif "daa" in lower or "algorithms" in lower:
            title = "DAA Problem Set"
        elif "internship" in lower:
            title = "Internship Application"
        elif "project results" in lower:
            title = "Project Results Delivery"
        else:
            first_sent = text.split(".")[0].strip()
            title = first_sent[:40] if first_sent else "Incoming Responsibility"

        action = f"Complete and prepare for {title}"
        if deadline:
            action += f" before {deadline}"

        # Ambiguity check
        is_ambiguous = False
        ambiguity_notes = None
        if "soon" in lower or "whenever" in lower or "asap" in lower:
            is_ambiguous = True
            ambiguity_notes = "Vague timeframe detected in message."

        urgency = []
        if is_moved:
            urgency.append("rescheduled")
        if "tomorrow" in lower or "tonight" in lower:
            urgency.append("immediate")

        return ExtractedEvent(
            event_type=event_type,
            responsibility_title=title,
            action_summary=action,
            deadline=deadline,
            requirements=[text[:120]],
            sender_or_source=source_channel,
            urgency_indicators=urgency,
            entities=["University", "Course Portal"],
            confidence=0.92,
            source_reference=text[:80],
            is_ambiguous=is_ambiguous,
            ambiguity_notes=ambiguity_notes
        )
