import json
import xml.etree.ElementTree as ET
from html import escape
from io import BytesIO
from math import atan2, degrees

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from backend.measurement.fit_sheet import MM_TO_PT


def hash_prefix(spec):
    return spec.content_hash().split(":")[1][:8]


def drawing_svg(spec):
    p = spec.parameters.model_dump(exclude={"family"})
    sleeve = spec.track.value == "adapt"
    length = p["length_mm"] if sleeve else p["bar_length_mm"]
    width = p["outer_width_mm"] if sleeve else p["bar_width_mm"]
    height = (
        p["outer_thickness_mm"] if sleeve else p["standoff_mm"] + p["bar_height_mm"]
    )
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210">',
        '<rect width="297" height="210" fill="white"/>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#18352c"/></marker></defs>',
        '<g font-family="sans-serif" font-size="3.5" fill="#18352c">',
        f'<text x="10" y="12">ReFit / {escape(spec.parameters.family)} / {hash_prefix(spec)}{" / EXAMPLE FIXTURE" if spec.example else ""}</text>',
        '<text x="10" y="19" fill="#9b4c0a">DIMENSIONS ESTIMATED: TEST PHYSICAL FIT BEFORE FULL FABRICATION</text>',
        '<text x="10" y="26">Units mm / Scale 1:1 at Actual size / measured specification</text>',
        f'<rect x="10" y="38" width="{length}" height="{width}" fill="#dfece3" stroke="#18352c" stroke-width="0.3"/>',
        f'<text x="10" y="{43 + width}">Top view</text>',
        f'<rect x="10" y="95" width="{length}" height="{height}" fill="none" stroke="#18352c" stroke-width="0.3"/>',
        f'<text x="10" y="{100 + height}">Side envelope / internal details follow cross-section and specification</text>',
    ]

    def dimline(x1, y1, x2, y2, label):
        return (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#18352c" stroke-width="0.2" marker-start="url(#arrow)" marker-end="url(#arrow)"/>'
            f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 1.5}" text-anchor="middle" font-size="3">{label:g} mm</text>'
        )

    parts.append(dimline(10, 33, 10 + length, 33, length))
    parts.append(dimline(10, 88, 10 + length, 88, length))
    parts.append(dimline(12 + length, 95, 12 + length, 95 + height, height))
    for x in (10, 10 + length):
        parts.append(
            f'<line x1="{x}" y1="31" x2="{x}" y2="38" stroke="#18352c" stroke-width="0.2"/>'
        )
    if sleeve:
        parts.append(
            f'<ellipse cx="35" cy="169" rx="{width / 2}" ry="{height / 2}" fill="#dfece3" stroke="#18352c" stroke-width="0.3"/>'
        )
        if spec.cross_section == "flat":
            parts.append(
                f'<rect x="{35 - p["inner_width_mm"] / 2}" y="{169 - p["inner_thickness_mm"] / 2}" width="{p["inner_width_mm"]}" height="{p["inner_thickness_mm"]}" fill="white" stroke="#18352c" stroke-width="0.3"/>'
            )
        else:
            parts.append(
                f'<ellipse cx="35" cy="169" rx="{p["inner_width_mm"] / 2}" ry="{p["inner_thickness_mm"] / 2}" fill="white" stroke="#18352c" stroke-width="0.3"/>'
            )
        parts.append(
            f'<rect x="{35 - p["slit_width_mm"] / 2}" y="{169 - height / 2}" width="{p["slit_width_mm"]}" height="{height / 2}" fill="white"/>'
        )
    else:
        for x in (
            (length - p["hole_spacing_mm"]) / 2,
            (length + p["hole_spacing_mm"]) / 2,
        ):
            parts.append(
                f'<circle cx="{10 + x}" cy="{38 + width / 2}" r="{p["hole_diameter_mm"] / 2}" fill="white" stroke="#18352c" stroke-width="0.3"/>'
            )
    for i, (key, value) in enumerate(p.items()):
        col = i // 6
        row = i % 6
        x = 70 + col * 100
        y = 150 + row * 6
        parts.append(
            f'<text x="{x}" y="{y}">{escape(key)}:</text><text x="{x + 65}" y="{y}" data-dim="{key}">{value}</text>'
        )
    parts.extend(
        [
            '<text x="10" y="198">Not a medical device. Handle only; avoid food contact. Drawer pull load capacity unvalidated.</text>',
            '<text x="10" y="204">Drawing shows exact envelopes and specified cross-section; consult STEP for the full solid.</text>',
            "</g></svg>",
        ]
    )
    return "".join(parts)


