"""Temporal graph store for narrative state."""
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TemporalNode:
    id: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class TemporalEdge:
    source: str
    target: str
    relation: str
    timestamp: float = field(default_factory=time.time)


class TemporalGraph:
    def __init__(self, window_seconds: float = 3600.0):
        self.window_seconds = window_seconds
        self._nodes: dict[str, TemporalNode] = {}
        self._edges: list[TemporalEdge] = []

    def add_node(self, node: TemporalNode) -> None:
        self._nodes[node.id] = node

    def add_edge(self, edge: TemporalEdge) -> None:
        self._edges.append(edge)

    def active_nodes(self) -> list[TemporalNode]:
        cutoff = time.time() - self.window_seconds
        return [n for n in self._nodes.values() if n.timestamp >= cutoff]
