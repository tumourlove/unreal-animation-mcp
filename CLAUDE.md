# CLAUDE.md — unreal-animation-mcp

## Project Overview

**unreal-animation-mcp** — Animation data inspector and editor for Unreal Engine AI development.

An MCP server that inspects, searches, and edits animation assets via the editor Python bridge and a C++ editor plugin. Covers AnimSequences, AnimMontages, BlendSpaces, AnimBlueprints, Skeletons, and SkeletalMeshes.

**Complements** (does not replace):
- `unreal-source-mcp` — Engine-level source intelligence
- `unreal-project-mcp` — Project-level source intelligence
- `unreal-editor-mcp` — Build diagnostics and editor log tools
- `unreal-blueprint-mcp` — Blueprint graph reading
- `unreal-material-mcp` — Material graph intelligence
- `unreal-config-mcp` — Config/INI intelligence

**We provide:** Animation pipeline visibility + editing — sequences, montages, blend spaces, ABP state machines/transitions/blend nodes, skeletons, skeletal meshes, notifies, curves, sync markers, bone tracks.

**C++ Plugin:** `AnimationMCPReader` (separate repo) — exposes 17 functions for deep access to montage sections, blendspace samples, ABP graph internals, notify timing, and bone track keys that Python can't reach natively.

## Tech Stack

- **Language:** Python 3.11+
- **MCP SDK:** `mcp` Python package (FastMCP)
- **Distribution:** PyPI via `uvx unreal-animation-mcp`
- **Package manager:** `uv` (for dev and build)
- **C++ Plugin:** Unreal Engine 5 Editor module (AnimationMCPReader)

## Project Structure

    unreal-animation-mcp/
    ├── pyproject.toml
    ├── CLAUDE.md
    ├── README.md
    ├── src/
    │   └── unreal_animation_mcp/
    │       ├── __init__.py              # Version
    │       ├── __main__.py              # CLI entry point
    │       ├── config.py                # UE_PROJECT_PATH, port config
    │       ├── server.py                # FastMCP + 62 tool definitions
    │       ├── editor_bridge.py         # UE remote execution protocol client
    │       └── helpers/
    │           └── animation_helpers.py # Uploaded to editor, runs in-process
    └── tests/
        └── test_server.py              # 68 tests (mocked bridge)

    AnimationMCPReader/                  # Separate C++ plugin repo
    ├── AnimationMCPReader.uplugin
    └── Source/AnimationMCPReader/
        ├── AnimationMCPReader.Build.cs
        ├── Public/AnimationMCPReaderLibrary.h    # 17 UFUNCTION declarations
        └── Private/
            ├── AnimationMCPReaderModule.cpp
            └── AnimationMCPReaderLibrary.cpp     # Full implementations

## Build & Run

```bash
uv sync                                    # Install deps
uv run pytest tests/ -v                    # Run tests (68 tests)
uv run python -m unreal_animation_mcp      # Run MCP server
```

## MCP Configuration (for Claude Code)

