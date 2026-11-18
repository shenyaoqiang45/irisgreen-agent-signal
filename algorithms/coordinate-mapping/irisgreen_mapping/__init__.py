"""Coordinate mapping between the camera view and the projector field."""

from .mapping import (
    PROJ_HEIGHT,
    PROJ_WIDTH,
    Calibration,
    camera_point_to_projector,
    homography_is_sane,
    in_projection_field,
    place_in_camera_rect,
    render_camera_polygon,
    solve_homography,
)

__all__ = [
    "PROJ_HEIGHT",
    "PROJ_WIDTH",
    "Calibration",
    "camera_point_to_projector",
    "homography_is_sane",
    "in_projection_field",
    "place_in_camera_rect",
    "render_camera_polygon",
    "solve_homography",
]
