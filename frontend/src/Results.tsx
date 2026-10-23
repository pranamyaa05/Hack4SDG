import { lazy, Suspense, useState } from "react";
import { api, fileUrl, pretty, type Design } from "./api";
import { Badge, Field } from "./ui";
const Viewer = lazy(() => import("./Viewer"));
export default function Results({
  design,
  refit,
  run,
  notify,
}: {
  design: Design;
  refit: () => void;
  run: (s: string, fn: () => Promise<void>) => Promise<void>;
  notify: (s: string) => void;
}) {
  const [outcome, setOutcome] = useState(
      design.feedback?.outcome || "not_tested",
    ),
    [kept, setKept] = useState(design.feedback?.kept_in_use || false),
    [notes, setNotes] = useState("");
  return (
    <>
      <div className="result-heading">
        <Badge>{pretty(design.spec.verification_level)}</Badge>
        <span className="mono">{design.spec_hash.slice(7, 19)}</span>
      </div>
      <div className="studio-grid">
        <section className="card">
          <h2>Your next step is a physical test.</h2>
          <Suspense fallback={<p>Loading 3D preview…</p>}>
            <Viewer url={fileUrl(design.id, "part.stl")} />
          </Suspense>
          <div className="actions">
            <a
              className="button"
              href={`/api/designs/${design.id}/package.zip`}
            >
              Download complete package ↓
            </a>
            <button className="button secondary" onClick={refit}>
              Re-fit this design ↻
            </button>
          </div>
          <details>
            <summary>Individual files</summary>
            <div className="downloads">
              {design.files
                .filter((f) => f !== "package.zip")
                .map((f) => (
                  <a key={f} href={fileUrl(design.id, f)}>
                    {f} ↓
                  </a>
                ))}
            </div>
          </details>
          <details>
            <summary>Drawing and proposed overlay</summary>
            <img
              className="output-image"
              alt="Dimensioned drawing generated from the design specification"
              src={fileUrl(design.id, "part_drawing.png")}
            />
            <img
              className="output-image"
              alt="Illustrative attachment, not a photo of a fabricated part"
              src={fileUrl(design.id, "final_concept.png")}
            />
          </details>
        </section>
        <aside className="aside-stack">
          <div className="green-card">
            <span className="mini-label">MATERIAL ESTIMATE</span>
            <strong className="big-number">
              {design.ledger.solid_material_estimate_g.toFixed(1)}
              <small> g</small>
            </strong>
            <p>
              Solid CAD volume × typical {design.spec.material} density.
              Supports and actual slicer use may differ.
            </p>
            <a href={fileUrl(design.id, "build_card.pdf")}>
              Open the build card ↗
            </a>
          </div>
          <section className="card compact">
            <h3>How did the trial go?</h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                run("Saving fit feedback", async () => {
                  await api(`/designs/${design.id}/feedback`, {
                    outcome,
                    kept_in_use: kept && outcome === "fits",
                    notes,
                    confirmed_by_user: true,
                  });
                  notify(
                    "Fit feedback saved. Statistics now reflect your report.",
                  );
                });
              }}
            >
              <Field label="Physical fit result">
                <select
                  value={outcome}
                  onChange={(e) => setOutcome(e.target.value)}
                >
                  {["not_tested", "fits", "too_tight", "too_loose"].map((v) => (
                    <option key={v} value={v}>
                      {pretty(v)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Trial notes">
                <textarea
                  value={notes}
                  maxLength={1000}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </Field>
              <label className="check">
                <input
                  type="checkbox"
                  checked={kept}
                  disabled={outcome !== "fits"}
                  onChange={(e) => setKept(e.target.checked)}
                />
                The object is back in use.
              </label>
              <button type="submit" className="button secondary">
                Save feedback
              </button>
            </form>
          </section>
        </aside>
      </div>
      <div className="footnote">
        {design.spec.disclaimers.map((d) => (
          <p key={d}>{d}</p>
        ))}
      </div>
    </>
  );
}
