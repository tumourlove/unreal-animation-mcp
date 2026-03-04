"""Animation helper functions executed inside Unreal Editor Python.

This module is uploaded to {project}/Saved/AnimationMCP/ and imported
by the MCP server's scripts. It wraps unreal.AnimationLibrary and
direct property access into JSON-returning functions.
"""

import json
import unreal


def _json_result(data: dict) -> str:
    """Return JSON string with success=True merged in."""
    data["success"] = True
    return json.dumps(data, default=str)


def _json_error(msg: str) -> str:
    """Return JSON error string."""
    return json.dumps({"success": False, "error": msg})


def _load_asset(asset_path: str):
    """Load an asset by path, return (asset, error_string)."""
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if asset is None:
        return None, f"Asset not found: {asset_path}"
    return asset, None


# ---------------------------------------------------------------------------
# AnimSequence inspection
# ---------------------------------------------------------------------------

def get_anim_sequence_info(asset_path):
    """Core metadata for an AnimSequence."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary

    data = {
        "asset_path": asset_path,
        "asset_type": asset.get_class().get_name(),
        "length": lib.get_sequence_length(asset),
        "num_frames": lib.get_num_frames(asset),
        "num_keys": lib.get_num_keys(asset),
        "rate_scale": lib.get_rate_scale(asset),
        "interpolation_type": str(lib.get_animation_interpolation_type(asset)),
        "additive_type": str(lib.get_additive_animation_type(asset)),
        "root_motion_enabled": lib.is_root_motion_enabled(asset),
        "root_motion_lock_type": str(lib.get_root_motion_lock_type(asset)),
        "track_names": [str(n) for n in lib.get_animation_track_names(asset)],
        "track_count": len(lib.get_animation_track_names(asset)),
    }

    # Skeleton reference
    skel = asset.get_editor_property("skeleton")
    if skel:
        data["skeleton"] = skel.get_path_name()

    return _json_result(data)


def get_anim_notifies(asset_path):
    """All notifies on an animation asset."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary
    events = lib.get_animation_notify_events(asset)
    track_names = [str(n) for n in lib.get_animation_notify_track_names(asset)]

    notifies = []
    for i, evt in enumerate(events):
        notify_data = {
            "index": i,
            "name": str(evt.get_editor_property("notify_name")),
            "trigger_time": evt.get_trigger_time(),
            "duration": evt.get_duration(),
            "track_index": evt.get_editor_property("track_index"),
            "trigger_weight_threshold": evt.get_editor_property("trigger_weight_threshold"),
            "trigger_chance": evt.get_editor_property("notify_trigger_chance"),
            "montage_tick_type": str(evt.get_editor_property("montage_tick_type")),
        }

        # Notify class info
        notify_obj = evt.get_editor_property("notify")
        state_obj = evt.get_editor_property("notify_state_class")
        if notify_obj:
            notify_data["type"] = "notify"
            notify_data["class"] = notify_obj.get_class().get_name()
        elif state_obj:
            notify_data["type"] = "notify_state"
            notify_data["class"] = state_obj.get_class().get_name()
            notify_data["end_time"] = evt.get_end_trigger_time()
        else:
            notify_data["type"] = "named"

        notifies.append(notify_data)

    return _json_result({
        "asset_path": asset_path,
        "notify_count": len(notifies),
        "track_names": track_names,
        "notifies": notifies,
    })


def get_anim_curves(asset_path, curve_type=None):
    """All curves on an animation sequence."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary
    curves = []

    for ct_name, ct_enum in [
        ("float", unreal.RawCurveTrackTypes.RCT_FLOAT),
        ("vector", unreal.RawCurveTrackTypes.RCT_VECTOR),
        ("transform", unreal.RawCurveTrackTypes.RCT_TRANSFORM),
    ]:
        if curve_type and curve_type != ct_name:
            continue
        names = lib.get_animation_curve_names(asset, ct_enum)
        for name in names:
            curve_data = {"name": str(name), "type": ct_name}
            if ct_name == "float":
                keys = lib.get_float_keys(asset, name)
                curve_data["key_count"] = len(keys) if keys else 0
            curves.append(curve_data)

    return _json_result({
        "asset_path": asset_path,
        "curve_count": len(curves),
        "curves": curves,
    })


def get_bone_tracks(asset_path, bone_name=None):
    """Bone track names, or keys for a specific bone."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary
    track_names = [str(n) for n in lib.get_animation_track_names(asset)]

    if bone_name is None:
        return _json_result({
            "asset_path": asset_path,
            "track_count": len(track_names),
            "tracks": track_names,
        })

    # Get keys for specific bone
    if not lib.is_valid_raw_animation_track_name(asset, bone_name):
        return _json_error(f"Bone track not found: {bone_name}")

    positions = lib.get_raw_track_position_data(asset, bone_name)
    rotations = lib.get_raw_track_rotation_data(asset, bone_name)
    scales = lib.get_raw_track_scale_data(asset, bone_name)

    return _json_result({
        "asset_path": asset_path,
        "bone_name": bone_name,
        "position_keys": len(positions) if positions else 0,
        "rotation_keys": len(rotations) if rotations else 0,
        "scale_keys": len(scales) if scales else 0,
    })


