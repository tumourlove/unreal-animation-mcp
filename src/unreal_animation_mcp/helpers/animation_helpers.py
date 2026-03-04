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
