"""Load and validate YAML flow definition. Used by flow_runner."""

import os
from pathlib import Path

import yaml


def _repo_root() -> Path:
    """Return repo root (parent of src)."""
    return Path(__file__).resolve().parent.parent.parent


def get_flow_path() -> Path:
    """Return path to the Telegram flow YAML (FLOW_PATH env or flows/telegram.yaml)."""
    default = _repo_root() / "flows" / "telegram.yaml"
    path = os.environ.get("FLOW_PATH", "").strip()
    if path:
        return Path(path).resolve()
    return default


def load_flow(path: Path | None = None) -> dict:
    """Load flow YAML and return the flow dict. Validates minimal structure."""
    if path is None:
        path = get_flow_path()
    raw = path.read_text(encoding="utf-8")
    flow = yaml.safe_load(raw)
    if not isinstance(flow, dict):
        raise ValueError("Flow YAML must be a dict")
    if "nodes" not in flow or not flow["nodes"]:
        raise ValueError("Flow must have a non-empty 'nodes' list")
    if "start_node" not in flow:
        raise ValueError("Flow must have 'start_node'")
    node_ids = {n["id"] for n in flow["nodes"] if isinstance(n, dict) and "id" in n}
    if not node_ids:
        raise ValueError("Flow nodes must have 'id'")
    if flow["start_node"] not in node_ids:
        raise ValueError(f"start_node '{flow['start_node']}' must be a node id")
    for node in flow["nodes"]:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not nid:
            raise ValueError("Every node must have 'id'")
        for edge in node.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            next_id = edge.get("next")
            if next_id and next_id not in node_ids:
                raise ValueError(
                    f"Node '{nid}' edge references unknown node '{next_id}'"
                )
    if "messages" not in flow:
        flow["messages"] = {}
    return flow


# Module-level cache for loaded flow
_flow_cache: dict | None = None


def get_flow(cache: bool = True) -> dict:
    """Load flow (cached by default). Pass cache=False to reload."""
    global _flow_cache
    if cache and _flow_cache is not None:
        return _flow_cache
    _flow_cache = load_flow()
    return _flow_cache
