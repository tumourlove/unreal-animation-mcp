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


def _get_curve_type_map():
    """Build available RawCurveTrackTypes map, skipping enums missing in this UE version."""
    ct_map = {}
    rct = getattr(unreal, "RawCurveTrackTypes", None)
    if rct is None:
        return ct_map
    for name, attr in [("float", "RCT_FLOAT"), ("vector", "RCT_VECTOR"), ("transform", "RCT_TRANSFORM")]:
        val = getattr(rct, attr, None)
        if val is not None:
            ct_map[name] = val
    return ct_map


def get_anim_curves(asset_path, curve_type=None):
    """All curves on an animation sequence."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    lib = unreal.AnimationLibrary
    curves = []
    ct_map = _get_curve_type_map()

    for ct_name, ct_enum in ct_map.items():
        if curve_type and curve_type != ct_name:
            continue
        try:
            names = lib.get_animation_curve_names(asset, ct_enum)
        except Exception:
            continue
        for name in names:
            curve_data = {"name": str(name), "type": ct_name}
            if ct_name == "float":
                try:
                    keys = lib.get_float_keys(asset, name)
                    curve_data["key_count"] = len(keys) if keys else 0
                except Exception:
                    curve_data["key_count"] = -1
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

    # Validate bone name against track list (is_valid_raw_animation_track_name is broken in UE 5.7)
    if bone_name not in track_names:
        return _json_error(f"Bone track not found: {bone_name}. Available: {track_names[:10]}{'...' if len(track_names) > 10 else ''}")

    try:
        positions = lib.get_raw_track_position_data(asset, bone_name)
        rotations = lib.get_raw_track_rotation_data(asset, bone_name)
        scales = lib.get_raw_track_scale_data(asset, bone_name)
    except Exception as e:
        return _json_error(f"Failed to read bone track data for '{bone_name}': {e}")

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
    """Bone hierarchy and metadata for a Skeleton. Delegates to C++ plugin for reliability."""
    # Prefer C++ plugin — avoids Python property crashes
    try:
        result = unreal.AnimationMCPReaderLibrary.get_skeleton_info(asset_path)
        return result
    except Exception:
        pass

    # Fallback: Python approach
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    data = {"asset_path": asset_path}

    # Compatible skeletons
    try:
        compatible = asset.get_editor_property("compatible_skeletons")
        data["compatible_skeletons"] = [str(s.get_path_name()) for s in compatible] if compatible else []
    except Exception:
        data["compatible_skeletons"] = []

    return _json_result(data)


def get_skeletal_mesh_info(asset_path):
    """Metadata for a SkeletalMesh. Delegates to C++ plugin for reliability."""
    # Prefer C++ plugin — avoids lod_info crash in UE 5.7
    try:
        result = unreal.AnimationMCPReaderLibrary.get_skeletal_mesh_info(asset_path)
        return result
    except Exception:
        pass

    # Fallback: Python approach with safe property access
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

    lod_count = -1
    try:
        if hasattr(asset, "get_lod_count"):
            lod_count = asset.get_lod_count()
    except Exception:
        pass

    return _json_result({
        "asset_path": asset_path,
        "skeleton": skel.get_path_name() if skel else None,
        "morph_target_count": len(morph_names),
        "morph_targets": morph_names,
        "socket_count": len(sockets),
        "sockets": sockets,
        "lod_count": lod_count,
    })


# ---------------------------------------------------------------------------
# AnimBlueprint inspection (Python-native)
# ---------------------------------------------------------------------------

def get_abp_info(asset_path):
    """Core metadata for an AnimBlueprint."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    result = {"asset_path": asset_path}

    for prop_name, key in [
        ("target_skeleton", "target_skeleton"),
        ("use_multi_threaded_animation_update", "multi_threaded_update"),
        ("enable_linked_anim_layer_instance_sharing", "linked_layer_sharing"),
    ]:
        try:
            val = asset.get_editor_property(prop_name)
            if hasattr(val, 'get_path_name'):
                val = val.get_path_name()
            result[key] = val
        except Exception:
            result[key] = None

    return _json_result(result)


