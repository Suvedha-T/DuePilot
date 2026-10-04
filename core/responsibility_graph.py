from typing import List, Dict, Any, Optional, Tuple
import networkx as nx
from models.schemas import Responsibility, DependencyEdge, SubAction
from models.enums import DependencyType, Status

class ResponsibilityGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def build(
        self,
        responsibilities: List[Responsibility],
        dependencies: List[DependencyEdge]
    ) -> nx.DiGraph:
        self.graph.clear()

        # 1. Add Responsibility nodes
        for r in responsibilities:
            score = r.priority_breakdown.total_score if r.priority_breakdown else 0.0
            node_type = "blocker" if r.is_blocked else "responsibility"
            self.graph.add_node(
                r.id,
                label=r.title,
                node_type=node_type,
                category=r.category,
                priority=score,
                status=r.status.value,
                is_blocked=r.is_blocked,
                blocker_reason=r.blocker_reason,
                deadline_str=r.deadline_str or "No deadline",
                estimated_hours=r.estimated_hours,
                description=r.description
            )

            # 2. Add SubAction nodes and edges
            for act in r.subactions:
                act_type = "blocker" if act.is_blocked else "action"
                self.graph.add_node(
                    act.id,
                    label=act.title,
                    node_type=act_type,
                    category=r.category,
                    priority=score * 0.9,
                    status=act.status.value,
                    is_blocked=act.is_blocked,
                    blocker_reason=act.blocker_reason,
                    estimated_hours=round(act.estimated_minutes / 60.0, 1),
                    description=f"Subtask of: {r.title}"
                )
                # Responsibility contains SubAction
                self.graph.add_edge(
                    r.id,
                    act.id,
                    edge_type=DependencyType.CONTAINS.value,
                    description=f"{r.title} contains {act.title}"
                )

        # 3. Add explicit dependencies
        for dep in dependencies:
            if dep.from_node in self.graph and dep.to_node in self.graph:
                self.graph.add_edge(
                    dep.from_node,
                    dep.to_node,
                    edge_type=dep.dependency_type.value,
                    description=dep.description
                )

        return self.graph

    def get_stats(self) -> Dict[str, int]:
        num_resps = sum(1 for _, d in self.graph.nodes(data=True) if d.get("node_type") in ("responsibility", "blocker") and "Subtask" not in d.get("description", ""))
        num_actions = sum(1 for _, d in self.graph.nodes(data=True) if "action" in d.get("node_type", ""))
        num_blocked = sum(1 for _, d in self.graph.nodes(data=True) if d.get("is_blocked"))
        num_deps = sum(1 for _, _, d in self.graph.edges(data=True) if d.get("edge_type") in ("depends_on", "blocked_by"))
        return {
            "responsibilities": num_resps,
            "actions": num_actions,
            "blocked": num_blocked,
            "dependencies": num_deps,
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges()
        }

    def detect_cycles(self) -> List[List[str]]:
        try:
            return list(nx.simple_cycles(self.graph))
        except Exception:
            return []

    def get_blocked_nodes(self) -> List[Dict[str, Any]]:
        blocked = []
        for n, data in self.graph.nodes(data=True):
            if data.get("is_blocked"):
                blocked.append({"id": n, **data})
        return blocked

    def to_plotly_figure(self):
        import plotly.graph_objects as go
        
        if self.graph.number_of_nodes() == 0:
            fig = go.Figure()
            fig.update_layout(
                title="Responsibility Graph (Empty)",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94a3b8")
            )
            return fig

        # Compute layout using spring_layout
        try:
            pos = nx.spring_layout(self.graph, k=0.8, iterations=50, seed=42)
        except Exception:
            pos = nx.circular_layout(self.graph)

        edge_x = []
        edge_y = []
        edge_hover = []
        
        for u, v, data in self.graph.edges(data=True):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            edge_hover.append(f"{u} -> {v} ({data.get('edge_type', 'depends_on')}): {data.get('description', '')}")

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=1.5, color='#475569'),
            hoverinfo='none',
            mode='lines'
        )

        node_x = []
        node_y = []
        node_text = []
        node_color = []
        node_size = []
        node_symbols = []

        # Color mapping by node_type
        # Responsibility: Blue/Cyan, Action: Purple, Blocker: Red/Amber, Completed: Green
        for node, data in self.graph.nodes(data=True):
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)

            ntype = data.get("node_type", "responsibility")
            is_bl = data.get("is_blocked", False)
            status = data.get("status", "pending")
            p_score = data.get("priority", 50.0)

            if is_bl:
                color = "#ef4444"  # Red for blocked
                symbol = "diamond"
                size = 28
            elif status == "completed":
                color = "#10b981"  # Green
                symbol = "circle"
                size = 20
            elif ntype == "action":
                color = "#8b5cf6"  # Purple for subactions
                symbol = "square"
                size = 18
            else:
                # Main responsibilities: colored by priority score
                if p_score >= 80:
                    color = "#f97316"  # Orange/amber for critical priority
                elif p_score >= 60:
                    color = "#3b82f6"  # Electric blue
                else:
                    color = "#06b6d4"  # Cyan
                symbol = "circle"
                size = 26

            node_color.append(color)
            node_size.append(size)
            node_symbols.append(symbol)

            label = data.get("label", node)
            desc = data.get("description", "")
            deadline = data.get("deadline_str", "")
            hrs = data.get("estimated_hours", 0)
            reason = data.get("blocker_reason", "")
            
            hover = (
                f"<b>{label}</b><br>"
                f"Type: {ntype.capitalize()}<br>"
                f"Priority: {p_score:.1f}/100<br>"
                f"Deadline: {deadline}<br>"
                f"Effort: {hrs}h<br>"
                f"Status: {status}"
            )
            if is_bl and reason:
                hover += f"<br><span style='color:#ef4444'>⚠️ Blocker: {reason}</span>"
            node_text.append(hover)

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            hoverinfo='text',
            text=[self.graph.nodes[n].get("label", n)[:18] + ("..." if len(self.graph.nodes[n].get("label", n)) > 18 else "") for n in self.graph.nodes()],
            textposition="top center",
            textfont=dict(size=10, color="#e2e8f0"),
            hovertext=node_text,
            marker=dict(
                color=node_color,
                size=node_size,
                symbol=node_symbols,
                line=dict(width=2, color='#ffffff')
            )
        )

        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                showlegend=False,
                hovermode='closest',
                margin=dict(b=20, l=20, r=20, t=30),
                paper_bgcolor="rgba(15, 23, 42, 0.6)",
                plot_bgcolor="rgba(15, 23, 42, 0.6)",
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
            )
        )
        return fig
