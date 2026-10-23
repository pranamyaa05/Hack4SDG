from math import hypot
from uuid import uuid4

from backend.ai.questions import support_decision
from backend.contracts import PullParameters, SleeveParameters, Track

from .models import ManufacturingSpec

DISCLAIMERS = [
    "Not a medical device. Consult an occupational therapist for suitability.",
    "Handle-only adaptation. Printed plastics are not food-safe by default.",
    "Illustrative overlays are not photographs of a fabricated part.",
    "Test a fit coupon first. Dimension estimates do not prove physical fit.",
    "Drawer pulls are light-duty only; load capacity, layer orientation, and fastening require physical assessment.",
]


def recommendations(session, analysis, workspace):
    decision = support_decision(session.track, analysis)
    if decision["status"] != "supported":
        raise ValueError(decision["reason"])
    critical = (
        ["handle_width", "handle_thickness", "covered_length"]
        if session.track == Track.ADAPT
        else ["hole_spacing", "hole_diameter"]
    )
    for key in critical:
        m = workspace.measurements.get(key)
        if m is None or m.status in {"unknown", "conflict"}:
            raise ValueError(f"Measure and resolve {key} before requesting a design")
    values = {k: workspace.measurements[k].value_mm for k in critical}
    options = []
    if session.track == Track.ADAPT:
        w, t, length = (
            values["handle_width"],
            values["handle_thickness"],
            values["covered_length"],
        )
        if not (2 <= w <= 30 and 1 <= t <= 25 and 30 <= length <= 140):
            raise ValueError(
                "Supported handle bounds: width 2-30, thickness 1-25, covered length 30-140 mm"
            )
        sigma = max(
            workspace.measurements[k].sigma_mm
            for k in ("handle_width", "handle_thickness")
        )
        if sigma > 1.5:
            raise ValueError(
                "Cross-section uncertainty exceeds 1.5 mm; cross-check with a direct measurement"
            )
        clearance = max(0.4, 0.3 + 0.5 * sigma)
        reasons = {
            "slipping": "A wider surface offers more area to hold; check friction with the chosen material.",
            "pain": "A broader grip is a comfort option to try; suitability needs user feedback.",
            "cannot_wrap_fingers": "A larger grip reduces the finger bend needed to surround the handle.",
            "weak_grip": "Try a larger flexible grip and assess the force needed in a physical trial.",
            "other": "Compare sizes and keep the one that feels comfortable.",
        }
        for variant, ow, ot in [
            ("compact", 26, 24),
            ("balanced", 32, 28),
            ("large", 38, 34),
        ]:
            required = (
                hypot(w + clearance, t + clearance)
                if analysis.confirmation.cross_section == "flat"
                else max(w + clearance, t + clearance)
            ) + 4.8
            ow = max(ow, required)
            ot = max(ot, required)
            if ow > 44 or ot > 40:
                continue
            params = SleeveParameters(
                inner_width_mm=w + clearance,
                inner_thickness_mm=t + clearance,
                outer_width_mm=ow,
                outer_thickness_mm=ot,
                length_mm=length,
                wall_min_mm=2.4,
                clearance_mm=clearance,
                slit_width_mm=1.6,
            )
            options.append(
                dict(
                    variant=variant,
                    parameters=params.model_dump(),
                    reason=reasons[analysis.answers.difficulty],
                    materials=["TPU"],
                    notes=[
                        "Smooth flexible sleeve; comfort and friction are unvalidated.",
                        "Coupon uses the same cross-section and slit.",
                    ],
                )
            )
    else:
        spacing, diameter = values["hole_spacing"], values["hole_diameter"]
        if not (24 <= spacing <= 256 and 2.5 <= diameter <= 6):
            raise ValueError(
                "Supported drawer bounds: hole spacing 24-256 mm, hole diameter 2.5-6 mm"
            )
        if workspace.measurements["hole_spacing"].sigma_mm > 1:
            raise ValueError(
                "Hole-spacing uncertainty exceeds 1 mm; cross-check the centres manually"
            )
        for variant, height in [("compact", 22), ("balanced", 28), ("large", 34)]:
            boss = max(12, diameter + 6)
            params = PullParameters(
                hole_spacing_mm=spacing,
                hole_diameter_mm=diameter,
                boss_diameter_mm=boss,
                bar_length_mm=spacing + boss + 10,
                bar_width_mm=max(boss, 14),
                bar_height_mm=10,
                standoff_mm=height,
            )
            options.append(
                dict(
                    variant=variant,
                    parameters=params.model_dump(),
                    reason="Replacement bar sized to the confirmed mounting centres.",
                    materials=["PETG", "PLA"],
                    notes=[
                        "Through-bolts and exposed nuts required; no hidden-thread matching.",
                        "Light-duty only; mechanical strength is unvalidated.",
                    ],
                )
            )
    if not options:
        raise ValueError(
            "No supported size satisfies the measured cross-section and wall constraints"
        )
    return options


def build_spec(session, analysis, workspace, body):
    options = recommendations(session, analysis, workspace)
    chosen = next((o for o in options if o["variant"] == body.variant), None)
    if chosen is None or body.material not in chosen["materials"]:
        raise ValueError("Variant or material is not supported for these measurements")
    critical = (
        ["handle_width", "handle_thickness", "covered_length"]
        if session.track == Track.ADAPT
        else ["hole_spacing", "hole_diameter"]
    )
    verification = (
        "dimensionally_cross_checked"
        if all(workspace.measurements[k].status == "cross_checked" for k in critical)
        else "dimensionally_estimated"
    )
    return ManufacturingSpec(
        design_id=str(uuid4()),
        parent_design_id=body.parent_design_id,
        track=session.track,
        object_type=analysis.confirmation.object_type,
        object_confirmed=True,
        difficulty=analysis.answers.difficulty or "replace_missing_drawer_pull",
        parameters=chosen["parameters"],
        measurements=workspace.measurements,
        verification_level=verification,
        disclaimers=DISCLAIMERS,
        variant=body.variant,
        material=body.material,
        cross_section=analysis.confirmation.cross_section,
        mounting=body.mounting,
    )