def get_abp_graphs(asset_path):
    """List animation graphs in an ABP. Delegates to C++ plugin."""
    return unreal.AnimationMCPReaderLibrary.get_graphs(asset_path)


def get_abp_nodes(asset_path, node_class=None):
    """Enumerate anim graph nodes by class. Delegates to C++ plugin."""
    return unreal.AnimationMCPReaderLibrary.get_nodes(asset_path, node_class or "")


def get_abp_asset_overrides(asset_path):
    """Parent node asset overrides in an ABP."""
    asset, err = _load_asset(asset_path)
    if err:
        return _json_error(err)

    override_list = []
    try:
        overrides = asset.get_editor_property("parent_asset_overrides")
        for o in overrides:
            entry = {}
            try:
                entry["guid"] = str(o.get_editor_property("parent_node_guid"))
            except Exception:
                entry["guid"] = "unknown"
            try:
                entry["new_asset"] = str(o.get_editor_property("new_asset"))
            except Exception:
                entry["new_asset"] = "unknown"
            override_list.append(entry)
    except Exception as e:
        # parent_asset_overrides crashes in UE 5.7 — return empty with warning
        return _json_result({
            "asset_path": asset_path,
            "override_count": 0,
            "overrides": [],
            "warning": f"parent_asset_overrides not accessible in this UE version: {e}",
        })

    return _json_result({
        "asset_path": asset_path,
        "override_count": len(override_list),
        "overrides": override_list,
    })


# ---------------------------------------------------------------------------
# Editing — Notifies
# ---------------------------------------------------------------------------

def add_notify(asset_path, track_name, time, notify_class):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    lib = unreal.AnimationLibrary
    cls = getattr(unreal, notify_class, None)
    if cls is None: return _json_error(f"Unknown notify class: {notify_class}")
    result = lib.add_animation_notify_event(asset, track_name, time, cls)
    return _json_result({"asset_path": asset_path, "time": time, "class": notify_class})

def add_notify_state(asset_path, track_name, time, duration, notify_state_class):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    lib = unreal.AnimationLibrary
    cls = getattr(unreal, notify_state_class, None)
    if cls is None: return _json_error(f"Unknown notify state class: {notify_state_class}")
    result = lib.add_animation_notify_state_event(asset, track_name, time, duration, cls)
    return _json_result({"asset_path": asset_path, "time": time, "duration": duration, "class": notify_state_class})

def remove_notifies(asset_path, notify_name=None, track_name=None):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    lib = unreal.AnimationLibrary
    if notify_name:
        lib.remove_animation_notify_events_by_name(asset, notify_name)
    elif track_name:
        lib.remove_animation_notify_events_by_track(asset, track_name)
    return _json_result({"asset_path": asset_path, "removed_by": notify_name or track_name})

def add_notify_track(asset_path, track_name, color=None):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    lib = unreal.AnimationLibrary
    c = unreal.LinearColor(r=1, g=1, b=1, a=1) if color is None else unreal.LinearColor(**color)
    lib.add_animation_notify_track(asset, track_name, c)
    return _json_result({"asset_path": asset_path, "track_name": track_name})

def remove_notify_track(asset_path, track_name):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    unreal.AnimationLibrary.remove_animation_notify_track(asset, track_name)
    return _json_result({"asset_path": asset_path, "removed_track": track_name})

# ---------------------------------------------------------------------------
# Editing — Curves
# ---------------------------------------------------------------------------

def add_curve(asset_path, curve_name, curve_type):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    ct_map = _get_curve_type_map()
    ct = ct_map.get(curve_type)
    if ct is None: return _json_error(f"Unknown or unavailable curve type: {curve_type}. Available: {list(ct_map.keys())}")
    unreal.AnimationLibrary.add_curve(asset, curve_name, ct)
    return _json_result({"asset_path": asset_path, "curve_name": curve_name, "type": curve_type})

