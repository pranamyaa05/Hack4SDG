import { useState } from "react";
import { api, pretty, type Measurements, type Track } from "./api";
import { Field, Badge } from "./ui";
type Point = { x_mm: number; y_mm: number };
interface Props {
  sid: string;
  track: Track;
  revision: number;
  data: Measurements | null;
  setData: (m: Measurements) => void;
  run: (label: string, fn: () => Promise<void>) => Promise<void>;
  next: () => void;
}
export default function Measure({
  sid,
  track,
  revision,
  data,
  setData,
  run,
  next,
}: Props) {
  const [mode, setMode] = useState("manual"),
    [values, setValues] = useState<Record<string, string>>({}),
    [instrument, setInstrument] = useState("manual_ruler"),
    [resolution, setResolution] = useState("0.5");
  const [photo, setPhoto] = useState<File | null>(null),
    [scale, setScale] = useState(false),
    [points, setPoints] = useState<Point[]>([]),
    [half, setHalf] = useState("15"),
    [height, setHeight] = useState("5"),
    [distance, setDistance] = useState("400"),
    [coplanar, setCoplanar] = useState(false),
    [perimeter, setPerimeter] = useState("");
  const root = `/sessions/${sid}`;
  const dimensions =
    track === "adapt"
      ? ["handle_width", "handle_thickness", "covered_length"]
      : ["hole_spacing", "hole_diameter"];
  return (
    <div className="studio-grid">
      <section className="card">
        <Badge>03 / DIMENSIONS WITH EVIDENCE</Badge>
        <h2>Get the fit right.</h2>
        <p className="muted">
          All dimensions in millimetres. Resolve conflicting readings before
          design.
        </p>
        {!data ? (
          <>
            <div className="track-picker">
              {["manual", "photo"].map((m) => (
                <button
                  className={"track " + (mode === m ? "selected" : "")}
                  key={m}
                  onClick={() => setMode(m)}
                >
                  <strong>
                    {m === "manual"
                      ? "Use a ruler or caliper"
                      : "Use the Fit Sheet"}
                  </strong>
                  <small>
                    {m === "manual"
                      ? "Enter and confirm your readings"
                      : "Calibrated photo + thickness measurement"}
                  </small>
                </button>
              ))}
            </div>
            <button
              className="button"
              onClick={() =>
                run("Starting measurements", async () =>
                  setData(
                    await api(root + "/measurement/start", {
                      expected_revision: revision,
                      mode,
                    }),
                  ),
                )
              }
            >
              Start measuring ↗
            </button>
          </>
        ) : (
          <>
            <div className="field-grid">
              <Field label="Instrument">
                <select
                  value={instrument}
                  onChange={(e) => {
                    setInstrument(e.target.value);
                    setResolution(
                      e.target.value === "manual_caliper" ? "0.05" : "0.5",
                    );
                  }}
                >
                  <option value="manual_ruler">Ruler</option>
                  <option value="manual_caliper">Caliper</option>
                </select>
              </Field>
              <Field label="Instrument resolution (mm)">
                <input
                  type="number"
                  min="0.001"
                  max="10"
                  step="any"
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value)}
                />
              </Field>
            </div>
            <div className="measurement-list">
              {dimensions.map((d) => {
                const m = data.workspace.measurements[d];
                return (
                  <div className="measurement-row" key={d}>
                    <Field label={pretty(d)}>
                      <input
                        aria-label={pretty(d) + " in mm"}
                        type="number"
                        min="0.01"
                        step="any"
                        value={values[d] ?? ""}
                        placeholder="mm"
                        onChange={(e) =>
                          setValues({ ...values, [d]: e.target.value })
                        }
                      />
                    </Field>
                    <button
                      className="button secondary"
                      disabled={!values[d]}
                      onClick={() =>
                        run("Saving measurement", async () =>
                          setData(
                            await api(root + "/measurements/manual", {
                              expected_revision: revision,
                              dimension: d,
                              value_mm: Number(values[d]),
                              instrument,
                              resolution_mm: Number(resolution),
                              confirmed_by_user: true,
                            }),
                          ),
                        )
                      }
                    >
                      Confirm reading
                    </button>
                    <div className="measurement-value">
                      {m?.value_mm != null ? (
                        <>
                          <strong>
                            {m.value_mm.toFixed(2)} ± {m.sigma_mm?.toFixed(2)}{" "}
                            mm
                          </strong>
                          <Badge>{pretty(m.status)}</Badge>
                        </>
                      ) : (
                        <Badge>{m?.status ?? "not measured"}</Badge>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            {Object.values(data.workspace.conflicts)
              .flat()
              .map((v, i) => (
                <p className="alert error" key={i}>
                  {v}
                </p>
              ))}
            {track === "adapt" && (
              <details>
                <summary>Use a paper-strip perimeter</summary>
                <p>
                  Width must be measured first. Confirm the cross-section model
                  or use a direct thickness reading.
                </p>
                <Perimeter
                  sid={sid}
                  revision={revision}
                  run={run}
                  setData={setData}
                  value={perimeter}
                  setValue={setPerimeter}
                />
              </details>
            )}
            <details open={mode === "photo"}>
              <summary>Measure from a calibrated photo</summary>
              <p>
                <a href="/api/fit-sheet.pdf" target="_blank" rel="noreferrer">
                  Print the Fit Sheet at Actual size ↗
                </a>
                . Keep the sheet flat and all markers visible.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  run("Calibrating photo", async () => {
                    if (!photo) throw Error("Choose a Fit Sheet photo.");
                    const form = new FormData();
                    form.append("image", photo);
                    form.append("expected_revision", String(revision));
                    form.append("scale_check_passed", String(scale));
                    setData(await api(root + "/calibrate", form));
                    setPoints([]);
                  });
                }}
              >
                <Field label="Object on the Fit Sheet">
                  <input
                    type="file"
                    accept="image/jpeg,image/png"
                    onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
                  />
                </Field>
                <label className="check">
                  <input
                    required
                    type="checkbox"
                    checked={scale}
                    onChange={(e) => setScale(e.target.checked)}
                  />
                  I checked both dimensions of the printed scale box with a card
                  or ruler.
                </label>
                <button
                  type="submit"
                  className="button secondary"
                  disabled={!photo || !scale}
                >
                  Calibrate photo
                </button>
              </form>
              {data.workspace.calibration && (
                <>
                  <Badge>
                    Calibration: {data.workspace.calibration.quality}
                  </Badge>
                  <p>
                    Select two points{" "}
                    {track === "adapt"
                      ? "along the handle segment"
                      : "at the mounting-hole centres"}
                    .
                  </p>
                  <div className="sheet-picker">
                    <img
                      alt="Rectified sheet; coordinate inputs below provide a keyboard alternative to clicking."
                      src={`/api${root}/measurement-images/rectified?revision=${revision}`}
                      onClick={(e) => {
                        const r = e.currentTarget.getBoundingClientRect();
                        const point = {
                          x_mm:
                            Math.round(
                              ((e.clientX - r.left) / r.width) * 2100,
                            ) / 10,
                          y_mm:
                            Math.round(
                              ((e.clientY - r.top) / r.height) * 2970,
                            ) / 10,
                        };
                        setPoints(
                          points.length >= 2 ? [point] : [...points, point],
                        );
                      }}
                    />
                    <svg viewBox="0 0 210 297" aria-hidden="true">
                      {points.map((p, i) => (
                        <circle key={i} cx={p.x_mm} cy={p.y_mm} r="2" />
                      ))}
                      {points.length === 2 && (
                        <line
                          x1={points[0].x_mm}
                          y1={points[0].y_mm}
                          x2={points[1].x_mm}
                          y2={points[1].y_mm}
                        />
                      )}
                    </svg>
                  </div>
                  <div className="field-grid">
                    {[0, 1].map((i) => (
                      <Field key={i} label={`Point ${i + 1}: x, y in mm`}>
                        <div className="coordinate-pair">
                          {(["x_mm", "y_mm"] as const).map((axis) => (
                            <input
                              key={axis}
                              aria-label={`Point ${i + 1} ${axis}`}
                              type="number"
                              min="0"
                              step="0.1"
                              value={points[i]?.[axis] ?? ""}
                              onChange={(e) => {
                                const ps = [...points];
                                ps[i] = {
                                  ...(ps[i] || { x_mm: 0, y_mm: 0 }),
                                  [axis]: Number(e.target.value),
                                };
                                setPoints(ps);
                              }}
                            />
                          ))}
                        </div>
                      </Field>
                    ))}
                  </div>
                  {track === "adapt" ? (
                    <div className="field-grid">
                      <Field label="Bracket half-width (mm)">
                        <input
                          type="number"
                          value={half}
                          onChange={(e) => setHalf(e.target.value)}
                        />
                      </Field>
                      <Field label="Object-height upper bound (mm)">
                        <input
                          type="number"
                          value={height}
                          onChange={(e) => setHeight(e.target.value)}
                        />
                      </Field>
                      <Field label="Camera-distance lower bound (mm)">
                        <input
                          type="number"
                          min="250"
                          value={distance}
                          onChange={(e) => setDistance(e.target.value)}
                        />
                      </Field>
                    </div>
                  ) : (
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={coplanar}
                        onChange={(e) => setCoplanar(e.target.checked)}
                      />
                      Sheet and hole centres lie in the same plane.
                    </label>
                  )}
                  <button
                    className="button secondary"
                    disabled={
                      points.length !== 2 || (track === "repair" && !coplanar)
                    }
                    onClick={() =>
                      run("Measuring selection", async () => {
                        const common = {
                          expected_revision: revision,
                          calibration_id: data.workspace.calibration?.id,
                          confirmed_by_user: true,
                        };
                        setData(
                          await api(
                            root +
                              (track === "adapt" ? "/region" : "/hole-spacing"),
                            track === "adapt"
                              ? {
                                  ...common,
                                  start: points[0],
                                  end: points[1],
                                  half_width_mm: Number(half),
                                  object_height_bound_mm: Number(height),
                                  camera_distance_lower_bound_mm:
                                    Number(distance),
                                }
                              : {
                                  ...common,
                                  first: points[0],
                                  second: points[1],
                                  coplanar_confirmed: coplanar,
                                },
                          ),
                        );
                      })
                    }
                  >
                    Confirm selection & measure
                  </button>
                  {data.workspace.measurements.handle_width?.sources.includes(
                    "photo_on_sheet",
                  ) && (
                    <img
                      className="region-preview"
                      alt="Detected handle outline highlighted in green. Inspect before fabrication."
                      src={`/api${root}/measurement-images/region-preview?revision=${revision}`}
                    />
                  )}
                </>
              )}
            </details>
            <button
              className="button"
              disabled={!data.dimensionally_complete}
              onClick={next}
            >
              See design options ↗
            </button>
          </>
        )}
      </section>
      <aside className="card compact">
        <h3>Confidence you can inspect.</h3>
        <p>
          <strong>Estimated</strong> means one method.{" "}
          <strong>Cross checked</strong> means independent readings agree. A
          physical trial still needs to prove fit.
        </p>
        <p>Photos cannot reveal hidden thickness or thread geometry.</p>
        <a href="/api/fit-sheet.pdf" target="_blank" rel="noreferrer">
          Get the calibration sheet ↗
        </a>
      </aside>
    </div>
  );
}
function Perimeter({
  sid,
  revision,
  run,
  setData,
  value,
  setValue,
}: {
  sid: string;
  revision: number;
  run: Props["run"];
  setData: Props["setData"];
  value: string;
  setValue: (v: string) => void;
}) {
  const [shape, setShape] = useState("ellipse"),
    [radius, setRadius] = useState("");
  return (
    <>
      <Field label="Cross-section model">
        <select value={shape} onChange={(e) => setShape(e.target.value)}>
          <option value="ellipse">Round / oval</option>
          <option value="rounded_rectangle">Rounded rectangle</option>
        </select>
      </Field>
      <Field label="Measured perimeter (mm)">
        <input
          type="number"
          min="1"
          step="any"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </Field>
      {shape === "rounded_rectangle" && (
        <Field label="Confirmed corner radius (mm)">
          <input
            type="number"
            min="0"
            step="any"
            value={radius}
            onChange={(e) => setRadius(e.target.value)}
          />
        </Field>
      )}
      <button
        className="button secondary"
        disabled={!value || (shape === "rounded_rectangle" && !radius)}
        onClick={() =>
          run("Checking perimeter", async () =>
            setData(
              await api(`/sessions/${sid}/measurements/perimeter`, {
                expected_revision: revision,
                perimeter_mm: Number(value),
                shape,
                ...(shape === "rounded_rectangle"
                  ? { corner_radius_mm: Number(radius) }
                  : {}),
                confirmed_by_user: true,
              }),
            ),
          )
        }
      >
        Confirm shape & perimeter
      </button>
    </>
  );
}
