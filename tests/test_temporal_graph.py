import time
from graph.temporal_graph import TemporalGraph, TemporalNode, TemporalEdge


def test_active_nodes_within_window():
    g = TemporalGraph(window_seconds=60)
    g.add_node(TemporalNode(id="a", data={"name": "Alice"}))
    assert len(g.active_nodes()) == 1


def test_expired_nodes_excluded():
    g = TemporalGraph(window_seconds=1)
    g.add_node(TemporalNode(id="old", data={}, timestamp=time.time() - 10))
    assert len(g.active_nodes()) == 0