def add_curve_keys(asset_path, curve_name, times, values):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    unreal.AnimationLibrary.add_float_curve_keys(asset, curve_name, times, values)
    return _json_result({"asset_path": asset_path, "curve_name": curve_name, "key_count": len(times)})

def remove_curve(asset_path, curve_name):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    unreal.AnimationLibrary.remove_curve(asset, curve_name)
    return _json_result({"asset_path": asset_path, "removed_curve": curve_name})

# ---------------------------------------------------------------------------
# Editing — Sync Markers
# ---------------------------------------------------------------------------

def add_sync_marker(asset_path, marker_name, time, track_name):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    unreal.AnimationLibrary.add_animation_sync_marker(asset, marker_name, time, track_name)
    return _json_result({"asset_path": asset_path, "marker_name": marker_name, "time": time})

def remove_sync_markers(asset_path, marker_name=None, track_name=None):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    lib = unreal.AnimationLibrary
    if marker_name:
        lib.remove_animation_sync_markers_by_name(asset, marker_name)
    elif track_name:
        lib.remove_animation_sync_markers_by_track(asset, track_name)
    else:
        lib.remove_all_animation_sync_markers(asset)
    return _json_result({"asset_path": asset_path, "removed_by": marker_name or track_name or "all"})

# ---------------------------------------------------------------------------
# Editing — Properties
# ---------------------------------------------------------------------------

def set_root_motion(asset_path, enabled, lock_type=None):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    lib = unreal.AnimationLibrary
    lib.set_root_motion_enabled(asset, enabled)
    if lock_type is not None:
        lt = getattr(unreal.RootMotionRootLock, lock_type, None)
        if lt: lib.set_root_motion_lock_type(asset, lt)
    return _json_result({"asset_path": asset_path, "root_motion_enabled": enabled})

def set_rate_scale(asset_path, rate_scale):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    unreal.AnimationLibrary.set_rate_scale(asset, rate_scale)
    return _json_result({"asset_path": asset_path, "rate_scale": rate_scale})

def set_additive_type(asset_path, additive_type, base_pose_type=None):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    lib = unreal.AnimationLibrary
    at = getattr(unreal.AdditiveAnimationType, additive_type, None)
    if at: lib.set_additive_animation_type(asset, at)
    if base_pose_type:
        bpt = getattr(unreal.AdditiveBasePoseType, base_pose_type, None)
        if bpt: lib.set_additive_base_pose_type(asset, bpt)
    return _json_result({"asset_path": asset_path, "additive_type": additive_type})

# ---------------------------------------------------------------------------
# Editing — Virtual Bones
# ---------------------------------------------------------------------------

def add_virtual_bone(asset_path, source_bone, target_bone):
    # AnimationLibrary.add_virtual_bone API changed in UE 5.7 — delegate to C++ plugin
    try:
        result = unreal.AnimationMCPReaderLibrary.add_virtual_bone(asset_path, source_bone, target_bone)
        return result
    except Exception:
        pass
    # Fallback: try Python API directly
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    try:
        name = unreal.AnimationLibrary.add_virtual_bone(asset, source_bone, target_bone)
        return _json_result({"asset_path": asset_path, "virtual_bone": str(name), "source": source_bone, "target": target_bone})
    except Exception as e:
        return _json_error(f"add_virtual_bone failed: {e}. Ensure AnimationMCPReader plugin is loaded.")

def remove_virtual_bones(asset_path, bone_names=None):
    # AnimationLibrary.remove_virtual_bones API changed in UE 5.7 — delegate to C++ plugin
    try:
        result = unreal.AnimationMCPReaderLibrary.remove_virtual_bones(asset_path, bone_names or [])
        return result
    except Exception:
        pass
    # Fallback: try Python API directly
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    try:
        lib = unreal.AnimationLibrary
        if bone_names:
            lib.remove_virtual_bones(asset, bone_names)
        else:
            lib.remove_all_virtual_bones(asset)
        return _json_result({"asset_path": asset_path, "removed": bone_names or "all"})
    except Exception as e:
        return _json_error(f"remove_virtual_bones failed: {e}. Ensure AnimationMCPReader plugin is loaded.")

