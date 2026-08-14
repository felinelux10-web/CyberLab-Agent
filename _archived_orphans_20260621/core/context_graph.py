import json
import os

GRAPH_PATH = os.path.expanduser("~/cyberlab_agent/runtime_graph.json")

GRAPH = {
    "nodes": {},
    "edges": []
}

def add_node(name, meta=None):
    GRAPH["nodes"][name] = meta or {}

def add_edge(frm, to, relation="depends_on"):
    GRAPH["edges"].append({
        "from": frm,
        "to": to,
        "relation": relation
    })

def save_graph():
    with open(GRAPH_PATH, "w") as f:
        json.dump(GRAPH, f, indent=2)

def load_graph():
    global GRAPH
    if os.path.exists(GRAPH_PATH):
        with open(GRAPH_PATH, "r") as f:
            GRAPH = json.load(f)
    return GRAPH

def get_graph():
    return GRAPH
