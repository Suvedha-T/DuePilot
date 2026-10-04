from typing import List, Dict, Any
from datetime import datetime, timedelta
from models.schemas import ScheduleBlock

class CalendarTool:
    @staticmethod
    def get_upcoming_schedule() -> List[Dict[str, Any]]:
        """Provides simulated calendar timeline blocks for today."""
        now = datetime.now()
        base_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
        return [
            {"time": "09:00 - 10:30", "title": "Academic Focus Block", "type": "study"},
            {"time": "10:30 - 10:45", "title": "Protected Buffer", "type": "buffer"},
            {"time": "10:45 - 12:15", "title": "Recruitment & Practice", "type": "career"},
            {"time": "12:15 - 13:00", "title": "Lunch & Rest", "type": "break"},
            {"time": "14:00 - 15:30", "title": "Lab & Project Execution", "type": "project"},
        ]