def copy_notifies(source_path, dest_path):
    src, err = _load_asset(source_path)
    if err: return _json_error(err)
    dst, err = _load_asset(dest_path)
    if err: return _json_error(err)
    unreal.AnimationLibrary.copy_anim_notifies_from_sequence(src, dst)
    return _json_result({"source": source_path, "dest": dest_path})

# ---------------------------------------------------------------------------
# Editing — Montage
# ---------------------------------------------------------------------------

def set_montage_blend(asset_path, blend_in_time=None, blend_out_time=None, blend_out_trigger=None, auto_blend_out=None):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    if blend_in_time is not None:
        bi = asset.get_editor_property("blend_in")
        bi.set_editor_property("blend_time", blend_in_time)
        asset.set_editor_property("blend_in", bi)
    if blend_out_time is not None:
        bo = asset.get_editor_property("blend_out")
        bo.set_editor_property("blend_time", blend_out_time)
        asset.set_editor_property("blend_out", bo)
    if blend_out_trigger is not None:
        asset.set_editor_property("blend_out_trigger_time", blend_out_trigger)
    if auto_blend_out is not None:
        asset.set_editor_property("enable_auto_blend_out", auto_blend_out)
    return _json_result({"asset_path": asset_path, "updated": True})

# ---------------------------------------------------------------------------
# Editing — Metadata
# ---------------------------------------------------------------------------

def add_meta_data(asset_path, meta_data_class):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    cls = getattr(unreal, meta_data_class, None)
    if cls is None: return _json_error(f"Unknown metadata class: {meta_data_class}")
    unreal.AnimationLibrary.add_meta_data(asset, cls)
    return _json_result({"asset_path": asset_path, "class": meta_data_class})

def remove_meta_data(asset_path, meta_data_class=None):
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)
    if meta_data_class:
        cls = getattr(unreal, meta_data_class, None)
        items = unreal.AnimationLibrary.get_meta_data_of_class(asset, cls)
        for item in items:
            unreal.AnimationLibrary.remove_meta_data(asset, item)
    else:
        unreal.AnimationLibrary.remove_all_meta_data(asset)
    return _json_result({"asset_path": asset_path, "removed": meta_data_class or "all"})


# ---------------------------------------------------------------------------
# Search & Analysis
# ---------------------------------------------------------------------------

_ANIM_CLASSES = {
    "AnimSequence": "/Script/Engine.AnimSequence",
    "AnimMontage": "/Script/Engine.AnimMontage",
    "BlendSpace": "/Script/Engine.BlendSpace",
    "BlendSpace1D": "/Script/Engine.BlendSpace1D",
    "AnimBlueprint": "/Script/Engine.AnimBlueprint",
}


