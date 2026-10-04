from typing import Dict, Any, List
import json
import os

SCENARIO_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "demo_scenarios.json")

def get_available_demo_scenarios() -> Dict[str, str]:
    with open(SCENARIO_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: v["name"] for k, v in data["scenarios"].items()}

def get_demo_scenario_details(scenario_key: str) -> Dict[str, Any]:
    with open(SCENARIO_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["scenarios"].get(scenario_key, {})
