# Measurement workflow (Chunk 2)

The measurement backend is available through /docs. The product frontend will be integrated with the existing landing page in Chunk 7. Both tracks work without AI analysis: starting measurement directly is an explicit manual-first path. It does not claim object confirmation or advance to recommendations.

## Physical preparation

Download GET /api/fit-sheet.pdf, or use docs/assets/refit-fit-sheet-v1.pdf. Print on A4 at 100% / Actual size with Fit to page disabled. Check both dimensions of the 85.60 by 53.98 mm rectangle against a card or a ruler. Do not upload identifying details on a card. Use the uncut sheet for calibration; cut out a second sheet's strip if using the perimeter route.

Keep the sheet flat, object in the clear gray work area, phone overhead, and lighting diffuse. Three markers are the minimum; four are preferred. Only select points inside the detected marker coverage. For a drawer, cut a window in the gray work area to reveal the mounting holes while leaving every marker intact, then tape the sheet flat against the drawer face in the mounting-hole plane. Do not let the cut sheet bend. This is a planar measurement system, not a depth camera.

## API sequence

1. POST /api/sessions with track adapt or repair and consent true.
2. POST /api/sessions/{id}/measurement/start with mode manual or photo and expected_revision 0.
3. Every successful mutation returns a new revision. Use it as expected_revision for the next request. A stale revision returns 409 without changing stored evidence.
4. Manual route: POST /api/sessions/{id}/measurements/manual with dimension, value_mm, instrument (manual_ruler or manual_caliper), resolution_mm, optional uncertainty_mm, and confirmed_by_user true.
5. Photo route: multipart POST /api/sessions/{id}/calibrate with image (JPEG/PNG), expected_revision, and scale_check_passed true. It returns calibration.id and the full-image to sheet-mm homography. The rectified image is available at /api/sessions/{id}/measurement-images/rectified.
6. Adapt: POST /api/sessions/{id}/region with calibration_id, start/end points in sheet mm, half_width_mm, confirmed_by_user true, object_height_bound_mm and camera_distance_lower_bound_mm. The selected axis runs along the handle. Leave gray background on both sides. Inspect /measurement-images/region-preview and the returned width profile. The reported width is the 95th percentile over valid scan lines, not a guarantee of clearance for every contour.
7. Adapt thickness: enter it manually, or POST /api/sessions/{id}/measurements/perimeter with perimeter_mm, perimeter_uncertainty_mm, shape ellipse or rounded_rectangle, and confirmed_by_user true. Rounded rectangles additionally require corner_radius_mm and corner_radius_uncertainty_mm. This models a confirmed shape; uncertain or irregular shapes need direct thickness measurement.
8. Repair: POST /api/sessions/{id}/hole-spacing with calibration_id, first/second points in sheet mm, coplanar_confirmed true, confirmed_by_user true, and optional click_uncertainty_mm. No automatic snapping changes the observed spacing. Enter hole_diameter manually. Fastener and mounting design checks follow in the Repair engine.
9. GET /api/sessions/{id}/measurements to resume the saved workspace, selections, observations, missing dimensions, uncertainty and conflicts.

Adapt requires handle_width, handle_thickness and covered_length. Repair requires hole_spacing and hole_diameter. Dimensionally complete is distinct from physically verified. None of these measurement endpoints marks physical fit as verified.

## Evidence and uncertainty

- JPEG/PNG only, up to 15 MB and 20 megapixels; minimum 1600-pixel long edge and 600-pixel short edge. EXIF is removed by decoding into pixels; only a clean rectified PNG is stored.
- Marker reprojection RMS and leave-one-marker-out RMS measure internal geometric agreement. They do not prove absolute measurement accuracy or print scale.
- Manual sigma is at least the supplied instrument resolution and provisional floors of 0.5 mm (ruler) / 0.05 mm (caliper), or the larger user-declared uncertainty.
- Photo uncertainty combines marker residuals, provisional edge and calibration floors, visible profile variation, and a conservative allowance using user-declared height/distance bounds. These bounds are not inferred camera pose. Lens distortion is not calibrated.
- Paper-strip thickness propagates width, perimeter and corner-radius uncertainty with reproducible Monte Carlo samples and a provisional 0.5 mm model floor. Invalid shape samples trigger manual fallback.
- Agreeing independent readings fuse by inverse-variance weights. Pairwise disagreement beyond min(1.5 mm, 2.5 times combined sigma) produces conflict, with no silently averaged dimension.
- Repeating a method replaces its old observation. Shared evidence is not precision-pooled. A derived thickness observation alone remains estimated.
- New width readings invalidate paper-strip thickness. Recalibration invalidates photo and derived observations, selections and previews while preserving manual readings. Session revision checks make evidence and image replacement atomic.

## Evaluation

The tests use synthetic known geometry, perspective warps, invalid photos, actual PDF rendering, and API persistence. No real-object accuracy has been established yet.

Copy sample_data/measurement_evaluation_template.csv and fill it with actual object IDs, methods, dimensions, estimates, and reference measurements. Capture at least three photos per object and vary lighting/angle. Record instrument accuracy separately; do not treat nominal resolution as truth.

```powershell
.venv\Scripts\python -m tools.evaluate_measurements your_trials.csv --output var/evaluation.json
```

The report computes mean/max absolute error, bias, fraction within 1 mm and repeatability. Empty data is rejected. Do not place illustrative or synthetic data in a report presented as physical validation.

## Technical references

OpenCV's [ArUco detection guide](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html) documents marker generation, IDs and corner detection. Its [homography guide](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html) explains the planar mapping used for rectification. Project-specific rejection thresholds and uncertainty floors remain assumptions requiring physical evaluation.