def search_animations(query=None, anim_type=None, folder=None, skeleton=None):
    """Find animation assets by criteria."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # Build class filter
    class_paths = []
    if anim_type and anim_type in _ANIM_CLASSES:
        parts = _ANIM_CLASSES[anim_type].rsplit(".", 1)
        class_paths.append(unreal.TopLevelAssetPath(parts[0], parts[1]))
    else:
        for cp in _ANIM_CLASSES.values():
            parts = cp.rsplit(".", 1)
            class_paths.append(unreal.TopLevelAssetPath(parts[0], parts[1]))

    filter_kwargs = {"class_paths": class_paths}
    if folder:
        filter_kwargs["package_paths"] = [folder]
        filter_kwargs["recursive_paths"] = True
    ar_filter = unreal.ARFilter(**filter_kwargs)

    assets = registry.get_assets(ar_filter)

    results = []
    for ad in assets:
        name = str(ad.asset_name)
        if query and query.lower() not in name.lower():
            continue
        results.append({
            "name": name,
            "path": str(ad.package_name),
            "class": str(ad.asset_class_path.asset_name),
        })

    return _json_result({"count": len(results), "results": results})


def search_by_notify(notify_name=None, notify_class=None, folder=None):
    """Find animations containing a specific notify."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    notify_class_paths = [
        unreal.TopLevelAssetPath("/Script/Engine", "AnimSequence"),
        unreal.TopLevelAssetPath("/Script/Engine", "AnimMontage"),
    ]
    filter_kwargs = {"class_paths": notify_class_paths}
    if folder:
        filter_kwargs["package_paths"] = [folder]
        filter_kwargs["recursive_paths"] = True
    ar_filter = unreal.ARFilter(**filter_kwargs)

    assets = registry.get_assets(ar_filter)
    lib = unreal.AnimationLibrary
    matches = []

    for ad in assets:
        asset = ad.get_asset()
        if asset is None:
            continue
        events = lib.get_animation_notify_events(asset)
        for evt in events:
            name = str(evt.get_editor_property("notify_name"))
            notify_obj = evt.get_editor_property("notify")
            state_obj = evt.get_editor_property("notify_state_class")
            cls_name = ""
            if notify_obj:
                cls_name = notify_obj.get_class().get_name()
            elif state_obj:
                cls_name = state_obj.get_class().get_name()

            if notify_name and notify_name.lower() in name.lower():
                matches.append({"asset": str(ad.package_name), "notify": name, "class": cls_name})
                break
            elif notify_class and notify_class.lower() in cls_name.lower():
                matches.append({"asset": str(ad.package_name), "notify": name, "class": cls_name})
                break

    return _json_result({"count": len(matches), "matches": matches})


def search_by_curve(curve_name, curve_type=None, folder=None):
    """Find animations containing a specific curve."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    filter_kwargs = {"class_paths": [unreal.TopLevelAssetPath("/Script/Engine", "AnimSequence")]}
    if folder:
        filter_kwargs["package_paths"] = [folder]
        filter_kwargs["recursive_paths"] = True
    ar_filter = unreal.ARFilter(**filter_kwargs)

    assets = registry.get_assets(ar_filter)
    lib = unreal.AnimationLibrary
    matches = []

    all_ct = _get_curve_type_map()
    if curve_type and curve_type in all_ct:
        ct_list = [all_ct[curve_type]]
    elif curve_type:
        return _json_error(f"Unknown or unavailable curve type: {curve_type}. Available: {list(all_ct.keys())}")
    else:
        ct_list = list(all_ct.values())

    for ad in assets:
        asset = ad.get_asset()
        if asset is None:
            continue
        for ct in ct_list:
            try:
                if lib.does_curve_exist(asset, curve_name, ct):
                    matches.append({"asset": str(ad.package_name), "curve": curve_name})
                    break
            except Exception:
                continue

    return _json_result({"count": len(matches), "matches": matches})


def search_by_slot(slot_name, folder=None):
    """Find montages using a specific slot."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    filter_kwargs = {"class_paths": [unreal.TopLevelAssetPath("/Script/Engine", "AnimMontage")]}
    if folder:
        filter_kwargs["package_paths"] = [folder]
        filter_kwargs["recursive_paths"] = True
    ar_filter = unreal.ARFilter(**filter_kwargs)

    assets = registry.get_assets(ar_filter)
    lib = unreal.AnimationLibrary
    matches = []

    for ad in assets:
        asset = ad.get_asset()
        if asset is None:
            continue
        slots = [str(n) for n in lib.get_montage_slot_names(asset)]
        if slot_name in slots:
            matches.append({"asset": str(ad.package_name), "slots": slots})

    return _json_result({"count": len(matches), "matches": matches})


