"""FastMCP server for animation data inspection and editing."""

from __future__ import annotations

import hashlib
import importlib.resources
import json

from mcp.server.fastmcp import FastMCP

from unreal_animation_mcp.config import UE_PROJECT_PATH
from unreal_animation_mcp.editor_bridge import EditorBridge, EditorNotRunning

mcp = FastMCP(
    "unreal-animation",
    instructions=(
        "Animation data inspector for Unreal Engine. "
        "Inspect, search, and edit animation sequences, montages, blend spaces, "
        "animation blueprints, skeletons, and skeletal meshes."
    ),
)

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_bridge: EditorBridge | None = None
_project_path: str = UE_PROJECT_PATH
_helper_uploaded: bool = False
_helper_hash: str = ""


def _reset_state() -> None:
    """Reset module singletons (used by tests)."""
    global _bridge, _helper_uploaded, _helper_hash, _project_path
    _bridge = None
    _helper_uploaded = False
    _helper_hash = ""
    _project_path = UE_PROJECT_PATH


def _get_bridge() -> EditorBridge:
    """Return (and lazily create) the editor bridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = EditorBridge(auto_connect=False)
    return _bridge


# ---------------------------------------------------------------------------
# Helper upload
# ---------------------------------------------------------------------------

def _get_helper_source() -> str:
    """Read the helpers/animation_helpers.py source from installed package."""
    ref = importlib.resources.files("unreal_animation_mcp") / "helpers" / "animation_helpers.py"
    return ref.read_text(encoding="utf-8")


def _escape_py_string(s: str) -> str:
    """Escape a string for safe embedding inside a Python string literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')


def _ensure_helper_uploaded() -> None:
    """Upload the helper module to {project}/Saved/AnimationMCP/ if needed."""
    global _helper_uploaded, _helper_hash

    if _helper_uploaded:
        return

    source = _get_helper_source()
    new_hash = hashlib.md5(source.encode("utf-8")).hexdigest()

    if new_hash == _helper_hash:
        _helper_uploaded = True
        return

    saved_dir = _project_path.replace("\\", "/") + "/Saved/AnimationMCP"
    escaped_source = _escape_py_string(source)

    upload_script = (
        "import os\n"
        f"d = '{saved_dir}'\n"
        "os.makedirs(d, exist_ok=True)\n"
        f"p = os.path.join(d, 'animation_helpers.py')\n"
        f'f = open(p, "w", encoding="utf-8")\n'
        f"f.write('''{escaped_source}''')\n"
        "f.close()\n"
        "print('helper_uploaded')\n"
    )

    bridge = _get_bridge()
    bridge.run_command(upload_script)

    _helper_hash = new_hash
    _helper_uploaded = True


# ---------------------------------------------------------------------------
# Script execution
# ---------------------------------------------------------------------------

def _run_animation_script(script_body: str) -> dict:
    """Upload helper (if needed), run script_body in editor, parse JSON output."""
    _ensure_helper_uploaded()

    saved_dir = _project_path.replace("\\", "/") + "/Saved/AnimationMCP"

    preamble = (
        "import sys, json\n"
        f"sys.path.insert(0, '{saved_dir}')\n"
        "import importlib, animation_helpers\n"
        "importlib.reload(animation_helpers)\n"
    )

    full_script = preamble + script_body
    bridge = _get_bridge()
    result = bridge.run_command(full_script)

    output = result.get("output", "") or result.get("result", "") or ""

    if isinstance(output, list):
        parts = []
        for item in output:
            if isinstance(item, dict):
                parts.append(item.get("output", str(item)))
            else:
                parts.append(str(item))
        output = "\n".join(parts)

    output = str(output).strip()

    json_start = output.find("{")
    if json_start == -1:
        return {"success": False, "error": f"No JSON in output: {output[:200]}"}

    try:
        return json.loads(output[json_start:])
    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"Invalid JSON: {exc} — raw: {output[:200]}"}


def _parse_plugin_result(raw: dict) -> dict:
    """Parse JSON result from a C++ plugin call via bridge."""
    output = raw.get("output", "") or raw.get("result", "") or ""
    if isinstance(output, list):
        output = "\n".join(
            item.get("output", str(item)) if isinstance(item, dict) else str(item)
            for item in output
        )
    output = str(output).strip()
    json_start = output.find("{")
    if json_start == -1:
        return {"success": False, "error": f"No JSON in output: {output[:200]}"}
    try:
        return json.loads(output[json_start:])
    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"Invalid JSON: {exc}"}


def _format_error(data: dict) -> str | None:
    """If data indicates an error, return the message; otherwise None."""
    if data.get("success") is False:
        return data.get("error", "Unknown error")
    return None


# ---------------------------------------------------------------------------
# Tools will be added in subsequent tasks
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server."""
    mcp.run()
