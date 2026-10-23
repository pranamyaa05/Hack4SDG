"""Deterministic measurement math. No model-invented dimensions."""

from itertools import combinations
from math import hypot, pi, sqrt
from uuid import uuid4

import numpy as np

from backend.contracts import Measurement

from .models import Observation, PerimeterRequest, Workspace


def rebuild(workspace: Workspace) -> Workspace:
    workspace.measurements = {}
    workspace.conflicts = {}
    for dimension in sorted({o.dimension for o in workspace.observations}):
        observations = [o for o in workspace.observations if o.dimension == dimension]
        conflicts = []
        for a, b in combinations(observations, 2):
            tolerance = min(1.5, 2.5 * hypot(a.sigma_mm, b.sigma_mm))
            if abs(a.value_mm - b.value_mm) > tolerance:
                conflicts.append(
                    f"{a.method} and {b.method} disagree; re-measure {dimension}"
                )
        sources = sorted({o.method for o in observations})
        if conflicts:
            workspace.measurements[dimension] = Measurement(
                status="conflict", sources=sources
            )
            workspace.conflicts[dimension] = conflicts
            continue
        # A derived reading can depend on another reading. Never precision-pool correlated evidence.
        selected = []
        used = set()
        for o in sorted(observations, key=lambda item: item.sigma_mm):
            if not used.intersection(o.evidence_ids) and o.method not in {
                v.method for v in selected
            }:
                selected.append(o)
                used.update(o.evidence_ids)
        weights = [1 / o.sigma_mm**2 for o in selected]
        value = sum(o.value_mm * w for o, w in zip(selected, weights)) / sum(weights)
        workspace.measurements[dimension] = Measurement(
            value_mm=value,
            sigma_mm=sqrt(1 / sum(weights)),
            status="cross_checked" if len(selected) >= 2 else "estimated",
            sources=sorted({o.method for o in selected}),
            confirmed_by_user=all(o.confirmed_by_user for o in selected),
        )
    return workspace


def add_observation(workspace: Workspace, observation: Observation) -> Workspace:
    # Re-taking a method replaces its reading rather than manufacturing confidence.
    removed = {
        o.id
        for o in workspace.observations
        if o.dimension == observation.dimension and o.method == observation.method
    }
    if observation.dimension == "handle_width":
        # The perimeter-derived thickness must be recomputed from updated width evidence.
        workspace.observations = [
            o for o in workspace.observations if o.method != "paper_strip"
        ]
    workspace.observations = [
        o
        for o in workspace.observations
        if o.id not in removed and not removed.intersection(o.evidence_ids)
    ]
    workspace.observations.append(observation)
    return rebuild(workspace)


def ellipse_perimeter(width: float, thickness: float) -> float:
    a, b = width / 2, thickness / 2
    return pi * (3 * (a + b) - sqrt((3 * a + b) * (a + 3 * b)))


def solve_thickness(
    width: float, perimeter: float, shape: str, radius: float = 0
) -> float:
    if not (
        np.isfinite(width) and np.isfinite(perimeter) and width > 0 and perimeter > 0
    ):
        raise ValueError("Width and perimeter must be finite positive measurements")
    if shape == "rounded_rectangle":
        thickness = (perimeter + (8 - 2 * pi) * radius) / 2 - width
        if thickness <= 0 or radius < 0 or 2 * radius > min(width, thickness):
            raise ValueError(
                "Perimeter and corner radius are incompatible with the confirmed width"
            )
        return thickness
    if shape != "ellipse":
        raise ValueError("Unsupported cross-section")
    low, high = 0.000001, perimeter
    if perimeter <= ellipse_perimeter(width, low):
        raise ValueError("Perimeter is too small for this width and shape; re-measure")
    for _ in range(80):
        mid = (low + high) / 2
        if ellipse_perimeter(width, mid) < perimeter:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def perimeter_observation(
    workspace: Workspace, request: PerimeterRequest
) -> Observation:
    width = workspace.measurements.get("handle_width")
    if width is None or width.status in {"unknown", "conflict"}:
        raise ValueError("Measure and resolve handle width before entering perimeter")
    w, p, r = width.value_mm, request.perimeter_mm, request.corner_radius_mm or 0
    nominal = solve_thickness(w, p, request.shape, r)
    # Monte Carlo captures nonlinear shape propagation. Fixed seed makes analysis reproducible.
    rng = np.random.default_rng(20261023)
    widths = rng.normal(w, width.sigma_mm, 4000)
    perimeters = rng.normal(p, request.perimeter_uncertainty_mm, 4000)
    radii = (
        rng.normal(r, request.corner_radius_uncertainty_mm, 4000)
        if request.shape == "rounded_rectangle"
        else np.zeros(4000)
    )
    samples = []
    for sw, sp, sr in zip(widths, perimeters, radii):
        try:
            samples.append(
                solve_thickness(float(sw), float(sp), request.shape, float(sr))
            )
        except ValueError:
            pass
    if len(samples) < 3800:
        raise ValueError(
            "Shape/measurement uncertainty is too high; enter directly measured thickness instead"
        )
    sigma = max(float(np.std(samples, ddof=1)), 0.5)
    evidence = sorted(
        {
            e
            for o in workspace.observations
            if o.dimension == "handle_width"
            for e in o.evidence_ids
        }
    )
    return Observation(
        dimension="handle_thickness",
        value_mm=nominal,
        sigma_mm=sigma,
        method="paper_strip",
        evidence_ids=evidence + [str(uuid4())],
        confirmed_by_user=True,
        notes=[
            "Thickness inferred from confirmed shape and perimeter; not a directly measured depth.",
            "0.5 mm model uncertainty floor is provisional.",
        ],
    )