def audit_notifies(asset_path=None, folder=None):
    """Audit notify usage across animations."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    lib = unreal.AnimationLibrary

    if asset_path:
        assets_to_check = [asset_path]
    else:
        audit_class_paths = [
            unreal.TopLevelAssetPath("/Script/Engine", "AnimSequence"),
            unreal.TopLevelAssetPath("/Script/Engine", "AnimMontage"),
        ]
        filter_kwargs = {"class_paths": audit_class_paths}
        if folder:
            filter_kwargs["package_paths"] = [folder]
            filter_kwargs["recursive_paths"] = True
        ar_filter = unreal.ARFilter(**filter_kwargs)
        ad_list = registry.get_assets(ar_filter)
        assets_to_check = [str(ad.package_name) for ad in ad_list]

    notify_counts = {}
    issues = []

    for path in assets_to_check:
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if asset is None:
            continue
        events = lib.get_animation_notify_events(asset)
        for evt in events:
            name = str(evt.get_editor_property("notify_name"))
            notify_counts[name] = notify_counts.get(name, 0) + 1
            chance = evt.get_editor_property("notify_trigger_chance")
            if chance <= 0:
                issues.append({"asset": path, "notify": name, "issue": "0% trigger chance"})

    sorted_notifies = sorted(notify_counts.items(), key=lambda x: -x[1])

    return _json_result({
        "assets_checked": len(assets_to_check),
        "unique_notifies": len(notify_counts),
        "notify_frequencies": [{"name": n, "count": c} for n, c in sorted_notifies],
        "issues": issues,
    })


def audit_blendspace(asset_path):
    """Analyze BlendSpace sample coverage."""
    asset, err = _load_asset(asset_path)
    if err: return _json_error(err)

    samples_raw = asset.get_editor_property("sample_data")
    samples = []
    for s in samples_raw:
        val = s.get_editor_property("sample_value")
        samples.append({"x": val.x, "y": val.y})

    # Check for duplicate positions
    duplicates = []
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            if abs(samples[i]["x"] - samples[j]["x"]) < 0.01 and abs(samples[i]["y"] - samples[j]["y"]) < 0.01:
                duplicates.append({"index_a": i, "index_b": j})

    return _json_result({
        "asset_path": asset_path,
        "sample_count": len(samples),
        "samples": samples,
        "duplicate_positions": duplicates,
    })


def compare_animations(path_a, path_b):
    """Compare two animation assets."""
    a, err = _load_asset(path_a)
    if err: return _json_error(err)
    b, err = _load_asset(path_b)
    if err: return _json_error(err)

    lib = unreal.AnimationLibrary

    diff = {"path_a": path_a, "path_b": path_b, "differences": []}

    len_a = lib.get_sequence_length(a)
    len_b = lib.get_sequence_length(b)
    if abs(len_a - len_b) > 0.001:
        diff["differences"].append({"property": "length", "a": len_a, "b": len_b})

    frames_a = lib.get_num_frames(a)
    frames_b = lib.get_num_frames(b)
    if frames_a != frames_b:
        diff["differences"].append({"property": "num_frames", "a": frames_a, "b": frames_b})

    notifies_a = len(lib.get_animation_notify_events(a))
    notifies_b = len(lib.get_animation_notify_events(b))
    if notifies_a != notifies_b:
        diff["differences"].append({"property": "notify_count", "a": notifies_a, "b": notifies_b})

    return _json_result(diff)


def get_animation_summary(folder):
    """Folder-level animation stats."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()

    type_counts = {}
    total_duration = 0.0

    for anim_type, class_path in _ANIM_CLASSES.items():
        parts = class_path.rsplit(".", 1)
        ar_filter = unreal.ARFilter(
            class_paths=[unreal.TopLevelAssetPath(parts[0], parts[1])],
            package_paths=[folder],
            recursive_paths=True,
        )
        assets = registry.get_assets(ar_filter)
        type_counts[anim_type] = len(assets)

    return _json_result({
        "folder": folder,
        "type_counts": type_counts,
        "total_assets": sum(type_counts.values()),
    })
