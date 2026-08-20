"""Tool solids and swept-volume computation.

By F-005 this package serves both the medium tier (35 pts) and the hard
tool-path tier (25 pts), which are the same geometry problem viewed from
opposite ends.
"""

from machineplan.geometry.sweep import (
    SweepError,
    SweptVolume,
    material_removed,
    segment_sweep,
    sweep_moves,
    sweep_tool_path,
)
from machineplan.geometry.tooling import Tool, UnknownToolError, tool_from_library_name

__all__ = [
    "Tool",
    "UnknownToolError",
    "tool_from_library_name",
    "SweptVolume",
    "SweepError",
    "sweep_tool_path",
    "sweep_moves",
    "segment_sweep",
    "material_removed",
]
