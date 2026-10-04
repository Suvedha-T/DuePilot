# ✈️ DuePilot

### Navigate what matters next.

DuePilot is an **Agentic AI responsibility-intelligence system** for college students. It transforms fragmented information into a living model of responsibilities, dependencies, deadlines, workload and personal working preferences, then continuously reasons about what the student should do next.

> **Don't just track what's due. Navigate what matters next.**

## Why DuePilot?

Students receive assignments, placement updates, project requests, club work and administrative deadlines across fragmented channels. The difficult part is not remembering every deadline—it is understanding what each message means, how responsibilities interact, what is blocked, what has the highest consequence, and how a new event changes the optimal plan.

DuePilot addresses this with a **Responsibility Graph** and an agentic loop:

**Observe → Understand → Update State → Reason → Prioritize → Plan → Replan → Human Approval**

## Core features

- AI-powered information-to-responsibility extraction
- Responsibility Graph with dependencies and blockers
- Explainable priority scoring
- Personalized working preferences
- Dynamic replanning after schedule changes
- Workload/conflict detection
- Human-in-the-loop communication drafts
- Agent activity/audit timeline
- Deterministic Demo Mode for reliable judging
- Streamlit web application

## Agent workflow

1. **Ingestion Agent** — extracts actionable information from unstructured input.
2. **Context Agent** — connects new information to existing responsibilities.
3. **Reasoning Agent** — evaluates urgency, consequence, effort, dependencies and preferences.
4. **Planning Agent** — creates the execution route.
5. **Replanning Agent** — recomputes the route when the world changes.
6. **Execution Agent** — prepares safe actions while keeping consequential actions under human approval.

## Tech stack

- Streamlit
- Python
- Gemini API
- Google ADK
- SQLite
- NetworkX
- Plotly
- GitHub
- Streamlit Community Cloud

## Run locally

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file from `.env.example` and add your Gemini key if available:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Run:

```bash
streamlit run app.py
```

**Demo Mode works without Gemini** using the deterministic fallback/demo scenarios.

## Flagship demo

1. Start on **Command Center**.
2. Keep **Deadline Shock** selected.
3. Show the initial priority route.
4. Click **Simulate Deadline Shock**.
5. Explain that the placement test moved from Friday to tomorrow.
6. Show the **Before → Event → After** rank changes.
7. Open **Why This?** to explain the new priority.
8. Open **Responsibility Map** to show the graph.
9. Load **Dependency Blocked** to demonstrate human-approved blocker resolution.

## Streamlit Community Cloud deployment

1. Push this repository to GitHub.
2. Open Streamlit Community Cloud.
3. Select the repository, branch and `app.py` as the main file.
4. Add `GEMINI_API_KEY` under app Secrets if using Gemini.
5. Deploy.

No separate frontend server, backend server or Docker container is required.

## Privacy and safety

- Secrets are environment variables / Streamlit Secrets.
- Demo data is fictional.
- Consequential external actions are not sent automatically.
- Communication actions require human approval.
- LLM outputs are validated before structured state updates.

## Project structure

```text
DuePilot/
├── app.py
├── agents/
├── core/
├── database/
├── models/
├── prompts/
├── tools/
├── data/
├── requirements.txt
├── .env.example
└── README.md
```
