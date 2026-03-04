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
# Helper for running C++ plugin calls
# ---------------------------------------------------------------------------

def _run_plugin_call(script: str) -> dict:
    """Run a C++ plugin call via bridge and parse the result."""
    bridge = _get_bridge()
    raw = bridge.run_command(script)
    return _parse_plugin_result(raw)


# ===========================================================================
# Tier 1: Inspection Tools (23 tools)
# ===========================================================================

# --- AnimSequence ---

@mcp.tool()
def get_anim_sequence_info(asset_path: str) -> str:
    """Get core metadata for an AnimSequence.

    Returns length, frame count, rate scale, interpolation type, additive type,
    root motion settings, bone track names, and skeleton reference.

    Args:
        asset_path: Unreal asset path, e.g. '/Game/Animations/AS_Run'
    """
    script = (
        f"result = animation_helpers.get_anim_sequence_info("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [
        f"AnimSequence: {data.get('asset_path', asset_path)}",
        f"  Length: {data.get('length', 'N/A')}s ({data.get('num_frames', '?')} frames)",
        f"  Rate Scale: {data.get('rate_scale', 1.0)}",
        f"  Interpolation: {data.get('interpolation_type', 'N/A')}",
        f"  Additive: {data.get('additive_type', 'N/A')}",
        f"  Root Motion: {data.get('root_motion_enabled', False)} (lock: {data.get('root_motion_lock_type', 'N/A')})",
        f"  Bone Tracks: {data.get('track_count', 0)}",
    ]
    if data.get("skeleton"):
        lines.append(f"  Skeleton: {data['skeleton']}")

    return "\n".join(lines)


@mcp.tool()
def get_anim_notifies(asset_path: str) -> str:
    """Get all notifies on an animation asset.

    Args:
        asset_path: Unreal asset path to an AnimSequence or AnimMontage
    """
    script = (
        f"result = animation_helpers.get_anim_notifies("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Notifies on {asset_path}: {data.get('notify_count', 0)}"]
    if data.get("track_names"):
        lines.append(f"  Tracks: {', '.join(data['track_names'])}")
    for n in data.get("notifies", []):
        line = f"  [{n.get('index')}] {n.get('name', '?')} @ {n.get('trigger_time', '?')}s"
        if n.get("type") == "notify_state":
            line += f" (duration: {n.get('duration', '?')}s)"
        if n.get("class"):
            line += f" [{n['class']}]"
        lines.append(line)

    return "\n".join(lines)


@mcp.tool()
def get_anim_curves(asset_path: str, curve_type: str | None = None) -> str:
    """Get all curves on an animation sequence.

    Args:
        asset_path: Unreal asset path
        curve_type: Filter by type: 'float', 'vector', or 'transform'
    """
    args = [f"'{_escape_py_string(asset_path)}'"]
    if curve_type:
        args.append(f"curve_type='{_escape_py_string(curve_type)}'")
    script = f"result = animation_helpers.get_anim_curves({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Curves on {asset_path}: {data.get('curve_count', 0)}"]
    for c in data.get("curves", []):
        line = f"  {c.get('name', '?')} ({c.get('type', '?')})"
        if "key_count" in c:
            line += f" - {c['key_count']} keys"
        lines.append(line)
    return "\n".join(lines)


@mcp.tool()
def get_bone_tracks(asset_path: str, bone_name: str | None = None) -> str:
    """Get bone track names, or detailed keys for a specific bone.

    Args:
        asset_path: Unreal asset path
        bone_name: Specific bone to inspect (omit for track list)
    """
    args = [f"'{_escape_py_string(asset_path)}'"]
    if bone_name:
        args.append(f"bone_name='{_escape_py_string(bone_name)}'")
    script = f"result = animation_helpers.get_bone_tracks({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    if bone_name:
        return (
            f"Bone Track: {data.get('bone_name', bone_name)}\n"
            f"  Position keys: {data.get('position_keys', 0)}\n"
            f"  Rotation keys: {data.get('rotation_keys', 0)}\n"
            f"  Scale keys: {data.get('scale_keys', 0)}"
        )
    lines = [f"Bone Tracks ({data.get('track_count', 0)}):"]
    for t in data.get("tracks", []):
        lines.append(f"  - {t}")
    return "\n".join(lines)


@mcp.tool()
def get_bone_pose_at_time(asset_path: str, bone_names: list[str], time: float) -> str:
    """Get bone transforms at a specific time.

    Args:
        asset_path: Unreal asset path
        bone_names: List of bone names to query
        time: Time in seconds
    """
    bones_str = ", ".join(f"'{_escape_py_string(b)}'" for b in bone_names)
    script = (
        f"result = animation_helpers.get_bone_pose_at_time("
        f"'{_escape_py_string(asset_path)}', [{bones_str}], {time})\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Bone Poses at {data.get('time', time)}s:"]
    for p in data.get("poses", []):
        loc = p.get("location", {})
        rot = p.get("rotation", {})
        lines.append(f"  {p.get('bone', '?')}:")
        lines.append(f"    Loc: ({loc.get('x', 0):.2f}, {loc.get('y', 0):.2f}, {loc.get('z', 0):.2f})")
        lines.append(f"    Rot: (P={rot.get('pitch', 0):.2f}, Y={rot.get('yaw', 0):.2f}, R={rot.get('roll', 0):.2f})")
    return "\n".join(lines)


@mcp.tool()
def get_sync_markers(asset_path: str) -> str:
    """Get sync markers on an animation sequence.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        f"result = animation_helpers.get_sync_markers("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Sync Markers: {data.get('marker_count', 0)}"]
    if data.get("unique_names"):
        lines.append(f"  Unique: {', '.join(data['unique_names'])}")
    for m in data.get("markers", []):
        lines.append(f"  {m.get('name', '?')} @ {m.get('time', '?')}s")
    return "\n".join(lines)


# --- AnimMontage ---

@mcp.tool()
def get_montage_info(asset_path: str) -> str:
    """Get core metadata for an AnimMontage.

    Args:
        asset_path: Unreal asset path, e.g. '/Game/Montages/AM_Attack'
    """
    script = (
        f"result = animation_helpers.get_montage_info("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [
        f"AnimMontage: {data.get('asset_path', asset_path)}",
        f"  Length: {data.get('sequence_length', 'N/A')}s",
        f"  Rate Scale: {data.get('rate_scale', 1.0)}",
        f"  Sections: {data.get('num_sections', 0)}",
        f"  Auto Blend Out: {data.get('auto_blend_out', False)}",
        f"  Blend In: {data.get('blend_in_time', 'N/A')}s",
        f"  Blend Out: {data.get('blend_out_time', 'N/A')}s (trigger: {data.get('blend_out_trigger_time', 'N/A')}s)",
        f"  Slots: {', '.join(data.get('slot_names', []))}",
    ]
    if data.get("skeleton"):
        lines.append(f"  Skeleton: {data['skeleton']}")
    return "\n".join(lines)


@mcp.tool()
def get_montage_sections(asset_path: str) -> str:
    """Get detailed section list for a montage.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        f"result = animation_helpers.get_montage_sections("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Montage Sections ({data.get('section_count', 0)}):"]
    for s in data.get("sections", []):
        lines.append(f"  [{s.get('index')}] {s.get('name', '?')}")
    return "\n".join(lines)


@mcp.tool()
def get_montage_slots(asset_path: str) -> str:
    """Get slot tracks for a montage.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        f"result = animation_helpers.get_montage_slots("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Montage Slots ({data.get('slot_count', 0)}):"]
    for s in data.get("slots", []):
        lines.append(f"  - {s}")
    return "\n".join(lines)


# --- BlendSpace ---

@mcp.tool()
def get_blendspace_info(asset_path: str) -> str:
    """Get core metadata for a BlendSpace.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        f"result = animation_helpers.get_blendspace_info("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [
        f"BlendSpace: {data.get('asset_path', asset_path)}",
        f"  Type: {data.get('asset_type', 'N/A')} ({'1D' if data.get('is_1d') else '2D'})",
        f"  Samples: {data.get('sample_count', 0)}",
        f"  Loop: {data.get('loop', False)}",
    ]
    if data.get("skeleton"):
        lines.append(f"  Skeleton: {data['skeleton']}")
    return "\n".join(lines)


@mcp.tool()
def get_blendspace_samples(asset_path: str) -> str:
    """Get all sample points in a BlendSpace.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        f"result = animation_helpers.get_blendspace_samples("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"BlendSpace Samples ({data.get('sample_count', 0)}):"]
    for s in data.get("samples", []):
        anim = s.get("animation", "None")
        lines.append(f"  [{s.get('index')}] ({s.get('x', 0):.2f}, {s.get('y', 0):.2f}) -> {anim}")
    return "\n".join(lines)


# --- Skeleton & Mesh ---

@mcp.tool()
def get_skeleton_info(asset_path: str) -> str:
    """Get bone hierarchy and metadata for a Skeleton.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        f"result = animation_helpers.get_skeleton_info("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Skeleton: {data.get('asset_path', asset_path)}"]
    compat = data.get("compatible_skeletons", [])
    if compat:
        lines.append(f"  Compatible Skeletons: {', '.join(compat)}")
    return "\n".join(lines)


@mcp.tool()
def get_skeletal_mesh_info(asset_path: str) -> str:
    """Get metadata for a SkeletalMesh.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        f"result = animation_helpers.get_skeletal_mesh_info("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [
        f"SkeletalMesh: {data.get('asset_path', asset_path)}",
        f"  Skeleton: {data.get('skeleton', 'None')}",
        f"  Morph Targets: {data.get('morph_target_count', 0)}",
        f"  Sockets: {data.get('socket_count', 0)}",
        f"  LODs: {data.get('lod_count', 0)}",
    ]
    return "\n".join(lines)


# --- AnimBlueprint (Python-native) ---

@mcp.tool()
def get_abp_info(asset_path: str) -> str:
    """Get core metadata for an AnimBlueprint.

    Args:
        asset_path: Unreal asset path, e.g. '/Game/Characters/ABP_Hero'
    """
    script = (
        f"result = animation_helpers.get_abp_info("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [
        f"AnimBlueprint: {data.get('asset_path', asset_path)}",
        f"  Target Skeleton: {data.get('target_skeleton', 'None')}",
        f"  Is Template: {data.get('is_template', False)}",
        f"  Multi-threaded Update: {data.get('multi_threaded_update', False)}",
        f"  Linked Layer Sharing: {data.get('linked_layer_sharing', False)}",
    ]
    return "\n".join(lines)


@mcp.tool()
def get_abp_graphs(asset_path: str) -> str:
    """List animation graphs in an AnimBlueprint.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.get_graphs('{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Animation Graphs ({data.get('count', 0)}):"]
    for g in data.get("graphs", []):
        name = g.get("name", "?")
        nodes = g.get("anim_node_count", 0)
        sms = g.get("state_machine_count", 0)
        lines.append(f"  - {name} ({nodes} anim nodes, {sms} state machines)")
    return "\n".join(lines)


@mcp.tool()
def get_abp_nodes(asset_path: str, node_class: str | None = None) -> str:
    """Enumerate anim graph nodes in an AnimBlueprint.

    Args:
        asset_path: Unreal asset path
        node_class: Filter by node class name (e.g. 'AnimGraphNode_BlendListByBool')
    """
    filter_arg = _escape_py_string(node_class) if node_class else ""
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.get_nodes('{_escape_py_string(asset_path)}', '{filter_arg}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"ABP Nodes ({data.get('count', 0)}):"]
    for n in data.get("nodes", []):
        title = n.get("title", n.get("name", "?"))
        graph = n.get("graph", "")
        cls = n.get("class", "?")
        line = f"  [{cls}] {title}"
        if graph:
            line += f" (graph: {graph})"
        pins = n.get("connected_pins", [])
        if pins:
            for p in pins:
                line += f"\n    Pin: {p.get('name', '?')} ({p.get('direction', '?')}, {p.get('connections', 0)} connections)"
        lines.append(line)
    return "\n".join(lines)


@mcp.tool()
def get_abp_asset_overrides(asset_path: str) -> str:
    """Get parent node asset overrides in an AnimBlueprint.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        f"result = animation_helpers.get_abp_asset_overrides("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Asset Overrides ({data.get('override_count', 0)}):"]
    for o in data.get("overrides", []):
        lines.append(f"  GUID: {o.get('guid', '?')} -> {o.get('new_asset', '?')}")
    return "\n".join(lines)


# --- AnimBlueprint (C++ plugin - deep graph) ---

@mcp.tool()
def get_abp_state_machines(asset_path: str) -> str:
    """Get all state machines in an AnimBlueprint with states and transitions.

    Args:
        asset_path: Unreal asset path, e.g. '/Game/Characters/ABP_Hero'
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.get_state_machines('{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"AnimBlueprint: {data.get('asset_path', asset_path)}", f"  State Machines: {data.get('count', 0)}"]
    for sm in data.get("state_machines", []):
        lines.append(f"\n  [{sm.get('name', '?')}] (graph: {sm.get('graph', '?')})")
        lines.append(f"    Entry State: {sm.get('entry_state', 'N/A')}")
        lines.append(f"    States ({sm.get('state_count', 0)}):")
        for s in sm.get("states", []):
            lines.append(f"      - {s.get('name', '?')}")
        lines.append(f"    Transitions ({sm.get('transition_count', 0)}):")
        for t in sm.get("transitions", []):
            lines.append(f"      {t.get('from', '?')} -> {t.get('to', '?')} ({t.get('blend_mode', '?')}, {t.get('cross_fade_duration', '?')}s)")

    return "\n".join(lines)


@mcp.tool()
def get_abp_state_info(asset_path: str, machine_name: str, state_name: str) -> str:
    """Get detailed info about a specific state in an ABP state machine.

    Args:
        asset_path: Unreal asset path
        machine_name: State machine name
        state_name: State name
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.get_state_info("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(machine_name)}', '{_escape_py_string(state_name)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"State: {data.get('state_name', state_name)} in {data.get('machine_name', machine_name)}"]
    lines.append(f"  Nodes ({data.get('node_count', 0)}):")
    for n in data.get("nodes", []):
        lines.append(f"    [{n.get('class', '?')}] {n.get('title', '?')}")
    return "\n".join(lines)


@mcp.tool()
def get_abp_transitions(asset_path: str, machine_name: str) -> str:
    """Get detailed transitions in an ABP state machine.

    Args:
        asset_path: Unreal asset path
        machine_name: State machine name
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.get_transitions("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(machine_name)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Transitions in {data.get('machine_name', machine_name)} ({data.get('count', 0)}):"]
    for t in data.get("transitions", []):
        lines.append(f"  {t.get('from', '?')} -> {t.get('to', '?')}")
        lines.append(f"    Crossfade: {t.get('cross_fade_duration', '?')}s ({t.get('blend_mode', '?')})")
        lines.append(f"    Bidirectional: {t.get('bidirectional', False)}")
        rules = t.get("rule_nodes", [])
        if rules:
            lines.append(f"    Rule Nodes ({len(rules)}):")
            for r in rules:
                lines.append(f"      [{r.get('class', '?')}] {r.get('title', '?')}")
    return "\n".join(lines)


@mcp.tool()
def get_abp_blend_nodes(asset_path: str, graph_name: str = "") -> str:
    """Get blend nodes in an AnimBlueprint graph.

    Args:
        asset_path: Unreal asset path
        graph_name: Graph name to inspect (empty for first graph)
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.get_blend_nodes("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(graph_name)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Blend Nodes in {data.get('graph_name', graph_name)} ({data.get('count', 0)}):"]
    for n in data.get("nodes", []):
        lines.append(f"  [{n.get('class', '?')}] {n.get('title', '?')}")
        for p in n.get("connected_pins", []):
            lines.append(f"    Pin: {p.get('name', '?')} ({p.get('direction', '?')}, {p.get('connections', 0)} connections)")
    return "\n".join(lines)


@mcp.tool()
def get_abp_linked_layers(asset_path: str) -> str:
    """Get linked animation layers in an AnimBlueprint.

    Args:
        asset_path: Unreal asset path
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.get_linked_layers('{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Linked Layers ({data.get('count', 0)}):"]
    for l in data.get("linked_layers", []):
        lines.append(f"  {l.get('title', '?')} (graph: {l.get('graph', '?')})")
    return "\n".join(lines)


# ===========================================================================
# Tier 2: Editing Tools (31 tools)
# ===========================================================================

# --- Notify Editing (Python) ---

@mcp.tool()
def add_notify(asset_path: str, track_name: str, time: float, notify_class: str) -> str:
    """Add a notify to an animation.

    Args:
        asset_path: Unreal asset path
        track_name: Notify track name
        time: Trigger time in seconds
        notify_class: Notify class name (e.g. 'AnimNotify_PlaySound')
    """
    script = (
        f"result = animation_helpers.add_notify("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(track_name)}', "
        f"{time}, '{_escape_py_string(notify_class)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added {notify_class} at {time}s on track '{track_name}'"


@mcp.tool()
def add_notify_state(asset_path: str, track_name: str, time: float, duration: float, notify_state_class: str) -> str:
    """Add a notify state to an animation.

    Args:
        asset_path: Unreal asset path
        track_name: Notify track name
        time: Start time in seconds
        duration: Duration in seconds
        notify_state_class: Notify state class name
    """
    script = (
        f"result = animation_helpers.add_notify_state("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(track_name)}', "
        f"{time}, {duration}, '{_escape_py_string(notify_state_class)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added {notify_state_class} at {time}s (duration: {duration}s)"


@mcp.tool()
def remove_notifies(asset_path: str, notify_name: str | None = None, track_name: str | None = None) -> str:
    """Remove notifies by name or track.

    Args:
        asset_path: Unreal asset path
        notify_name: Remove notifies with this name
        track_name: Remove all notifies on this track
    """
    args = [f"'{_escape_py_string(asset_path)}'"]
    if notify_name:
        args.append(f"notify_name='{_escape_py_string(notify_name)}'")
    if track_name:
        args.append(f"track_name='{_escape_py_string(track_name)}'")
    script = f"result = animation_helpers.remove_notifies({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Removed notifies by: {notify_name or track_name}"


@mcp.tool()
def add_notify_track(asset_path: str, track_name: str) -> str:
    """Add a notify track to an animation.

    Args:
        asset_path: Unreal asset path
        track_name: Name for the new track
    """
    script = (
        f"result = animation_helpers.add_notify_track("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(track_name)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added notify track: {track_name}"


@mcp.tool()
def remove_notify_track(asset_path: str, track_name: str) -> str:
    """Remove a notify track.

    Args:
        asset_path: Unreal asset path
        track_name: Track to remove
    """
    script = (
        f"result = animation_helpers.remove_notify_track("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(track_name)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Removed notify track: {track_name}"


# --- Notify Editing (C++ plugin) ---

@mcp.tool()
def set_notify_time(asset_path: str, notify_index: int, new_time: float) -> str:
    """Set the trigger time of a specific notify.

    Args:
        asset_path: Unreal asset path
        notify_index: Index of the notify
        new_time: New trigger time in seconds
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.set_notify_time("
        f"'{_escape_py_string(asset_path)}', {notify_index}, {new_time})\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Set notify [{notify_index}] time to {new_time}s"


@mcp.tool()
def set_notify_duration(asset_path: str, notify_index: int, new_duration: float) -> str:
    """Set the duration of a notify state.

    Args:
        asset_path: Unreal asset path
        notify_index: Index of the notify state
        new_duration: New duration in seconds
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.set_notify_duration("
        f"'{_escape_py_string(asset_path)}', {notify_index}, {new_duration})\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Set notify [{notify_index}] duration to {new_duration}s"


# --- Curve Editing (Python) ---

@mcp.tool()
def add_curve(asset_path: str, curve_name: str, curve_type: str) -> str:
    """Add a curve to an animation.

    Args:
        asset_path: Unreal asset path
        curve_name: Name for the new curve
        curve_type: 'float', 'vector', or 'transform'
    """
    script = (
        f"result = animation_helpers.add_curve("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(curve_name)}', "
        f"'{_escape_py_string(curve_type)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added {curve_type} curve: {curve_name}"


@mcp.tool()
def add_curve_keys(asset_path: str, curve_name: str, times: list[float], values: list[float]) -> str:
    """Add keys to a float curve.

    Args:
        asset_path: Unreal asset path
        curve_name: Curve name
        times: List of key times
        values: List of key values
    """
    script = (
        f"result = animation_helpers.add_curve_keys("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(curve_name)}', "
        f"{times}, {values})\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added {len(times)} keys to curve: {curve_name}"


@mcp.tool()
def remove_curve(asset_path: str, curve_name: str) -> str:
    """Remove a curve from an animation.

    Args:
        asset_path: Unreal asset path
        curve_name: Curve to remove
    """
    script = (
        f"result = animation_helpers.remove_curve("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(curve_name)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Removed curve: {curve_name}"


# --- Sync Marker Editing (Python) ---

@mcp.tool()
def add_sync_marker(asset_path: str, marker_name: str, time: float, track_name: str) -> str:
    """Add a sync marker to an animation.

    Args:
        asset_path: Unreal asset path
        marker_name: Marker name
        time: Time in seconds
        track_name: Notify track name
    """
    script = (
        f"result = animation_helpers.add_sync_marker("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(marker_name)}', "
        f"{time}, '{_escape_py_string(track_name)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added sync marker '{marker_name}' at {time}s"


@mcp.tool()
def remove_sync_markers(asset_path: str, marker_name: str | None = None, track_name: str | None = None) -> str:
    """Remove sync markers by name, track, or all.

    Args:
        asset_path: Unreal asset path
        marker_name: Remove markers with this name
        track_name: Remove markers on this track
    """
    args = [f"'{_escape_py_string(asset_path)}'"]
    if marker_name:
        args.append(f"marker_name='{_escape_py_string(marker_name)}'")
    if track_name:
        args.append(f"track_name='{_escape_py_string(track_name)}'")
    script = f"result = animation_helpers.remove_sync_markers({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Removed sync markers by: {marker_name or track_name or 'all'}"


# --- Property Editing (Python) ---

@mcp.tool()
def set_root_motion(asset_path: str, enabled: bool, lock_type: str | None = None) -> str:
    """Enable/disable root motion on an animation.

    Args:
        asset_path: Unreal asset path
        enabled: Enable or disable root motion
        lock_type: Lock type (e.g. 'AnimFirstFrame', 'Zero', 'RefPose')
    """
    args = [f"'{_escape_py_string(asset_path)}'", str(enabled)]
    if lock_type:
        args.append(f"lock_type='{_escape_py_string(lock_type)}'")
    script = f"result = animation_helpers.set_root_motion({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Root motion {'enabled' if enabled else 'disabled'}"


@mcp.tool()
def set_rate_scale(asset_path: str, rate_scale: float) -> str:
    """Set the rate scale of an animation.

    Args:
        asset_path: Unreal asset path
        rate_scale: New rate scale value
    """
    script = (
        f"result = animation_helpers.set_rate_scale("
        f"'{_escape_py_string(asset_path)}', {rate_scale})\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Set rate scale to {rate_scale}"


@mcp.tool()
def set_additive_type(asset_path: str, additive_type: str, base_pose_type: str | None = None) -> str:
    """Set additive animation type.

    Args:
        asset_path: Unreal asset path
        additive_type: Additive type (e.g. 'AAT_None', 'AAT_LocalSpaceBase')
        base_pose_type: Base pose type (e.g. 'ABPT_None', 'ABPT_RefPose')
    """
    args = [f"'{_escape_py_string(asset_path)}'", f"'{_escape_py_string(additive_type)}'"]
    if base_pose_type:
        args.append(f"base_pose_type='{_escape_py_string(base_pose_type)}'")
    script = f"result = animation_helpers.set_additive_type({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Set additive type to {additive_type}"


# --- Virtual Bones (Python) ---

@mcp.tool()
def add_virtual_bone(asset_path: str, source_bone: str, target_bone: str) -> str:
    """Add a virtual bone to a skeleton.

    Args:
        asset_path: Unreal asset path to skeleton
        source_bone: Source bone name
        target_bone: Target bone name
    """
    script = (
        f"result = animation_helpers.add_virtual_bone("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(source_bone)}', "
        f"'{_escape_py_string(target_bone)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added virtual bone: {source_bone} -> {target_bone}"


@mcp.tool()
def remove_virtual_bones(asset_path: str, bone_names: list[str] | None = None) -> str:
    """Remove virtual bones from a skeleton.

    Args:
        asset_path: Unreal asset path
        bone_names: Specific bones to remove (omit for all)
    """
    args = [f"'{_escape_py_string(asset_path)}'"]
    if bone_names:
        bones_str = ", ".join(f"'{_escape_py_string(b)}'" for b in bone_names)
        args.append(f"bone_names=[{bones_str}]")
    script = f"result = animation_helpers.remove_virtual_bones({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Removed virtual bones: {bone_names or 'all'}"


@mcp.tool()
def copy_notifies(source_path: str, dest_path: str) -> str:
    """Copy notifies from one animation to another.

    Args:
        source_path: Source asset path
        dest_path: Destination asset path
    """
    script = (
        f"result = animation_helpers.copy_notifies("
        f"'{_escape_py_string(source_path)}', '{_escape_py_string(dest_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Copied notifies from {source_path} to {dest_path}"


# --- Montage Editing (Python) ---

@mcp.tool()
def set_montage_blend(
    asset_path: str,
    blend_in_time: float | None = None,
    blend_out_time: float | None = None,
    blend_out_trigger: float | None = None,
    auto_blend_out: bool | None = None,
) -> str:
    """Set montage blend settings.

    Args:
        asset_path: Unreal asset path
        blend_in_time: Blend in time in seconds
        blend_out_time: Blend out time in seconds
        blend_out_trigger: Blend out trigger time
        auto_blend_out: Enable auto blend out
    """
    args = [f"'{_escape_py_string(asset_path)}'"]
    if blend_in_time is not None:
        args.append(f"blend_in_time={blend_in_time}")
    if blend_out_time is not None:
        args.append(f"blend_out_time={blend_out_time}")
    if blend_out_trigger is not None:
        args.append(f"blend_out_trigger={blend_out_trigger}")
    if auto_blend_out is not None:
        args.append(f"auto_blend_out={auto_blend_out}")
    script = f"result = animation_helpers.set_montage_blend({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return "Updated montage blend settings"


# --- Metadata (Python) ---

@mcp.tool()
def add_meta_data(asset_path: str, meta_data_class: str) -> str:
    """Add metadata to an animation asset.

    Args:
        asset_path: Unreal asset path
        meta_data_class: Metadata class name
    """
    script = (
        f"result = animation_helpers.add_meta_data("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(meta_data_class)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added metadata: {meta_data_class}"


@mcp.tool()
def remove_meta_data(asset_path: str, meta_data_class: str | None = None) -> str:
    """Remove metadata from an animation asset.

    Args:
        asset_path: Unreal asset path
        meta_data_class: Specific class to remove (omit for all)
    """
    args = [f"'{_escape_py_string(asset_path)}'"]
    if meta_data_class:
        args.append(f"meta_data_class='{_escape_py_string(meta_data_class)}'")
    script = f"result = animation_helpers.remove_meta_data({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Removed metadata: {meta_data_class or 'all'}"


# --- Montage Section Editing (C++ plugin) ---

@mcp.tool()
def add_montage_section(asset_path: str, section_name: str, start_time: float) -> str:
    """Add a new section to a montage.

    Args:
        asset_path: Unreal asset path
        section_name: Name for the new section
        start_time: Start time in seconds
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.add_montage_section("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(section_name)}', {start_time})\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added section '{section_name}' at {start_time}s (index: {data.get('index', '?')})"


@mcp.tool()
def delete_montage_section(asset_path: str, section_index: int) -> str:
    """Delete a section from a montage.

    Args:
        asset_path: Unreal asset path
        section_index: Index of the section to delete
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.delete_montage_section("
        f"'{_escape_py_string(asset_path)}', {section_index})\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Deleted section [{section_index}]: {data.get('deleted_section', '?')}"


@mcp.tool()
def set_section_next(asset_path: str, section_name: str, next_section_name: str) -> str:
    """Set the next section for a montage section.

    Args:
        asset_path: Unreal asset path
        section_name: Current section name
        next_section_name: Next section to play
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.set_section_next("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(section_name)}', "
        f"'{_escape_py_string(next_section_name)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Set {section_name} -> {next_section_name}"


@mcp.tool()
def set_section_time(asset_path: str, section_name: str, new_time: float) -> str:
    """Set the start time of a montage section.

    Args:
        asset_path: Unreal asset path
        section_name: Section name
        new_time: New start time in seconds
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.set_section_time("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(section_name)}', {new_time})\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Set section '{section_name}' time to {new_time}s"


# --- BlendSpace Sample Editing (C++ plugin) ---

@mcp.tool()
def add_blendspace_sample(asset_path: str, anim_path: str, x: float, y: float) -> str:
    """Add a sample to a BlendSpace.

    Args:
        asset_path: BlendSpace asset path
        anim_path: Animation asset path for the sample
        x: X axis value
        y: Y axis value
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.add_blend_space_sample("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(anim_path)}', {x}, {y})\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added sample at ({x}, {y}) -> {anim_path}"


@mcp.tool()
def edit_blendspace_sample(asset_path: str, sample_index: int, x: float, y: float, anim_path: str = "") -> str:
    """Edit a BlendSpace sample position and/or animation.

    Args:
        asset_path: BlendSpace asset path
        sample_index: Index of the sample to edit
        x: New X axis value
        y: New Y axis value
        anim_path: New animation path (empty to keep current)
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.edit_blend_space_sample("
        f"'{_escape_py_string(asset_path)}', {sample_index}, {x}, {y}, '{_escape_py_string(anim_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Edited sample [{sample_index}] to ({x}, {y})"


@mcp.tool()
def delete_blendspace_sample(asset_path: str, sample_index: int) -> str:
    """Delete a sample from a BlendSpace.

    Args:
        asset_path: BlendSpace asset path
        sample_index: Index of the sample to delete
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.delete_blend_space_sample("
        f"'{_escape_py_string(asset_path)}', {sample_index})\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Deleted sample [{sample_index}]"


# --- Bone Track Editing (C++ plugin) ---

@mcp.tool()
def add_bone_track(asset_path: str, bone_name: str) -> str:
    """Add a bone track to an animation.

    Args:
        asset_path: Unreal asset path
        bone_name: Bone name
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.add_bone_track("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(bone_name)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Added bone track: {bone_name}"


@mcp.tool()
def remove_bone_track(asset_path: str, bone_name: str, include_children: bool = False) -> str:
    """Remove a bone track from an animation.

    Args:
        asset_path: Unreal asset path
        bone_name: Bone name
        include_children: Also remove child bone tracks
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.remove_bone_track("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(bone_name)}', "
        f"{'True' if include_children else 'False'})\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Removed bone track: {bone_name}"


@mcp.tool()
def set_bone_track_keys(asset_path: str, bone_name: str, positions_json: str, rotations_json: str, scales_json: str) -> str:
    """Set bone track keys for an animation.

    Args:
        asset_path: Unreal asset path
        bone_name: Bone name
        positions_json: JSON array of [x,y,z] positions
        rotations_json: JSON array of [x,y,z,w] rotations
        scales_json: JSON array of [x,y,z] scales
    """
    script = (
        "import unreal, json\n"
        f"result = unreal.AnimationMCPReaderLibrary.set_bone_track_keys("
        f"'{_escape_py_string(asset_path)}', '{_escape_py_string(bone_name)}', "
        f"'{_escape_py_string(positions_json)}', '{_escape_py_string(rotations_json)}', "
        f"'{_escape_py_string(scales_json)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_plugin_call(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"
    return f"Set {data.get('num_keys', '?')} keys for bone: {bone_name}"


# ===========================================================================
# Tier 3: Search & Analysis Tools (8 tools)
# ===========================================================================

@mcp.tool()
def search_animations(
    query: str | None = None,
    anim_type: str | None = None,
    folder: str | None = None,
    skeleton: str | None = None,
) -> str:
    """Search for animation assets by name, type, folder, or skeleton.

    Args:
        query: Name pattern to match (case-insensitive)
        anim_type: Filter by type: AnimSequence, AnimMontage, BlendSpace, BlendSpace1D, AnimBlueprint
        folder: Unreal folder path, e.g. '/Game/Animations'
        skeleton: Filter by skeleton path
    """
    args = []
    if query: args.append(f"query='{_escape_py_string(query)}'")
    if anim_type: args.append(f"anim_type='{_escape_py_string(anim_type)}'")
    if folder: args.append(f"folder='{_escape_py_string(folder)}'")
    if skeleton: args.append(f"skeleton='{_escape_py_string(skeleton)}'")

    script = f"result = animation_helpers.search_animations({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    results = data.get("results", [])
    if not results:
        return "No animations found matching criteria."

    lines = [f"Found {data.get('count', 0)} animations:"]
    for r in results:
        lines.append(f"  [{r.get('class', '?')}] {r.get('name', '?')}  ({r.get('path', '')})")
    return "\n".join(lines)


@mcp.tool()
def search_by_notify(notify_name: str | None = None, notify_class: str | None = None, folder: str | None = None) -> str:
    """Find animations containing a specific notify.

    Args:
        notify_name: Notify name to search for
        notify_class: Notify class to search for
        folder: Restrict search to folder
    """
    args = []
    if notify_name: args.append(f"notify_name='{_escape_py_string(notify_name)}'")
    if notify_class: args.append(f"notify_class='{_escape_py_string(notify_class)}'")
    if folder: args.append(f"folder='{_escape_py_string(folder)}'")

    script = f"result = animation_helpers.search_by_notify({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    matches = data.get("matches", [])
    if not matches:
        return "No animations found with matching notify."

    lines = [f"Found {data.get('count', 0)} animations:"]
    for m in matches:
        lines.append(f"  {m.get('asset', '?')} — {m.get('notify', '?')} [{m.get('class', '')}]")
    return "\n".join(lines)


@mcp.tool()
def search_by_curve(curve_name: str, curve_type: str | None = None, folder: str | None = None) -> str:
    """Find animations containing a specific curve.

    Args:
        curve_name: Curve name to search for
        curve_type: Filter by type: 'float', 'vector', 'transform'
        folder: Restrict search to folder
    """
    args = [f"'{_escape_py_string(curve_name)}'"]
    if curve_type: args.append(f"curve_type='{_escape_py_string(curve_type)}'")
    if folder: args.append(f"folder='{_escape_py_string(folder)}'")

    script = f"result = animation_helpers.search_by_curve({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    matches = data.get("matches", [])
    if not matches:
        return "No animations found with matching curve."

    lines = [f"Found {data.get('count', 0)} animations:"]
    for m in matches:
        lines.append(f"  {m.get('asset', '?')}")
    return "\n".join(lines)


@mcp.tool()
def search_by_slot(slot_name: str, folder: str | None = None) -> str:
    """Find montages using a specific slot.

    Args:
        slot_name: Slot name to search for
        folder: Restrict search to folder
    """
    args = [f"'{_escape_py_string(slot_name)}'"]
    if folder: args.append(f"folder='{_escape_py_string(folder)}'")

    script = f"result = animation_helpers.search_by_slot({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    matches = data.get("matches", [])
    if not matches:
        return "No montages found using that slot."

    lines = [f"Found {data.get('count', 0)} montages:"]
    for m in matches:
        lines.append(f"  {m.get('asset', '?')} (slots: {', '.join(m.get('slots', []))})")
    return "\n".join(lines)


@mcp.tool()
def audit_notifies(asset_path: str | None = None, folder: str | None = None) -> str:
    """Audit notify usage across animations.

    Args:
        asset_path: Specific asset to audit (omit for folder scan)
        folder: Folder to scan
    """
    args = []
    if asset_path: args.append(f"asset_path='{_escape_py_string(asset_path)}'")
    if folder: args.append(f"folder='{_escape_py_string(folder)}'")

    script = f"result = animation_helpers.audit_notifies({', '.join(args)})\nprint(result)\n"
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [
        f"Notify Audit ({data.get('assets_checked', 0)} assets, {data.get('unique_notifies', 0)} unique notifies):",
    ]
    for nf in data.get("notify_frequencies", [])[:20]:
        lines.append(f"  {nf.get('name', '?')}: {nf.get('count', 0)}")
    issues = data.get("issues", [])
    if issues:
        lines.append(f"\nIssues ({len(issues)}):")
        for iss in issues[:10]:
            lines.append(f"  {iss.get('asset', '?')} — {iss.get('notify', '?')}: {iss.get('issue', '?')}")
    return "\n".join(lines)


@mcp.tool()
def audit_blendspace(asset_path: str) -> str:
    """Analyze BlendSpace sample coverage and find issues.

    Args:
        asset_path: BlendSpace asset path
    """
    script = (
        f"result = animation_helpers.audit_blendspace("
        f"'{_escape_py_string(asset_path)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"BlendSpace Audit: {data.get('sample_count', 0)} samples"]
    dupes = data.get("duplicate_positions", [])
    if dupes:
        lines.append(f"  Duplicate positions ({len(dupes)}):")
        for d in dupes:
            lines.append(f"    Sample {d.get('index_a')} and {d.get('index_b')}")
    else:
        lines.append("  No duplicate positions found.")
    return "\n".join(lines)


@mcp.tool()
def compare_animations(path_a: str, path_b: str) -> str:
    """Compare two animation assets.

    Args:
        path_a: First animation asset path
        path_b: Second animation asset path
    """
    script = (
        f"result = animation_helpers.compare_animations("
        f"'{_escape_py_string(path_a)}', '{_escape_py_string(path_b)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    diffs = data.get("differences", [])
    if not diffs:
        return f"No differences found between {path_a} and {path_b}"

    lines = [f"Differences between {path_a} and {path_b}:"]
    for d in diffs:
        lines.append(f"  {d.get('property', '?')}: {d.get('a', '?')} vs {d.get('b', '?')}")
    return "\n".join(lines)


@mcp.tool()
def get_animation_summary(folder: str) -> str:
    """Get folder-level animation stats.

    Args:
        folder: Unreal folder path, e.g. '/Game/Animations'
    """
    script = (
        f"result = animation_helpers.get_animation_summary("
        f"'{_escape_py_string(folder)}')\n"
        "print(result)\n"
    )
    try:
        data = _run_animation_script(script)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return f"Error: {err}"

    lines = [f"Animation Summary for {data.get('folder', folder)}:"]
    lines.append(f"  Total Assets: {data.get('total_assets', 0)}")
    for type_name, count in data.get("type_counts", {}).items():
        lines.append(f"  {type_name}: {count}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------

def main() -> None:
    """Run the MCP server."""
    mcp.run()