def get_bone_pose_at_time(asset_path, bone_names, time):
    """Bone transforms at a specific time."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary
    poses = []

    for bone_name in bone_names:
        transform = lib.get_bone_pose_for_time(asset, bone_name, time, False)
        loc = transform.translation
        rot = transform.rotation.rotator()
        scale = transform.scale3d
        poses.append({
            "bone": bone_name,
            "location": {"x": loc.x, "y": loc.y, "z": loc.z},
            "rotation": {"pitch": rot.pitch, "yaw": rot.yaw, "roll": rot.roll},
            "scale": {"x": scale.x, "y": scale.y, "z": scale.z},
        })

    return _json_result({
        "asset_path": asset_path,
        "time": time,
        "poses": poses,
    })


def get_sync_markers(asset_path):
    """Sync markers on an animation sequence."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary
    markers = lib.get_animation_sync_markers(asset)
    unique_names = [str(n) for n in lib.get_unique_marker_names(asset)]

    marker_list = []
    for m in markers:
        marker_list.append({
            "name": str(m.marker_name),
            "time": m.time,
        })

    return _json_result({
        "asset_path": asset_path,
        "unique_names": unique_names,
        "marker_count": len(marker_list),
        "markers": marker_list,
    })


# ---------------------------------------------------------------------------
# AnimMontage inspection
# ---------------------------------------------------------------------------

def get_montage_info(asset_path):
    """Core metadata for an AnimMontage."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary

    blend_in = asset.get_editor_property("blend_in")
    blend_out = asset.get_editor_property("blend_out")

    data = {
        "asset_path": asset_path,
        "asset_type": "AnimMontage",
        "sequence_length": asset.get_editor_property("sequence_length"),
        "rate_scale": asset.get_editor_property("rate_scale"),
        "num_sections": asset.get_num_sections(),
        "auto_blend_out": asset.get_editor_property("enable_auto_blend_out"),
        "blend_in_time": asset.get_default_blend_in_time(),
        "blend_out_time": asset.get_default_blend_out_time(),
        "blend_out_trigger_time": asset.get_editor_property("blend_out_trigger_time"),
        "blend_mode_in": str(asset.get_editor_property("blend_mode_in")),
        "blend_mode_out": str(asset.get_editor_property("blend_mode_out")),
        "sync_group": str(asset.get_editor_property("sync_group")),
        "slot_names": [str(n) for n in lib.get_montage_slot_names(asset)],
    }

    skel = asset.get_editor_property("skeleton")
    if skel:
        data["skeleton"] = skel.get_path_name()

    return _json_result(data)


def get_montage_sections(asset_path):
    """Detailed section list for a montage."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    sections = []
    for i in range(asset.get_num_sections()):
        name = str(asset.get_section_name(i))
        section_data = {
            "index": i,
            "name": name,
        }
        sections.append(section_data)

    return _json_result({
        "asset_path": asset_path,
        "section_count": len(sections),
        "sections": sections,
    })


def get_montage_slots(asset_path):
    """Slot tracks with animation segments."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary
    slot_names = [str(n) for n in lib.get_montage_slot_names(asset)]

    return _json_result({
        "asset_path": asset_path,
        "slot_count": len(slot_names),
        "slots": slot_names,
    })


# ---------------------------------------------------------------------------
# BlendSpace inspection
# ---------------------------------------------------------------------------

def get_blendspace_info(asset_path):
    """Core metadata for a BlendSpace."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    class_name = asset.get_class().get_name()
    is_1d = "BlendSpace1D" in class_name

    data = {
        "asset_path": asset_path,
        "asset_type": class_name,
        "is_1d": is_1d,
        "sample_count": len(asset.get_editor_property("sample_data")),
        "notify_trigger_mode": str(asset.get_editor_property("notify_trigger_mode")),
        "loop": asset.get_editor_property("loop"),
    }

    skel = asset.get_editor_property("skeleton")
    if skel:
        data["skeleton"] = skel.get_path_name()

    return _json_result(data)


