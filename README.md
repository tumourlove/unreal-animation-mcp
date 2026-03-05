# unreal-animation-mcp

Animation data inspector and editor for Unreal Engine AI development via Model Context Protocol.

Inspect, search, and edit animation sequences, montages, blend spaces, animation blueprints, skeletons, and skeletal meshes — 62 tools total.

## Why?

Animation data in Unreal is deeply nested and spread across many asset types — sequences hold notifies, curves, and bone tracks; montages add sections and slots on top; blend spaces map animations to parameter grids; and Animation Blueprints wire it all together through state machines, transitions, and blend nodes. AI agents can't see any of this from C++ alone. This server exposes the full animation stack as structured data so agents can inspect, search, audit, and edit animation assets alongside the rest of your project.

**Complements** (does not replace):
- [unreal-source-mcp](https://github.com/tumourlove/unreal-source-mcp) — Engine-level source intelligence (full UE C++ and HLSL)
- [unreal-project-mcp](https://github.com/tumourlove/unreal-project-mcp) — Project-level source intelligence (your C++ code)
- [unreal-editor-mcp](https://github.com/tumourlove/unreal-editor-mcp) — Build diagnostics and editor log tools (Live Coding, error parsing, log search)
- [unreal-blueprint-mcp](https://github.com/tumourlove/unreal-blueprint-mcp) — Blueprint graph reading (nodes, pins, connections, execution flow)
- [unreal-blueprint-reader](https://github.com/tumourlove/unreal-blueprint-reader) — C++ editor plugin that serializes Blueprint graphs to JSON for AI tooling
- [unreal-material-mcp](https://github.com/tumourlove/unreal-material-mcp) — Material graph intelligence and editing (expressions, connections, parameters, instances, graph manipulation)
- [unreal-config-mcp](https://github.com/tumourlove/unreal-config-mcp) — Config/INI intelligence (resolve inheritance chains, search settings, diff from defaults, explain CVars)
- [unreal-niagara-mcp](https://github.com/tumourlove/unreal-niagara-mcp) — Niagara VFX intelligence and editing (emitters, modules, HLSL generation, procedural creation, 70 tools)
- [unreal-api-mcp](https://github.com/nicobailon/unreal-api-mcp) by [Nico Bailon](https://github.com/nicobailon) — API surface lookup (signatures, #include paths, deprecation warnings)

Together these servers give AI agents full-stack UE understanding: engine internals, API surface, your project code, build/runtime feedback, Blueprint graph data, config/INI intelligence, material graph inspection + editing, animation data inspection + editing, and Niagara VFX inspection + creation.

## Prerequisites

- **AnimationMCPReader plugin** installed in your UE project ([unreal-animation-reader](https://github.com/tumourlove/unreal-animation-reader)) — required for C++-backed tools (montage sections, blendspace samples, ABP state machines/transitions/blend nodes, notify time/duration, bone track keys)
- **Python Remote Execution** enabled in the editor: **Edit > Project Settings** > search "remote" > under **Python Remote Execution**, check **"Enable Remote Execution?"**

## Quick Start

### Install from GitHub

```bash
uvx --from git+https://github.com/tumourlove/unreal-animation-mcp.git unreal-animation-mcp
```

### Claude Code Configuration

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "unreal-animation": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/tumourlove/unreal-animation-mcp.git", "unreal-animation-mcp"],
      "env": {
        "UE_PROJECT_PATH": "D:/Unreal Projects/YourProject"
      }
    }
  }
}
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `UE_PROJECT_PATH` | *(required)* | Absolute path to your `.uproject` root |
| `UE_EDITOR_PYTHON_PORT` | `6776` | TCP port for editor Python commands |
| `UE_MULTICAST_GROUP` | `239.0.0.1` | Multicast group for editor discovery |
| `UE_MULTICAST_PORT` | `6766` | Multicast port for editor discovery |
| `UE_MULTICAST_BIND` | `127.0.0.1` | Local interface to bind multicast listener |

## How It Works

1. **Editor Discovery** — Discovers the running UE editor via UDP multicast (the same protocol as UE's built-in `remote_execution.py`). Opens a TCP command channel to execute Python in the editor.

2. **Helper Upload** — Uploads `animation_helpers.py` to `{project}/Saved/AnimationMCP/` on first use. The helper module wraps `unreal.AnimationLibrary` and related APIs for inspection, editing, and search operations.

3. **Plugin Bridge** — For advanced operations, sends Python commands that call `AnimationMCPReaderLibrary` static functions from the companion C++ plugin. The plugin serializes animation graph data to JSON strings.

4. **Serving** — FastMCP server exposes 62 tools over stdio. Claude Code manages the server lifecycle automatically.

**No database, no indexing** — all data comes live from the running editor. The server is stateless; animation data is read on demand from whatever assets are loaded.

## Adding to Your Project's CLAUDE.md

```markdown
## Animation Data (unreal-animation MCP)

Use `unreal-animation` MCP tools to inspect, edit, and search animation data —
sequences, montages, blend spaces, ABPs, skeletons, and meshes. Requires
**AnimationMCPReader** plugin and **Python Remote Execution** enabled in editor.

| Category | Tools | When |
|----------|-------|------|
| Sequence Inspect | `get_anim_sequence_info`, `get_anim_notifies`, `get_anim_curves`, `get_bone_tracks` | Understand an animation's properties, notifies, curves, bone data |
| Montage Inspect | `get_montage_info`, `get_montage_sections`, `get_montage_slots` | Read montage structure, sections, slot assignments |
| BlendSpace | `get_blendspace_info`, `get_blendspace_samples` | Read blend space parameters and sample points |
| ABP Inspect | `get_abp_info`, `get_abp_state_machines`, `get_abp_transitions` | Read AnimBP graph structure, state machines, transitions |
| Notify Edit | `add_notify`, `add_notify_state`, `remove_notifies`, `set_notify_time` | Add/remove/move animation notifies |
| Montage Edit | `add_montage_section`, `set_section_next`, `set_montage_blend` | Edit montage sections and blend settings |
| Search | `search_animations`, `search_by_notify`, `audit_notifies` | Find animations by type/folder, audit notify usage |

**Asset paths (no extension):**
- Project `Content/`: `/Game/Path/To/Asset`
- Project `Plugins/`: `/PluginName/Path/To/Asset`
- Engine plugins: `/PluginName/Path/To/Asset`
```

## Tools (62)

### Inspection (23)

- **AnimSequence**: `get_anim_sequence_info`, `get_anim_notifies`, `get_anim_curves`, `get_bone_tracks`, `get_bone_pose_at_time`, `get_sync_markers`
- **AnimMontage**: `get_montage_info`, `get_montage_sections`, `get_montage_slots`
- **BlendSpace**: `get_blendspace_info`, `get_blendspace_samples`
- **Skeleton/Mesh**: `get_skeleton_info`, `get_skeletal_mesh_info`
- **AnimBlueprint**: `get_abp_info`, `get_abp_graphs`, `get_abp_nodes`, `get_abp_asset_overrides`, `get_abp_state_machines`, `get_abp_state_info`, `get_abp_transitions`, `get_abp_blend_nodes`, `get_abp_linked_layers`

### Editing (31)

- **Notifies**: `add_notify`, `add_notify_state`, `remove_notifies`, `add_notify_track`, `remove_notify_track`, `set_notify_time`, `set_notify_duration`
- **Curves**: `add_curve`, `add_curve_keys`, `remove_curve`
- **Sync Markers**: `add_sync_marker`, `remove_sync_markers`
- **Properties**: `set_root_motion`, `set_rate_scale`, `set_additive_type`
- **Virtual Bones**: `add_virtual_bone`, `remove_virtual_bones`
- **Montage**: `set_montage_blend`, `add_montage_section`, `delete_montage_section`, `set_section_next`, `set_section_time`
- **BlendSpace**: `add_blendspace_sample`, `edit_blendspace_sample`, `delete_blendspace_sample`
- **Bone Tracks**: `add_bone_track`, `remove_bone_track`, `set_bone_track_keys`
- **Misc**: `copy_notifies`, `add_meta_data`, `remove_meta_data`

### Search & Analysis (8)

- `search_animations`, `search_by_notify`, `search_by_curve`, `search_by_slot`
- `audit_notifies`, `audit_blendspace`, `compare_animations`, `get_animation_summary`

## Development

```bash
# Clone and install
git clone https://github.com/tumourlove/unreal-animation-mcp.git
cd unreal-animation-mcp
uv sync

# Run tests
uv run pytest -v

# Run server locally
uv run unreal-animation-mcp
```

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Unreal Engine 5.x with Python plugin and Remote Execution enabled
- [AnimationMCPReader](https://github.com/tumourlove/unreal-animation-reader) C++ plugin

## License

MIT