```json
{
  "mcpServers": {
    "unreal-animation": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/YourOrg/unreal-animation-mcp.git", "unreal-animation-mcp"],
      "env": {
        "UE_PROJECT_PATH": "D:/Unreal Projects/YourProject"
      }
    }
  }
}
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `UE_PROJECT_PATH` | Path to UE project root (contains .uproject) — required |
| `UE_EDITOR_PYTHON_PORT` | TCP port for command connection (default: 6776) |
| `UE_MULTICAST_GROUP` | UDP multicast group for discovery (default: 239.0.0.1) |
| `UE_MULTICAST_PORT` | UDP multicast port (default: 6766) |
| `UE_MULTICAST_BIND` | Multicast bind address (default: 127.0.0.1) |

## MCP Tools (62)

### Tier 1: Inspection (23 tools)

| Tool | Purpose |
|------|---------|
| `get_anim_sequence_info` | Length, frames, rate scale, interpolation, additive type, root motion, bone tracks, skeleton |
| `get_anim_notifies` | All notifies with type, class, trigger time, duration, track |
| `get_anim_curves` | Float/vector/transform curves with key counts |
| `get_bone_tracks` | Bone track list or specific bone key counts |
| `get_bone_pose_at_time` | Bone transforms (location, rotation, scale) at a time |
| `get_sync_markers` | Sync markers with names and times |
| `get_montage_info` | Length, sections, blend settings, slots, skeleton |
| `get_montage_sections` | Section list with indices and names |
| `get_montage_slots` | Slot track names |
| `get_blendspace_info` | Type (1D/2D), sample count, loop, skeleton |
| `get_blendspace_samples` | Sample positions and animations |
| `get_skeleton_info` | Compatible skeletons |
| `get_skeletal_mesh_info` | Morph targets, sockets, LODs, skeleton ref |
| `get_abp_info` | Target skeleton, template status, threading, layer sharing |
| `get_abp_graphs` | Animation graph list |
| `get_abp_nodes` | Enumerate anim graph nodes, optional class filter |
| `get_abp_asset_overrides` | Parent node asset overrides |
| `get_abp_state_machines` | State machines with states, transitions, entry state (C++ plugin) |
| `get_abp_state_info` | State inner graph nodes (C++ plugin) |
| `get_abp_transitions` | Detailed transitions with rule nodes (C++ plugin) |
| `get_abp_blend_nodes` | Blend nodes with connected pins (C++ plugin) |
| `get_abp_linked_layers` | Linked animation layers (C++ plugin) |
| `get_abp_asset_overrides` | Parent node overrides |

### Tier 2: Editing (31 tools)

| Tool | Purpose |
|------|---------|
| `add_notify` | Add notify to animation |
| `add_notify_state` | Add notify state with duration |
| `remove_notifies` | Remove notifies by name or track |
| `add_notify_track` | Add notify track |
| `remove_notify_track` | Remove notify track |
| `set_notify_time` | Set notify trigger time (C++ plugin) |
| `set_notify_duration` | Set notify state duration (C++ plugin) |
| `add_curve` | Add float/vector/transform curve |
| `add_curve_keys` | Add keys to float curve |
| `remove_curve` | Remove curve |
| `add_sync_marker` | Add sync marker |
| `remove_sync_markers` | Remove sync markers by name/track/all |
| `set_root_motion` | Enable/disable root motion |
| `set_rate_scale` | Set animation rate scale |
| `set_additive_type` | Set additive animation type |
| `add_virtual_bone` | Add virtual bone |
| `remove_virtual_bones` | Remove virtual bones |
| `copy_notifies` | Copy notifies between animations |
| `set_montage_blend` | Set montage blend in/out settings |
| `add_meta_data` | Add metadata |
| `remove_meta_data` | Remove metadata |
| `add_montage_section` | Add montage section (C++ plugin) |
| `delete_montage_section` | Delete montage section (C++ plugin) |
| `set_section_next` | Set section next link (C++ plugin) |
| `set_section_time` | Set section start time (C++ plugin) |
| `add_blendspace_sample` | Add blendspace sample (C++ plugin) |
| `edit_blendspace_sample` | Edit blendspace sample (C++ plugin) |
| `delete_blendspace_sample` | Delete blendspace sample (C++ plugin) |
| `add_bone_track` | Add bone track (C++ plugin) |
| `remove_bone_track` | Remove bone track (C++ plugin) |
| `set_bone_track_keys` | Set bone track keys (C++ plugin) |

### Tier 3: Search & Analysis (8 tools)

| Tool | Purpose |
|------|---------|
| `search_animations` | Find animations by name, type, folder, skeleton |
| `search_by_notify` | Find animations containing a notify |
| `search_by_curve` | Find animations containing a curve |
| `search_by_slot` | Find montages using a slot |
| `audit_notifies` | Audit notify usage, find issues |
| `audit_blendspace` | Analyze blendspace coverage, find duplicates |
| `compare_animations` | Diff two animations |
| `get_animation_summary` | Folder-level animation stats |

## Architecture Notes

- **Helper module strategy** — `animation_helpers.py` is uploaded to `{project}/Saved/AnimationMCP/` on first tool call. MD5 hash skips re-upload if unchanged.
- **Two-tier architecture** — Python helpers handle AnimationLibrary calls. C++ plugin (AnimationMCPReaderLibrary) handles deep graph access (montage sections, blendspace samples, ABP state machines, notify editing, bone tracks).
- **C++ plugin calls** — Tools call `unreal.AnimationMCPReaderLibrary.function_name()` directly via bridge, bypassing the helper upload.
- **Editor bridge** — UE remote execution protocol: UDP multicast discovery → TCP command connection. Shared pattern across all sister servers.
- **Undo support** — All C++ editing functions wrap changes in `GEditor->BeginTransaction/EndTransaction` with `Modify()` for undo support.

## Coding Conventions

- **Lazy singletons** — `_get_bridge()` inits on first call, stored in module global
- **`_reset_state()`** — every module with singletons exposes this for test teardown
- **Mock-based testing** — tests mock EditorBridge; no real editor needed
- **Formatted string returns** — all tools return human-readable multi-line strings, not raw JSON
- Follow standard Python conventions: snake_case, type hints, docstrings on public functions
- Use `logging` module, not print statements
- Keep dependencies minimal — just `mcp>=1.0.0`

## C++ Plugin Dependencies

```
Core, CoreUObject, Engine, UnrealEd, AnimGraph, AnimGraphRuntime,
BlueprintGraph, AnimationBlueprintLibrary, Json, JsonUtilities
```