def drawing_pdf(spec):
    stream = BytesIO()
    c = canvas.Canvas(stream, pagesize=(297 * MM_TO_PT, 210 * MM_TO_PT))
    c.setTitle(f"ReFit drawing {hash_prefix(spec)}")

    def text(x, y, value, size=9):
        c.setFont("Helvetica", size)
        c.drawString(x * MM_TO_PT, (210 - y) * MM_TO_PT, value)

    def rect(x, y, w, h):
        c.rect(x * MM_TO_PT, (210 - y - h) * MM_TO_PT, w * MM_TO_PT, h * MM_TO_PT)

    p = spec.parameters
    sleeve = spec.track.value == "adapt"
    length = p.length_mm if sleeve else p.bar_length_mm
    width = p.outer_width_mm if sleeve else p.bar_width_mm
    height = p.outer_thickness_mm if sleeve else p.standoff_mm + p.bar_height_mm
    text(
        10,
        12,
        f"ReFit / {p.family} / {hash_prefix(spec)}{' / EXAMPLE FIXTURE' if spec.example else ''}",
        12,
    )
    text(10, 20, "DIMENSIONS ESTIMATED - TEST FIT BEFORE FABRICATION", 10)
    text(10, 27, "Units mm / Print at Actual size / 1:1")
    rect(10, 38, length, width)
    if not sleeve:
        for x in ((length - p.hole_spacing_mm) / 2, (length + p.hole_spacing_mm) / 2):
            c.circle(
                (10 + x) * MM_TO_PT,
                (210 - 38 - width / 2) * MM_TO_PT,
                p.hole_diameter_mm / 2 * MM_TO_PT,
            )
    text(10, 43 + width, f"Top: {length:g} x {width:g} mm")
    rect(10, 95, length, height)
    text(10, 100 + height, f"Side envelope: {length:g} x {height:g} mm")
    c.setLineWidth(0.4)
    for y in (33, 88):
        c.line(
            10 * MM_TO_PT,
            (210 - y) * MM_TO_PT,
            (10 + length) * MM_TO_PT,
            (210 - y) * MM_TO_PT,
        )
        for x, direction in ((10, 1), (10 + length, -1)):
            c.line(
                x * MM_TO_PT,
                (210 - y) * MM_TO_PT,
                (x + direction * 2) * MM_TO_PT,
                (210 - y + 1) * MM_TO_PT,
            )
            c.line(
                x * MM_TO_PT,
                (210 - y) * MM_TO_PT,
                (x + direction * 2) * MM_TO_PT,
                (210 - y - 1) * MM_TO_PT,
            )
        text(10 + length / 2 - 5, y - 1.5, f"{length:g} mm", 8)
    if sleeve:
        cx, cy = 245, 169
        c.setFillColorRGB(0.88, 0.93, 0.89)
        c.ellipse(
            (cx - width / 2) * MM_TO_PT,
            (210 - cy - height / 2) * MM_TO_PT,
            (cx + width / 2) * MM_TO_PT,
            (210 - cy + height / 2) * MM_TO_PT,
            fill=1,
        )
        c.setFillColorRGB(1, 1, 1)
        if spec.cross_section == "flat":
            c.rect(
                (cx - p.inner_width_mm / 2) * MM_TO_PT,
                (210 - cy - p.inner_thickness_mm / 2) * MM_TO_PT,
                p.inner_width_mm * MM_TO_PT,
                p.inner_thickness_mm * MM_TO_PT,
                fill=1,
            )
        else:
            c.ellipse(
                (cx - p.inner_width_mm / 2) * MM_TO_PT,
                (210 - cy - p.inner_thickness_mm / 2) * MM_TO_PT,
                (cx + p.inner_width_mm / 2) * MM_TO_PT,
                (210 - cy + p.inner_thickness_mm / 2) * MM_TO_PT,
                fill=1,
            )
        c.rect(
            (cx - p.slit_width_mm / 2) * MM_TO_PT,
            (210 - cy) * MM_TO_PT,
            p.slit_width_mm * MM_TO_PT,
            height / 2 * MM_TO_PT,
            stroke=0,
            fill=1,
        )
        c.setFillColorRGB(0, 0, 0)
        text(222, 195, "Cross-section / slit on +z", 8)
    for i, (key, value) in enumerate(p.model_dump(exclude={"family"}).items()):
        text(10 + (i // 5) * 95, 155 + (i % 5) * 7, f"{key}: {value:g}", 8)
    text(
        10,
        197,
        "Envelope drawing. Full solid in STEP. Verify cross-section and mounting before use.",
        8,
    )
    text(
        10,
        204,
        "Not a medical device. Handle only; avoid food contact. Drawer pull load capacity unvalidated.",
        8,
    )
    c.save()
    return stream.getvalue()


def build_card(spec):
    stream = BytesIO()
    c = canvas.Canvas(stream, pagesize=(210 * MM_TO_PT, 297 * MM_TO_PT))
    p = spec.parameters
    lines = [
        f"ReFit build card / {hash_prefix(spec)}{' / EXAMPLE FIXTURE' if spec.example else ''}",
        "Measured dimensions are estimates. Test comfort and fit first.",
    ]
    if spec.track.value == "adapt":
        lines += [
            "No-printer route: soft foam tube and tape",
            f"Choose a foam tube with an opening at least {max(p.inner_width_mm, p.inner_thickness_mm):g} mm across.",
            f"Cut length: {p.length_mm:g} mm. Slit along one side and fit only over the handle.",
            f"Target outside grip: {p.outer_width_mm:g} x {p.outer_thickness_mm:g} mm.",
            "Add soft wrap gradually. Foam and tape deform; confirm the actual fit and comfort.",
            "Keep the sleeve clear of the bowl, tines, blade, and mouth-contact areas.",
            "Replace if worn, loose, or difficult to clean. Do not force a tight sleeve.",
            "3D-print route: print the 10 mm fit coupon before committing to the full sleeve.",
            "Tighter/looser coupons alter each inner span by -0.2/+0.2 mm; select from real trials.",
        ]
    else:
        m = spec.mounting
        lines += [
            "Light-duty drawer pull / through-bolt-and-nut mounting",
            f"Confirmed hole spacing: {p.hole_spacing_mm:g} mm. Measured hole diameter: {p.hole_diameter_mm:g} mm.",
            f"Bolt diameter {m.bolt_diameter_mm:g} mm; bolt length {m.bolt_length_mm:g} mm; nut height {m.nut_height_mm:g} mm.",
            f"Drawer-face thickness {m.face_thickness_mm:g} mm. Stand-off {p.standoff_mm:g} mm.",
            "Bolts pass from behind the drawer face through both bosses and the bar, with nuts on top.",
            "Use suitable washers. Do not fit to a cracked face. Check protrusions and finger clearance.",
            "Print orientation, layer adhesion, torque and load capacity require physical assessment.",
            "No-printer route: choose a conventional pull matching the measured centres; compare before purchase.",
        ]
    lines += [
        f"Material: {spec.material}. This is not a food-safety or strength certification.",
        "Not a medical device. Consult an occupational therapist for suitability.",
        "Print this card at 100% / Actual size. Check the 50 mm square below.",
    ]
    y = 279 * MM_TO_PT
    for i, line in enumerate(lines):
        font = 14 if i == 0 else 10
        c.setFont("Helvetica", font)
        for part in simpleSplit(line, "Helvetica", font, 180 * MM_TO_PT):
            c.drawString(15 * MM_TO_PT, y, part)
            y -= 6 * MM_TO_PT
        y -= 3 * MM_TO_PT
    c.setFont("Helvetica", 9)
    if spec.track.value == "adapt":
        c.drawString(
            15 * MM_TO_PT,
            100 * MM_TO_PT,
            "1:1 cut-length guide (10 mm wide paper strip)",
        )
        c.rect(15 * MM_TO_PT, 84 * MM_TO_PT, p.length_mm * MM_TO_PT, 10 * MM_TO_PT)
    elif p.hole_spacing_mm <= 170:
        c.drawString(
            15 * MM_TO_PT,
            105 * MM_TO_PT,
            "1:1 mounting-centre check; verify against the actual drawer",
        )
        for x in (20, 20 + p.hole_spacing_mm):
            c.circle(x * MM_TO_PT, 90 * MM_TO_PT, p.hole_diameter_mm / 2 * MM_TO_PT)
        c.line(
            20 * MM_TO_PT,
            90 * MM_TO_PT,
            (20 + p.hole_spacing_mm) * MM_TO_PT,
            90 * MM_TO_PT,
        )
    else:
        c.drawString(
            15 * MM_TO_PT,
            95 * MM_TO_PT,
            "Use the 1:1 landscape drawing for the mounting-centre template.",
        )
    c.rect(15 * MM_TO_PT, 20 * MM_TO_PT, 50 * MM_TO_PT, 50 * MM_TO_PT)
    c.setFont("Helvetica", 9)
    c.drawString(17 * MM_TO_PT, 43 * MM_TO_PT, "50 x 50 mm scale check")
    c.save()
    return stream.getvalue()


def concept_image(spec, rectified=None, selection=None):
    p = spec.parameters
    sleeve = spec.track.value == "adapt"
    length = p.length_mm if sleeve else p.bar_length_mm
    width = p.outer_width_mm if sleeve else p.bar_width_mm
    if rectified:
        image = Image.open(BytesIO(rectified)).convert("RGB")
    else:
        image = Image.new("RGB", (1600, 1000), (241, 245, 240))
    ppm = 10 if rectified else min(8, 1300 / length)
    sprite = Image.new(
        "RGBA", (round(length * ppm), round(width * ppm)), (36, 137, 104, 155)
    )
    angle = 0
    center = (image.width / 2, image.height / 2)
    if rectified and selection:
        if sleeve:
            req = selection["request"]
            a = req["start"]
            b = req["end"]
        else:
            a = selection["first"]
            b = selection["second"]
        center = ((a["x_mm"] + b["x_mm"]) * 5, (a["y_mm"] + b["y_mm"]) * 5)
        angle = -degrees(atan2(b["y_mm"] - a["y_mm"], b["x_mm"] - a["x_mm"]))
    sprite = sprite.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    image.paste(
        sprite,
        (round(center[0] - sprite.width / 2), round(center[1] - sprite.height / 2)),
        sprite,
    )
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width, 110), fill=(20, 49, 41))
    draw.text(
        (25, 20),
        f"{'EXAMPLE FIXTURE' if spec.example else 'PROPOSED'} / ILLUSTRATIVE / {hash_prefix(spec)}",
        fill="white",
        font=ImageFont.load_default(size=25),
    )
    draw.text(
        (25, 60),
        "Calibrated-plane overlay"
        if rectified
        else "Measured silhouette - no calibrated photo",
        fill="white",
        font=ImageFont.load_default(size=22),
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), {
        "unrotated_length_px": round(length * ppm),
        "unrotated_width_px": round(width * ppm),
        "pixels_per_mm": ppm,
        "illustrative": True,
    }


