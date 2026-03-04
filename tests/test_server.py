"""Tests for the Animation MCP server."""

import json
from unittest.mock import MagicMock, patch

import pytest

from unreal_animation_mcp import server


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset server singletons before and after each test."""
    server._reset_state()
    yield
    server._reset_state()


def _setup_tool_mock(return_data: dict):
    """Configure server with mocked bridge returning return_data."""
    server._project_path = "/tmp/TestProject"
    server._helper_uploaded = False
    server._helper_hash = ""

    mock_bridge = MagicMock()
    mock_bridge.run_command.side_effect = [
        {"success": True, "output": "helper_uploaded"},
        {"success": True, "output": json.dumps(return_data)},
    ]
    server._bridge = mock_bridge


def _setup_plugin_mock(return_data: dict):
    """Configure server with mocked bridge for C++ plugin calls (no helper upload)."""
    server._project_path = "/tmp/TestProject"
    mock_bridge = MagicMock()
    mock_bridge.run_command.return_value = {"success": True, "output": json.dumps(return_data)}
    server._bridge = mock_bridge


class TestServerInit:
    def test_reset_state_clears_bridge(self):
        server._bridge = MagicMock()
        server._reset_state()
        assert server._bridge is None

    def test_get_bridge_creates_lazily(self):
        bridge = server._get_bridge()
        assert bridge is not None
        assert server._bridge is bridge

    @patch.object(server, "_get_bridge")
    @patch.object(server, "_get_helper_source", return_value="# helper\n")
    def test_ensure_helper_uploaded(self, _src, mock_get_bridge):
        mock_bridge = MagicMock()
        mock_get_bridge.return_value = mock_bridge
        server._project_path = "/tmp/TestProject"
        server._ensure_helper_uploaded()
        mock_bridge.run_command.assert_called_once()
        assert server._helper_uploaded is True

    @patch.object(server, "_get_bridge")
    @patch.object(server, "_get_helper_source", return_value="# helper\n")
    def test_skip_upload_when_already_done(self, _src, mock_get_bridge):
        mock_bridge = MagicMock()
        mock_get_bridge.return_value = mock_bridge
        server._helper_uploaded = True
        server._ensure_helper_uploaded()
        mock_bridge.run_command.assert_not_called()


# ===========================================================================
# Tier 1: Inspection Tools
# ===========================================================================

class TestSequenceInspection:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_anim_sequence_info(self, _src):
        _setup_tool_mock({
            "success": True,
            "asset_path": "/Game/Anims/AS_Run",
            "length": 1.5,
            "num_frames": 45,
            "rate_scale": 1.0,
            "interpolation_type": "Linear",
            "additive_type": "NoAdditive",
            "root_motion_enabled": True,
            "root_motion_lock_type": "AnimFirstFrame",
            "track_count": 65,
            "skeleton": "/Game/Skel/SK_Mannequin",
        })
        result = server.get_anim_sequence_info("/Game/Anims/AS_Run")
        assert "1.5s" in result
        assert "45 frames" in result
        assert "Root Motion: True" in result
        assert "SK_Mannequin" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_anim_sequence_info_error(self, _src):
        _setup_tool_mock({"success": False, "error": "Asset not found"})
        result = server.get_anim_sequence_info("/Game/Missing")
        assert "Error" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_anim_notifies(self, _src):
        _setup_tool_mock({
            "success": True,
            "asset_path": "/Game/Anims/AS_Run",
            "notify_count": 2,
            "track_names": ["Default"],
            "notifies": [
                {"index": 0, "name": "FootStep", "trigger_time": 0.3, "type": "notify", "class": "AnimNotify_PlaySound"},
                {"index": 1, "name": "Trail", "trigger_time": 0.5, "duration": 0.4, "type": "notify_state", "class": "AnimNotifyState_Trail"},
            ],
        })
        result = server.get_anim_notifies("/Game/Anims/AS_Run")
        assert "FootStep" in result
        assert "0.3s" in result
        assert "Trail" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_anim_curves(self, _src):
        _setup_tool_mock({
            "success": True, "curve_count": 1,
            "curves": [{"name": "Weight", "type": "float", "key_count": 10}],
        })
        result = server.get_anim_curves("/Game/Anims/AS_Run")
        assert "Weight" in result
        assert "10 keys" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_bone_tracks_list(self, _src):
        _setup_tool_mock({
            "success": True, "track_count": 3,
            "tracks": ["root", "pelvis", "spine_01"],
        })
        result = server.get_bone_tracks("/Game/Anims/AS_Run")
        assert "root" in result
        assert "pelvis" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_bone_tracks_specific(self, _src):
        _setup_tool_mock({
            "success": True, "bone_name": "root",
            "position_keys": 45, "rotation_keys": 45, "scale_keys": 1,
        })
        result = server.get_bone_tracks("/Game/Anims/AS_Run", bone_name="root")
        assert "Position keys: 45" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_bone_pose_at_time(self, _src):
        _setup_tool_mock({
            "success": True, "time": 0.5,
            "poses": [{"bone": "root", "location": {"x": 0, "y": 0, "z": 90}, "rotation": {"pitch": 0, "yaw": 0, "roll": 0}, "scale": {"x": 1, "y": 1, "z": 1}}],
        })
        result = server.get_bone_pose_at_time("/Game/Anims/AS_Run", ["root"], 0.5)
        assert "root" in result
        assert "0.5s" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_sync_markers(self, _src):
        _setup_tool_mock({
            "success": True, "marker_count": 1,
            "unique_names": ["FootSync"],
            "markers": [{"name": "FootSync", "time": 0.25}],
        })
        result = server.get_sync_markers("/Game/Anims/AS_Run")
        assert "FootSync" in result


class TestMontageInspection:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_montage_info(self, _src):
        _setup_tool_mock({
            "success": True, "asset_path": "/Game/Montages/AM_Attack",
            "sequence_length": 2.0, "rate_scale": 1.0, "num_sections": 3,
            "auto_blend_out": True, "blend_in_time": 0.25, "blend_out_time": 0.25,
            "blend_out_trigger_time": -1.0, "slot_names": ["DefaultSlot"],
            "skeleton": "/Game/Skel/SK_Mannequin",
        })
        result = server.get_montage_info("/Game/Montages/AM_Attack")
        assert "2.0s" in result
        assert "Sections: 3" in result
        assert "DefaultSlot" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_montage_sections(self, _src):
        _setup_tool_mock({
            "success": True, "section_count": 2,
            "sections": [{"index": 0, "name": "Default"}, {"index": 1, "name": "Loop"}],
        })
        result = server.get_montage_sections("/Game/Montages/AM_Attack")
        assert "Default" in result
        assert "Loop" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_montage_slots(self, _src):
        _setup_tool_mock({
            "success": True, "slot_count": 1, "slots": ["DefaultSlot"],
        })
        result = server.get_montage_slots("/Game/Montages/AM_Attack")
        assert "DefaultSlot" in result


class TestBlendSpaceInspection:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_blendspace_info(self, _src):
        _setup_tool_mock({
            "success": True, "asset_type": "BlendSpace", "is_1d": False,
            "sample_count": 9, "loop": True,
            "skeleton": "/Game/Skel/SK_Mannequin",
        })
        result = server.get_blendspace_info("/Game/BS/BS_Locomotion")
        assert "Samples: 9" in result
        assert "2D" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_blendspace_samples(self, _src):
        _setup_tool_mock({
            "success": True, "sample_count": 2,
            "samples": [
                {"index": 0, "animation": "/Game/Anims/AS_Idle", "x": 0.0, "y": 0.0},
                {"index": 1, "animation": "/Game/Anims/AS_Run", "x": 300.0, "y": 0.0},
            ],
        })
        result = server.get_blendspace_samples("/Game/BS/BS_Locomotion")
        assert "AS_Idle" in result
        assert "AS_Run" in result


class TestSkeletonInspection:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_skeleton_info(self, _src):
        _setup_tool_mock({
            "success": True, "asset_path": "/Game/Skel/SK_Mannequin",
            "compatible_skeletons": [],
        })
        result = server.get_skeleton_info("/Game/Skel/SK_Mannequin")
        assert "SK_Mannequin" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_skeletal_mesh_info(self, _src):
        _setup_tool_mock({
            "success": True, "skeleton": "/Game/Skel/SK_Mannequin",
            "morph_target_count": 5, "socket_count": 2, "lod_count": 3,
        })
        result = server.get_skeletal_mesh_info("/Game/Mesh/SK_Mannequin")
        assert "Morph Targets: 5" in result
        assert "Sockets: 2" in result
        assert "LODs: 3" in result


class TestABPInspection:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_abp_info(self, _src):
        _setup_tool_mock({
            "success": True, "target_skeleton": "/Game/Skel/SK_Mannequin",
            "is_template": False, "multi_threaded_update": True,
            "linked_layer_sharing": False,
        })
        result = server.get_abp_info("/Game/ABP/ABP_Hero")
        assert "SK_Mannequin" in result
        assert "Multi-threaded Update: True" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_abp_graphs(self, _src):
        _setup_tool_mock({
            "success": True, "graph_count": 2,
            "graphs": [{"name": "AnimGraph"}, {"name": "EventGraph"}],
        })
        result = server.get_abp_graphs("/Game/ABP/ABP_Hero")
        assert "AnimGraph" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_abp_nodes(self, _src):
        _setup_tool_mock({
            "success": True, "node_count": 3,
            "nodes": [
                {"class": "AnimGraphNode_StateMachine", "name": "SM_Main", "title": "State Machine"},
                {"class": "AnimGraphNode_BlendListByBool", "name": "Blend", "title": "Blend by Bool"},
                {"class": "AnimGraphNode_Output", "name": "Output", "title": "Output Pose"},
            ],
        })
        result = server.get_abp_nodes("/Game/ABP/ABP_Hero")
        assert "State Machine" in result
        assert "3" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_abp_asset_overrides(self, _src):
        _setup_tool_mock({
            "success": True, "override_count": 0, "overrides": [],
        })
        result = server.get_abp_asset_overrides("/Game/ABP/ABP_Hero")
        assert "0" in result


class TestABPPluginInspection:
    def test_get_abp_state_machines(self):
        _setup_plugin_mock({
            "success": True, "asset_path": "/Game/ABP/ABP_Hero", "count": 1,
            "state_machines": [{
                "name": "Locomotion", "graph": "AnimGraph",
                "entry_state": "Idle", "state_count": 3, "transition_count": 4,
                "states": [{"name": "Idle"}, {"name": "Walk"}, {"name": "Run"}],
                "transitions": [
                    {"from": "Idle", "to": "Walk", "blend_mode": "Linear", "cross_fade_duration": 0.2},
                ],
            }],
        })
        result = server.get_abp_state_machines("/Game/ABP/ABP_Hero")
        assert "Locomotion" in result
        assert "Idle" in result
        assert "Walk" in result

    def test_get_abp_state_info(self):
        _setup_plugin_mock({
            "success": True, "state_name": "Idle", "machine_name": "Locomotion",
            "node_count": 2,
            "nodes": [
                {"class": "AnimGraphNode_SequencePlayer", "title": "Play AS_Idle"},
                {"class": "AnimGraphNode_Output", "title": "Output"},
            ],
        })
        result = server.get_abp_state_info("/Game/ABP/ABP_Hero", "Locomotion", "Idle")
        assert "Play AS_Idle" in result

    def test_get_abp_transitions(self):
        _setup_plugin_mock({
            "success": True, "machine_name": "Locomotion", "count": 2,
            "transitions": [
                {"from": "Idle", "to": "Walk", "cross_fade_duration": 0.2, "blend_mode": "Linear", "bidirectional": False, "rule_nodes": []},
                {"from": "Walk", "to": "Idle", "cross_fade_duration": 0.2, "blend_mode": "Linear", "bidirectional": False, "rule_nodes": []},
            ],
        })
        result = server.get_abp_transitions("/Game/ABP/ABP_Hero", "Locomotion")
        assert "Idle" in result
        assert "Walk" in result

    def test_get_abp_blend_nodes(self):
        _setup_plugin_mock({
            "success": True, "graph_name": "AnimGraph", "count": 2,
            "nodes": [
                {"class": "AnimGraphNode_BlendListByBool", "title": "Blend", "connected_pins": [{"name": "Input", "direction": "Input", "connections": 1}]},
                {"class": "AnimGraphNode_Output", "title": "Output", "connected_pins": []},
            ],
        })
        result = server.get_abp_blend_nodes("/Game/ABP/ABP_Hero", "AnimGraph")
        assert "Blend" in result

    def test_get_abp_linked_layers(self):
        _setup_plugin_mock({
            "success": True, "count": 0, "linked_layers": [],
        })
        result = server.get_abp_linked_layers("/Game/ABP/ABP_Hero")
        assert "0" in result


# ===========================================================================
# Tier 2: Editing Tools
# ===========================================================================

class TestNotifyEditing:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_add_notify(self, _src):
        _setup_tool_mock({"success": True, "asset_path": "/Game/Anims/AS_Run", "time": 0.5, "class": "AnimNotify_PlaySound"})
        result = server.add_notify("/Game/Anims/AS_Run", "Default", 0.5, "AnimNotify_PlaySound")
        assert "AnimNotify_PlaySound" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_add_notify_state(self, _src):
        _setup_tool_mock({"success": True})
        result = server.add_notify_state("/Game/Anims/AS_Run", "Default", 0.5, 0.3, "AnimNotifyState_Trail")
        assert "AnimNotifyState_Trail" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_remove_notifies(self, _src):
        _setup_tool_mock({"success": True, "removed_by": "FootStep"})
        result = server.remove_notifies("/Game/Anims/AS_Run", notify_name="FootStep")
        assert "FootStep" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_add_notify_track(self, _src):
        _setup_tool_mock({"success": True, "track_name": "SFX"})
        result = server.add_notify_track("/Game/Anims/AS_Run", "SFX")
        assert "SFX" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_remove_notify_track(self, _src):
        _setup_tool_mock({"success": True})
        result = server.remove_notify_track("/Game/Anims/AS_Run", "SFX")
        assert "SFX" in result

    def test_set_notify_time(self):
        _setup_plugin_mock({"success": True, "index": 0, "new_time": 0.7})
        result = server.set_notify_time("/Game/Anims/AS_Run", 0, 0.7)
        assert "0.7s" in result

    def test_set_notify_duration(self):
        _setup_plugin_mock({"success": True, "index": 1, "new_duration": 0.5})
        result = server.set_notify_duration("/Game/Anims/AS_Run", 1, 0.5)
        assert "0.5s" in result


class TestCurveEditing:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_add_curve(self, _src):
        _setup_tool_mock({"success": True, "curve_name": "Weight", "type": "float"})
        result = server.add_curve("/Game/Anims/AS_Run", "Weight", "float")
        assert "Weight" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_add_curve_keys(self, _src):
        _setup_tool_mock({"success": True, "key_count": 3})
        result = server.add_curve_keys("/Game/Anims/AS_Run", "Weight", [0.0, 0.5, 1.0], [0.0, 1.0, 0.0])
        assert "3 keys" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_remove_curve(self, _src):
        _setup_tool_mock({"success": True})
        result = server.remove_curve("/Game/Anims/AS_Run", "Weight")
        assert "Weight" in result


class TestSyncMarkerEditing:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_add_sync_marker(self, _src):
        _setup_tool_mock({"success": True})
        result = server.add_sync_marker("/Game/Anims/AS_Run", "FootSync", 0.25, "Default")
        assert "FootSync" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_remove_sync_markers(self, _src):
        _setup_tool_mock({"success": True})
        result = server.remove_sync_markers("/Game/Anims/AS_Run", marker_name="FootSync")
        assert "FootSync" in result


class TestPropertyEditing:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_set_root_motion(self, _src):
        _setup_tool_mock({"success": True})
        result = server.set_root_motion("/Game/Anims/AS_Run", True)
        assert "enabled" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_set_rate_scale(self, _src):
        _setup_tool_mock({"success": True})
        result = server.set_rate_scale("/Game/Anims/AS_Run", 1.5)
        assert "1.5" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_set_additive_type(self, _src):
        _setup_tool_mock({"success": True})
        result = server.set_additive_type("/Game/Anims/AS_Run", "AAT_LocalSpaceBase")
        assert "AAT_LocalSpaceBase" in result


class TestVirtualBoneEditing:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_add_virtual_bone(self, _src):
        _setup_tool_mock({"success": True})
        result = server.add_virtual_bone("/Game/Skel/SK_Mannequin", "hand_r", "hand_l")
        assert "hand_r" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_remove_virtual_bones(self, _src):
        _setup_tool_mock({"success": True})
        result = server.remove_virtual_bones("/Game/Skel/SK_Mannequin")
        assert "all" in result


class TestMiscEditing:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_copy_notifies(self, _src):
        _setup_tool_mock({"success": True})
        result = server.copy_notifies("/Game/Anims/AS_Run", "/Game/Anims/AS_Walk")
        assert "AS_Run" in result
        assert "AS_Walk" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_set_montage_blend(self, _src):
        _setup_tool_mock({"success": True, "updated": True})
        result = server.set_montage_blend("/Game/Montages/AM_Attack", blend_in_time=0.3)
        assert "Updated" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_add_meta_data(self, _src):
        _setup_tool_mock({"success": True})
        result = server.add_meta_data("/Game/Anims/AS_Run", "AnimMetaData_Test")
        assert "AnimMetaData_Test" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_remove_meta_data(self, _src):
        _setup_tool_mock({"success": True})
        result = server.remove_meta_data("/Game/Anims/AS_Run")
        assert "all" in result


class TestMontageSectionEditing:
    def test_add_montage_section(self):
        _setup_plugin_mock({"success": True, "section_name": "Attack", "index": 2, "start_time": 0.5})
        result = server.add_montage_section("/Game/Montages/AM_Attack", "Attack", 0.5)
        assert "Attack" in result
        assert "0.5s" in result

    def test_delete_montage_section(self):
        _setup_plugin_mock({"success": True, "deleted_section": "Loop", "index": 1})
        result = server.delete_montage_section("/Game/Montages/AM_Attack", 1)
        assert "Loop" in result

    def test_set_section_next(self):
        _setup_plugin_mock({"success": True})
        result = server.set_section_next("/Game/Montages/AM_Attack", "Default", "Loop")
        assert "Default" in result
        assert "Loop" in result

    def test_set_section_time(self):
        _setup_plugin_mock({"success": True})
        result = server.set_section_time("/Game/Montages/AM_Attack", "Loop", 1.5)
        assert "1.5s" in result


class TestBlendSpaceEditing:
    def test_add_blendspace_sample(self):
        _setup_plugin_mock({"success": True, "index": 3})
        result = server.add_blendspace_sample("/Game/BS/BS_Loco", "/Game/Anims/AS_Run", 300.0, 0.0)
        assert "AS_Run" in result

    def test_edit_blendspace_sample(self):
        _setup_plugin_mock({"success": True})
        result = server.edit_blendspace_sample("/Game/BS/BS_Loco", 0, 150.0, 0.0)
        assert "150.0" in result

    def test_delete_blendspace_sample(self):
        _setup_plugin_mock({"success": True, "deleted_index": 2})
        result = server.delete_blendspace_sample("/Game/BS/BS_Loco", 2)
        assert "2" in result


class TestBoneTrackEditing:
    def test_add_bone_track(self):
        _setup_plugin_mock({"success": True, "bone_name": "custom_bone"})
        result = server.add_bone_track("/Game/Anims/AS_Run", "custom_bone")
        assert "custom_bone" in result

    def test_remove_bone_track(self):
        _setup_plugin_mock({"success": True})
        result = server.remove_bone_track("/Game/Anims/AS_Run", "custom_bone")
        assert "custom_bone" in result

    def test_set_bone_track_keys(self):
        _setup_plugin_mock({"success": True, "num_keys": 2})
        result = server.set_bone_track_keys(
            "/Game/Anims/AS_Run", "root",
            "[[0,0,0],[0,0,10]]", "[[0,0,0,1],[0,0,0,1]]", "[[1,1,1],[1,1,1]]"
        )
        assert "2 keys" in result


# ===========================================================================
# Tier 3: Search & Analysis Tools
# ===========================================================================

class TestSearchTools:
    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_search_animations(self, _src):
        _setup_tool_mock({
            "success": True, "count": 2,
            "results": [
                {"name": "AS_Run", "path": "/Game/Anims/AS_Run", "class": "AnimSequence"},
                {"name": "AS_Walk", "path": "/Game/Anims/AS_Walk", "class": "AnimSequence"},
            ],
        })
        result = server.search_animations(query="Run")
        assert "AS_Run" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_search_animations_empty(self, _src):
        _setup_tool_mock({"success": True, "count": 0, "results": []})
        result = server.search_animations(query="Nonexistent")
        assert "No animations found" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_search_by_notify(self, _src):
        _setup_tool_mock({
            "success": True, "count": 1,
            "matches": [{"asset": "/Game/Anims/AS_Run", "notify": "FootStep", "class": "AnimNotify_PlaySound"}],
        })
        result = server.search_by_notify(notify_name="FootStep")
        assert "FootStep" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_search_by_curve(self, _src):
        _setup_tool_mock({
            "success": True, "count": 1,
            "matches": [{"asset": "/Game/Anims/AS_Run", "curve": "Weight"}],
        })
        result = server.search_by_curve("Weight")
        assert "AS_Run" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_search_by_slot(self, _src):
        _setup_tool_mock({
            "success": True, "count": 1,
            "matches": [{"asset": "/Game/Montages/AM_Attack", "slots": ["DefaultSlot"]}],
        })
        result = server.search_by_slot("DefaultSlot")
        assert "AM_Attack" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_audit_notifies(self, _src):
        _setup_tool_mock({
            "success": True, "assets_checked": 10, "unique_notifies": 5,
            "notify_frequencies": [{"name": "FootStep", "count": 8}],
            "issues": [{"asset": "/Game/Anims/AS_Bad", "notify": "Dead", "issue": "0% trigger chance"}],
        })
        result = server.audit_notifies(folder="/Game/Anims")
        assert "FootStep" in result
        assert "0% trigger chance" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_audit_blendspace(self, _src):
        _setup_tool_mock({
            "success": True, "sample_count": 9,
            "samples": [], "duplicate_positions": [{"index_a": 2, "index_b": 5}],
        })
        result = server.audit_blendspace("/Game/BS/BS_Loco")
        assert "Duplicate" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_compare_animations(self, _src):
        _setup_tool_mock({
            "success": True, "path_a": "/Game/Anims/AS_Run", "path_b": "/Game/Anims/AS_Walk",
            "differences": [{"property": "length", "a": 1.5, "b": 2.0}],
        })
        result = server.compare_animations("/Game/Anims/AS_Run", "/Game/Anims/AS_Walk")
        assert "length" in result

    @patch.object(server, "_get_helper_source", return_value="# src\n")
    def test_get_animation_summary(self, _src):
        _setup_tool_mock({
            "success": True, "folder": "/Game/Anims",
            "total_assets": 50,
            "type_counts": {"AnimSequence": 30, "AnimMontage": 15, "BlendSpace": 5},
        })
        result = server.get_animation_summary("/Game/Anims")
        assert "50" in result
        assert "AnimSequence: 30" in result