def get_blendspace_samples(asset_path):
    """All sample points in a BlendSpace."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    samples_raw = asset.get_editor_property("sample_data")
    samples = []
    for i, sample in enumerate(samples_raw):
        anim = sample.get_editor_property("animation")
        val = sample.get_editor_property("sample_value")
        samples.append({
            "index": i,
            "animation": anim.get_path_name() if anim else None,
            "x": val.x,
            "y": val.y,
        })

    return _json_result({
        "asset_path": asset_path,
        "sample_count": len(samples),
        "samples": samples,
    })


# ---------------------------------------------------------------------------
# Skeleton & SkeletalMesh inspection
# ---------------------------------------------------------------------------

def get_skeleton_info(asset_path):
    """Bone hierarchy and metadata for a Skeleton."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    # Get bone names via the reference pose
    ref_skeleton = asset.get_editor_property("reference_skeleton") if hasattr(asset, "reference_skeleton") else None

    # Use compatible skeletons list
    compatible = asset.get_editor_property("compatible_skeletons")
    compat_list = [str(s.get_path_name()) for s in compatible] if compatible else []

    return _json_result({
        "asset_path": asset_path,
        "compatible_skeletons": compat_list,
    })


def get_skeletal_mesh_info(asset_path):
    """Metadata for a SkeletalMesh."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    morph_names = [str(n) for n in asset.get_all_morph_target_names()]
    skel = asset.get_editor_property("skeleton")

    sockets = []
    for i in range(asset.num_sockets()):
        sock = asset.get_socket_by_index(i)
        if sock:
            sockets.append({
                "name": str(sock.socket_name),
                "bone": str(sock.bone_name),
            })

    return _json_result({
        "asset_path": asset_path,
        "skeleton": skel.get_path_name() if skel else None,
        "morph_target_count": len(morph_names),
        "morph_targets": morph_names,
        "socket_count": len(sockets),
        "sockets": sockets,
        "lod_count": len(asset.get_editor_property("lod_info")),
    })


# ---------------------------------------------------------------------------
# AnimBlueprint inspection (Python-native)
# ---------------------------------------------------------------------------

def get_abp_info(asset_path):
    """Core metadata for an AnimBlueprint."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    skel = asset.get_editor_property("target_skeleton")

    return _json_result({
        "asset_path": asset_path,
        "target_skeleton": skel.get_path_name() if skel else None,
        "is_template": asset.get_editor_property("is_template"),
        "multi_threaded_update": asset.get_editor_property("use_multi_threaded_animation_update"),
        "linked_layer_sharing": asset.get_editor_property("enable_linked_anim_layer_instance_sharing"),
    })


def get_abp_graphs(asset_path):
    """List animation graphs in an ABP."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    # Access via AnimationLibrary
    lib = unreal.AnimationLibrary
    graphs = lib.get_animation_graphs(asset)

    graph_list = []
    for g in graphs:
        graph_list.append({
            "name": g.get_name(),
        })

    return _json_result({
        "asset_path": asset_path,
        "graph_count": len(graph_list),
        "graphs": graph_list,
    })


def get_abp_nodes(asset_path, node_class=None):
    """Enumerate anim graph nodes by class."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary

    if node_class:
        cls = getattr(unreal, node_class, None)
        if cls is None:
            return _json_error(f"Unknown node class: {node_class}")
        nodes = lib.get_nodes_of_class(asset, cls, True)
    else:
        nodes = lib.get_nodes_of_class(asset, unreal.AnimGraphNode_Base, True)

    node_list = []
    for n in nodes:
        node_list.append({
            "class": n.get_class().get_name(),
            "name": n.get_name(),
            "title": n.get_node_title(unreal.NodeTitleType.FULL_TITLE) if hasattr(n, 'get_node_title') else str(n.get_name()),
        })

    return _json_result({
        "asset_path": asset_path,
        "node_count": len(node_list),
        "filter_class": node_class,
        "nodes": node_list,
    })


def get_abp_asset_overrides(asset_path):
    """Parent node asset overrides in an ABP."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    overrides = asset.get_editor_property("parent_asset_overrides")
    override_list = []
    for o in overrides:
        override_list.append({
            "guid": str(o.get_editor_property("parent_node_guid")),
            "new_asset": str(o.get_editor_property("new_asset")),
        })

    return _json_result({
        "asset_path": asset_path,
        "override_count": len(override_list),
        "overrides": override_list,
    })
