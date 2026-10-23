"""Deterministic solid generation; imported lazily by the packaging worker."""

from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh


def sleeve(spec, length=None, clearance_delta=0):
    p = spec.parameters
    length = length or p.length_mm
    iw = p.inner_width_mm + clearance_delta
    it = p.inner_thickness_mm + clearance_delta
    if min(iw, it) <= 0:
        raise ValueError("Coupon inner dimensions must stay positive")
    outer = (
        cq.Workplane("YZ")
        .ellipse(p.outer_width_mm / 2, p.outer_thickness_mm / 2)
        .extrude(length)
    )
    if spec.cross_section == "flat":
        inner = cq.Workplane("YZ", origin=(-1, 0, 0)).rect(iw, it).extrude(length + 2)
    else:
        inner = (
            cq.Workplane("YZ", origin=(-1, 0, 0))
            .ellipse(iw / 2, it / 2)
            .extrude(length + 2)
        )
    slit = (
        cq.Workplane("XY")
        .box(
            length + 2,
            p.slit_width_mm,
            p.outer_thickness_mm,
            centered=(False, True, False),
        )
        .translate((-1, 0, 0))
    )
    return outer.cut(inner).cut(slit)


def pull(spec):
    p = spec.parameters
    length = p.bar_length_mm
    # x=0 is the start face, z=0 is the drawer mounting plane.
    result = (
        cq.Workplane("XY")
        .box(length, p.bar_width_mm, p.bar_height_mm, centered=(False, True, False))
        .translate((0, 0, p.standoff_mm))
    )
    for x in ((length - p.hole_spacing_mm) / 2, (length + p.hole_spacing_mm) / 2):
        boss = (
            cq.Workplane("XY")
            .center(x, 0)
            .circle(p.boss_diameter_mm / 2)
            .extrude(p.standoff_mm + 1)
        )
        bore = (
            cq.Workplane("XY", origin=(0, 0, -1))
            .center(x, 0)
            .circle(p.hole_diameter_mm / 2)
            .extrude(p.standoff_mm + p.bar_height_mm + 2)
        )
        result = result.union(boss).cut(bore)
    return result


def export_checked(shape, folder: Path, stem: str, expected=None):
    solid = shape.val()
    if not solid.isValid() or len(shape.solids().vals()) != 1 or solid.Volume() <= 0:
        raise ValueError("Geometry is not a single valid solid")
    bbox = solid.BoundingBox()
    extents = [bbox.xlen, bbox.ylen, bbox.zlen]
    if expected is not None and not np.allclose(extents, expected, atol=0.05, rtol=0):
        raise ValueError("CAD bounding box disagrees with the specification")
    step = folder / f"{stem}.step"
    stl = folder / f"{stem}.stl"
    cq.exporters.export(shape, str(step))
    cq.exporters.export(shape, str(stl), tolerance=0.02, angularTolerance=0.08)
    mesh = trimesh.load_mesh(stl, process=True)
    if (
        not mesh.is_watertight
        or not mesh.is_volume
        or not np.allclose(mesh.extents, extents, atol=0.1, rtol=0)
    ):
        raise ValueError(
            "Exported mesh failed watertightness, orientation, or dimensions"
        )
    if abs(mesh.volume - solid.Volume()) / solid.Volume() > 0.02:
        raise ValueError("Exported mesh volume differs from the CAD solid by over 2%")
    return {
        "solid_valid": True,
        "watertight": True,
        "volume_mm3": solid.Volume(),
        "bbox_mm": extents,
        "mesh_volume_mm3": float(mesh.volume),
    }


def generate_geometry(spec, folder: Path):
    p = spec.parameters
    if p.family == "grip_sleeve":
        shape = sleeve(spec)
        metrics = export_checked(
            shape, folder, "part", [p.length_mm, p.outer_width_mm, p.outer_thickness_mm]
        )
        export_checked(
            sleeve(spec, length=10),
            folder,
            "fit_coupon",
            [10, p.outer_width_mm, p.outer_thickness_mm],
        )
        for name, delta in [("tighter", -0.2), ("looser", 0.2)]:
            export_checked(
                sleeve(spec, length=10, clearance_delta=delta),
                folder,
                f"fit_coupon_{name}",
            )
    else:
        shape = pull(spec)
        metrics = export_checked(
            shape,
            folder,
            "part",
            [p.bar_length_mm, p.bar_width_mm, p.standoff_mm + p.bar_height_mm],
        )
    return metrics
