# unreal-animation-mcp

Animation data inspector and editor for Unreal Engine AI development via MCP.

Inspect, search, and edit animation sequences, montages, blend spaces, animation blueprints, skeletons, and skeletal meshes — 62 tools total.

## Installation

### Python MCP Server

```bash
uvx unreal-animation-mcp
```

Or install from source:

```bash
git clone https://github.com/YourOrg/unreal-animation-mcp.git
cd unreal-animation-mcp
uv sync
uv run python -m unreal_animation_mcp
```

### C++ Plugin (AnimationMCPReader)

1. Copy the `AnimationMCPReader/` folder into your UE project's `Plugins/` directory
2. Restart the editor
3. Enable the plugin in Edit > Plugins > Animation MCP Reader

The C++ plugin is required for advanced tools: montage section editing, blendspace sample editing, ABP state machine/transition/blend node reading, notify time editing, and bone track key editing.

## MCP Configuration

Add to your Claude Code MCP settings:

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

## Requirements

- Python 3.11+
- Unreal Engine 5 with Python scripting plugin enabled
- `AnimationMCPReader` C++ plugin (for C++-backed tools)
- `UE_PROJECT_PATH` environment variable pointing to your .uproject root

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

## Usage Examples

```
> get_anim_sequence_info /Game/Animations/AS_Run

AnimSequence: /Game/Animations/AS_Run
  Length: 0.833s (25 frames)
  Rate Scale: 1.0
  Root Motion: True (lock: AnimFirstFrame)
  Bone Tracks: 65
  Skeleton: /Game/Characters/SK_Mannequin
```

```
> search_animations --anim_type AnimMontage --folder /Game/Combat

Found 12 animations:
  [AnimMontage] AM_Attack_Light  (/Game/Combat/AM_Attack_Light)
  [AnimMontage] AM_Attack_Heavy  (/Game/Combat/AM_Attack_Heavy)
  ...
```

## License

MIT