def material_ledger(spec, metrics):
    densities = {"TPU": 1.21, "PETG": 1.27, "PLA": 1.24}
    grams = metrics["volume_mm3"] / 1000 * densities[spec.material]
    return {
        "spec_hash": spec.content_hash(),
        "material": spec.material,
        "volume_mm3": metrics["volume_mm3"],
        "density_g_per_cm3": densities[spec.material],
        "solid_material_estimate_g": grams,
        "assumptions": [
            "Typical material density; check the actual spool datasheet.",
            "Solid CAD volume estimate; excludes supports, brim and purge. Actual slicer use can differ.",
        ],
        "co2_savings": None,
        "cost_savings": None,
    }


def render_outputs(spec, folder, metrics, rectified=None, selection=None):
    import pypdfium2 as pdfium

    svg = drawing_svg(spec)
    root = ET.fromstring(svg)
    values = spec.parameters.model_dump(exclude={"family"})
    checked = set()
    for node in root.iter():
        key = node.attrib.get("data-dim")
        if key:
            if abs(float(node.text) - values[key]) > 1e-8:
                raise ValueError("Drawing dimensions disagree with specification")
            checked.add(key)
    if checked != set(values):
        raise ValueError("Drawing omits specification dimensions")
    (folder / "part_drawing.svg").write_text(svg, encoding="utf-8")
    pdf = drawing_pdf(spec)
    (folder / "part_drawing.pdf").write_bytes(pdf)
    with pdfium.PdfDocument(pdf) as doc:
        doc[0].render(scale=2).to_pil().save(folder / "part_drawing.png")
    (folder / "build_card.pdf").write_bytes(build_card(spec))
    concept, overlay = concept_image(spec, rectified, selection)
    (folder / "final_concept.png").write_bytes(concept)
    ledger = material_ledger(spec, metrics)
    (folder / "impact_ledger.json").write_text(
        json.dumps(ledger, indent=2), encoding="utf-8"
    )
    return {"drawing_dimensions_match": True, "overlay": overlay, "ledger": ledger}
