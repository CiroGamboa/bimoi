"""
XState-compatible state machine using xstate-python.

Loads standard XState JSON (id, initial, states with on: { EVENT: target })
and uses the library for transitions. Same JSON can be used in Stately Studio
or JS XState. We do not use SCXML (Js2Py is only required for that).
"""

import json
from pathlib import Path

from xstate.machine import Machine


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def get_machine_path() -> Path:
    default = _repo_root() / "flows" / "telegram_machine.json"
    import os

    path = os.environ.get("XSTATE_MACHINE_PATH", "").strip()
    if path:
        return Path(path).resolve()
    return default


def load_machine(path: Path | None = None) -> dict:
    if path is None:
        path = get_machine_path()
    raw = path.read_text(encoding="utf-8")
    config = json.loads(raw)
    if "initial" not in config or "states" not in config:
        raise ValueError("Machine must have 'initial' and 'states'")
    return config


def _machine_instance(config: dict) -> Machine:
    """Return a Machine instance for this config. Cached per config id."""
    cache: dict[int, Machine] = getattr(_machine_instance, "_cache", {})
    key = id(config)
    if key not in cache:
        cache[key] = Machine(config)
        _machine_instance._cache = cache
    return cache[key]


def transition(machine: dict, state_value: str, event: str) -> str | None:
    """
    Return next state value for (state_value, event), or None if no transition.
    Uses xstate-python for full XState semantics.
    """
    try:
        instance = _machine_instance(machine)
        state = instance.state_from(state_value)
        next_state = instance.transition(state, event)
        if next_state.value == state_value:
            return None
        return next_state.value
    except (ValueError, KeyError):
        return None


# Module-level cache for config dict (for get_machine)
_machine_cache: dict | None = None


def get_machine(cache: bool = True) -> dict:
    global _machine_cache
    if cache and _machine_cache is not None:
        return _machine_cache
    _machine_cache = load_machine()
    return _machine_cache
