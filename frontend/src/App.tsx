import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  pretty,
  fileUrl,
  type Session,
  type Analysis,
  type Measurements,
  type Design,
  type Proposal,
  type Stats,
  type Track,
} from "./api";
import { Field, Badge } from "./ui";
import Measure from "./Measure";
import Results from "./Results";
export default function App() {
  const [tab, setTab] = useState("studio"),
    [step, setStep] = useState(0),
    [track, setTrack] = useState<Track>("adapt");
  const [session, setSession] = useState<Session | null>(null),
    [analysis, setAnalysis] = useState<Analysis | null>(null),
    [measurements, setMeasurements] = useState<Measurements | null>(null),
    [design, setDesign] = useState<Design | null>(null);
  const [library, setLibrary] = useState<Design[]>([]),
    [stats, setStats] = useState<Stats | null>(null),
    [cloudConfigured, setCloudConfigured] = useState(false),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [photo, setPhoto] = useState<File | null>(null),
    [notes, setNotes] = useState(""),
    [provider, setProvider] = useState("ollama"),
    [cloud, setCloud] = useState(false),
    [consent, setConsent] = useState(false);
  const [object, setObject] = useState("spoon"),
    [component, setComponent] = useState("handle"),
    [shape, setShape] = useState("oval"),
    [intact, setIntact] = useState(false),
    [answers, setAnswers] = useState<Record<string, string>>({});
  const [proposals, setProposals] = useState<Proposal[]>([]),
    [variant, setVariant] = useState("balanced"),
    [material, setMaterial] = useState("TPU"),
    [mounting, setMounting] = useState<Record<string, string>>({}),
    [mountConfirmed, setMountConfirmed] = useState(false);
  const revision =
      measurements?.revision ?? analysis?.revision ?? session?.revision ?? 0,
    sid = session?.id;
  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Retry.");
    } finally {
      setBusy("");
    }
  }
  async function loadSession(id: string) {
    const s = await api<Session>("/sessions/" + id);
    setSession(s);
    setTrack(s.track);
    const a = await api<Analysis>(`/sessions/${id}/analysis`);
    setAnalysis(a);
    let m: Measurements | null = null;
    if (["measuring", "calibrating", "ready"].includes(s.state)) {
      try {
        m = await api<Measurements>(`/sessions/${id}/measurements`);
      } catch {
        /* No workspace yet is expected after confirmation. */
      }
    }
    setMeasurements(m);
    setDesign(null);
    setStep(
      a.support.status === "supported"
        ? 2
        : a.workspace.confirmation
          ? 1
          : s.state === "created"
            ? 0
            : 1,
    );
    if (a.workspace.confirmation) {
      setObject(a.workspace.confirmation.object_type);
      setComponent(a.workspace.confirmation.component);
      setShape(a.workspace.confirmation.cross_section);
      setIntact(a.workspace.confirmation.handle_intact === true);
    }
    localStorage.setItem("refit-session", id);
    if (s.state === "ready") {
      const list = await api<{ designs: Design[] }>("/designs");
      const found = list.designs.find((d) => d.session_id === id);
      if (found) {
        setDesign(found);
        setStep(4);
      }
    }
  }
  useEffect(() => {
    api<{ default_provider: string; gemini: { configured: boolean } }>(
      "/ai/providers",
    )
      .then((p) => {
        setCloudConfigured(p.gemini.configured);
        setProvider(p.default_provider);
      })
      .catch(() => setError("Start the ReFit backend and refresh to connect."));
    const id = localStorage.getItem("refit-session");
    if (id)
      loadSession(id).catch(() => localStorage.removeItem("refit-session"));
  }, []);
  async function showTab(next: string) {
    setTab(next);
    if (next === "library")
      await run("Loading designs", async () =>
        setLibrary((await api<{ designs: Design[] }>("/designs")).designs),
      );
    if (next === "statistics")
      await run("Loading statistics", async () =>
        setStats(await api<Stats>("/statistics")),
      );
  }
  function reset() {
    setSession(null);
    setAnalysis(null);
    setMeasurements(null);
    setDesign(null);
    setStep(0);
    setPhoto(null);
    setNotes("");
    setAnswers({});
    setProposals([]);
    setIntact(false);
    setConsent(false);
    setError("");
    setNotice("");
    localStorage.removeItem("refit-session");
  }
  async function intake(e: FormEvent) {
    e.preventDefault();
    await run("Analysing your object", async () => {
      let s = session;
      if (!s) {
        s = await api<Session>("/sessions", { track, consent: true });
        setSession(s);
        localStorage.setItem("refit-session", s.id);
      }
      let rev = revision;
      if (photo) {
        const form = new FormData();
        form.append("image", photo);
        form.append("expected_revision", String(rev));
        form.append("user_text", notes);
        const uploaded = await api<Analysis>(`/sessions/${s.id}/image`, form);
        rev = uploaded.revision;
        setSession({ ...s, revision: rev });
      }
      const a = await api<Analysis>(`/sessions/${s.id}/analyze`, {
        expected_revision: rev,
        provider: photo ? provider : "manual",
        cloud_consent: cloud,
        user_text: notes,
      });
      setAnalysis(a);
      setMeasurements(null);
      if (a.workspace.analysis) {
        setObject(a.workspace.analysis.object_type);
        setComponent(a.workspace.analysis.component);
        setShape(a.workspace.analysis.cross_section_guess);
      } else {
        setObject(track === "adapt" ? "spoon" : "drawer_handle");
        setComponent(track === "adapt" ? "handle" : "drawer_mounting_holes");
      }
      setStep(1);
    });
  }
  async function confirm(e: FormEvent) {
    e.preventDefault();
    await run("Confirming object", async () => {
      const a = await api<Analysis>(`/sessions/${sid}/confirm-object`, {
        expected_revision: revision,
        object_type: object,
        component,
        cross_section: shape,
        handle_intact: track === "adapt" ? intact : null,
        confirmed_by_user: true,
      });
      setAnalysis(a);
      if (a.support.status === "supported") setStep(2);
    });
  }
  async function saveAnswers(e: FormEvent) {
    e.preventDefault();
    await run("Saving answers", async () => {
      const a = await api<Analysis>(`/sessions/${sid}/answers`, {
        expected_revision: revision,
        ...answers,
      });
      setAnalysis(a);
      if (a.support.status === "supported") setStep(2);
    });
  }
  async function getOptions() {
    await run("Checking design options", async () => {
      const result = await api<{ options: Proposal[] }>(
        `/sessions/${sid}/recommendations`,
      );
      setProposals(result.options);
      setMaterial(track === "adapt" ? "TPU" : "PETG");
      setStep(3);
    });
  }
  async function generate() {
    await run("Building CAD and validating your package", async () => {
      const body: Record<string, unknown> = {
        expected_revision: revision,
        variant,
        material,
      };
      if (track === "repair")
        body.mounting = {
          ...Object.fromEntries(
            Object.entries(mounting).map(([k, v]) => [k, Number(v)]),
          ),
          confirmed_by_user: mountConfirmed,
        };
      const result = await api<{ design: Design; revision: number }>(
        `/sessions/${sid}/generate`,
        body,
      );
      setDesign(result.design);
      setStep(4);
    });
  }
  async function refit(d: Design) {
    await run("Creating a Re-fit session", async () => {
      const r = await api<{ session: Session }>(`/designs/${d.id}/refit`, {
        consent: true,
      });
      await loadSession(r.session.id);
      setStep(1);
      setTab("studio");
      setNotice(
        "New Re-fit session created. Measure and confirm the updated dimensions; the original design stays saved.",
      );
    });
  }
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <a className="brand" href="/app/" aria-label="ReFit home">
          <span className="brand-icon">r.</span>ReFit
          <span className="brand-note">STUDIO</span>
        </a>
        <nav aria-label="Main navigation">
          {[
            ["studio", "Create a fit"],
            ["library", "Your designs"],
            ["statistics", "Statistics"],
          ].map(([id, label]) => (
            <button
              key={id}
              disabled={!!busy}
              className={tab === id ? "nav active" : "nav"}
              onClick={() => showTab(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <span className="local-label">
          <i />
          Local workspace
        </span>
      </header>
      <main id="main">
        <div className="page-heading">
          <div>
            <p className="eyebrow">GOOD OBJECTS DESERVE A SECOND CHANCE</p>
            <h1>
              {tab === "studio"
                ? "Make everyday fit you."
                : tab === "library"
                  ? "Made to keep."
                  : "Small changes. Real records."}
            </h1>
            <p className="lede">
              {tab === "studio"
                ? "Adapt an object to your needs, or replace the small part that broke. Start with what you have."
                : tab === "library"
                  ? "Your measured designs, fabrication files, and the next iteration."
                  : "Follow actual designs and reported fit trials. Every estimate stays labelled."}
            </p>
          </div>
          {session && tab === "studio" && (
            <button
              className="button secondary"
              disabled={!!busy}
              onClick={reset}
            >
              ＋ New project
            </button>
          )}
        </div>
        {error && (
          <div className="alert error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="alert" role="status">
            {notice}
          </div>
        )}
        {busy && (
          <div className="alert busy" role="status">
            <span className="spinner" />
            {busy}…
          </div>
        )}
        {(busy === "Analysing your object" ||
          analysis?.workspace.provider_status === "running") &&
          sid && (
            <button
              className="button secondary"
              onClick={async () => {
                try {
                  const s = await api<Session>(`/sessions/${sid}`);
                  setAnalysis(
                    await api<Analysis>(`/sessions/${sid}/analysis/cancel`, {
                      expected_revision: s.revision,
                    }),
                  );
                  setStep(1);
                } catch (e) {
                  setError(
                    e instanceof Error
                      ? e.message
                      : "Could not cancel analysis.",
                  );
                }
              }}
            >
              Cancel analysis / choose manually
            </button>
          )}
        {tab === "studio" && (
          <>
            <ol className="steps" aria-label="Project steps">
              {[
                "Show the object",
                "Confirm the need",
                "Measure the fit",
                "Choose a design",
                "Make & test",
              ].map((label, index) => (
                <li
                  key={label}
                  className={
                    step === index ? "current" : step > index ? "done" : ""
                  }
                >
                  <span>{step > index ? "✓" : index + 1}</span>
                  {label}
                </li>
              ))}
            </ol>
            <fieldset disabled={!!busy} className="workspace-fieldset">
              {step === 0 && (
                <div className="studio-grid">
                  <section className="card intake">
                    <Badge>01 / A BETTER FIT STARTS HERE</Badge>
                    <h2>What would you like to do?</h2>
                    <div className="track-picker">
                      {(["adapt", "repair"] as Track[]).map((t) => (
                        <button
                          type="button"
                          aria-pressed={track === t}
                          className={"track " + (track === t ? "selected" : "")}
                          disabled={!!session}
                          key={t}
                          onClick={() => {
                            setTrack(t);
                            setObject(
                              t === "adapt" ? "spoon" : "drawer_handle",
                            );
                            setComponent(
                              t === "adapt"
                                ? "handle"
                                : "drawer_mounting_holes",
                            );
                          }}
                        >
                          <span className="track-symbol">
                            {t === "adapt" ? "◎" : "⌁"}
                          </span>
                          <strong>{t === "adapt" ? "Adapt" : "Repair"}</strong>
                          <small>
                            {t === "adapt"
                              ? "A more comfortable utensil handle"
                              : "A replacement drawer pull"}
                          </small>
                        </button>
                      ))}
                    </div>
                    <form onSubmit={intake}>
                      <Field
                        label="Show us the object"
                        hint="Optional for manual selection. JPEG or PNG, up to 15 MB."
                      >
                        <input
                          type="file"
                          accept="image/jpeg,image/png"
                          onChange={(e) =>
                            setPhoto(e.target.files?.[0] ?? null)
                          }
                        />
                      </Field>
                      <Field label="What is difficult, or what broke?">
                        <textarea
                          rows={3}
                          maxLength={2000}
                          placeholder={
                            track === "adapt"
                              ? "For example: this spoon slips out of my hand."
                              : "For example: the pull is missing, but both mounting holes are visible."
                          }
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                        />
                      </Field>
                      <Field label="Object understanding">
                        <select
                          value={provider}
                          onChange={(e) => setProvider(e.target.value)}
                        >
                          <option value="ollama">Local AI / Ollama</option>
                          <option value="manual">
                            Choose the object myself
                          </option>
                          <option value="gemini" disabled={!cloudConfigured}>
                            Cloud AI / Gemini
                            {!cloudConfigured ? " — not configured" : ""}
                          </option>
                        </select>
                      </Field>
                      {provider === "gemini" && photo && (
                        <label className="check">
                          <input
                            type="checkbox"
                            checked={cloud}
                            onChange={(e) => setCloud(e.target.checked)}
                          />
                          Send the resized photo and notes to Gemini for this
                          analysis.
                        </label>
                      )}
                      <label className="check">
                        <input
                          type="checkbox"
                          required
                          checked={consent}
                          onChange={(e) => setConsent(e.target.checked)}
                        />
                        I agree to store this project and its photos in this
                        local workspace.
                      </label>
                      <button
                        className="button"
                        type="submit"
                        disabled={
                          !consent ||
                          (provider === "gemini" && !!photo && !cloud)
                        }
                      >
                        Continue ↗
                      </button>
                    </form>
                  </section>
                  <aside className="aside-stack">
                    <div className="green-card">
                      <span className="mini-label">THE REFIT APPROACH</span>
                      <div className="orbit-art" aria-hidden="true">
                        <div />
                        <div />
                        <div />
                        <span>↻</span>
                      </div>
                      <h2>
                        Keep the object.
                        <br />
                        Change the fit.
                      </h2>
                      <p>
                        A measured attachment can make a familiar object easier
                        to use, or bring a broken one back into reach.
                      </p>
                      <div className="tags">
                        <span>SDG 10 / Inclusion</span>
                        <span>SDG 12 / Reuse</span>
                      </div>
                    </div>
                    <div className="card compact">
                      <h3>Measure first. Make second.</h3>
                      <p>
                        AI helps identify the object. Confirmed measurements set
                        the dimensions. A physical trial proves the fit.
                      </p>
                      <a
                        href="/api/fit-sheet.pdf"
                        target="_blank"
                        rel="noreferrer"
                      >
                        Download the printable Fit Sheet ↗
                      </a>
                    </div>
                  </aside>
                </div>
              )}
              {step === 1 && analysis && (
                <div className="studio-grid">
                  <section className="card">
                    <Badge>02 / YOU HAVE THE FINAL SAY</Badge>
                    <h2>Does this look right?</h2>
                    <p className="muted">
                      {analysis.workspace.message ||
                        "Choose the object and the part you want to work on."}
                    </p>
                    {analysis.workspace.analysis && (
                      <div className="insight">
                        <Badge>
                          {analysis.workspace.analysis.confidence} AI confidence
                        </Badge>
                        <h3>Visible observations</h3>
                        <ul>
                          {analysis.workspace.analysis.visible_facts.map(
                            (v, i) => (
                              <li key={i}>{v}</li>
                            ),
                          )}
                        </ul>
                        <h3>Unconfirmed interpretations</h3>
                        <ul>
                          {analysis.workspace.analysis.inferences.map(
                            (v, i) => (
                              <li key={i}>{v}</li>
                            ),
                          )}
                        </ul>
                      </div>
                    )}
                    <form onSubmit={confirm}>
                      <div className="field-grid">
                        <Field label="Object">
                          <select
                            value={object}
                            onChange={(e) => setObject(e.target.value)}
                          >
                            {(track === "adapt"
                              ? ["spoon", "fork", "knife", "other", "unknown"]
                              : ["drawer_handle", "other", "unknown"]
                            ).map((o) => (
                              <option key={o} value={o}>
                                {pretty(o)}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <Field label="Target component">
                          <select
                            value={component}
                            onChange={(e) => setComponent(e.target.value)}
                          >
                            {[
                              "handle",
                              "drawer_mounting_holes",
                              "other",
                              "unknown",
                            ].map((o) => (
                              <option key={o} value={o}>
                                {pretty(o)}
                              </option>
                            ))}
                          </select>
                        </Field>
                      </div>
                      {track === "adapt" && (
                        <>
                          <Field
                            label="Handle cross-section"
                            hint="Confirm by looking at the end. If unsure, do not guess."
                          >
                            <select
                              value={shape}
                              onChange={(e) => setShape(e.target.value)}
                            >
                              {["round", "oval", "flat", "unknown"].map((v) => (
                                <option key={v}>{v}</option>
                              ))}
                            </select>
                          </Field>
                          <label className="check">
                            <input
                              type="checkbox"
                              checked={intact}
                              onChange={(e) => setIntact(e.target.checked)}
                            />
                            The handle is intact; the attachment will avoid
                            food, mouth and blade contact.
                          </label>
                        </>
                      )}
                      <button className="button secondary" type="submit">
                        Confirm object
                      </button>
                    </form>
                    {analysis.support.status === "unsupported" && (
                      <p className="alert error">{analysis.support.reason}</p>
                    )}
                    {analysis.questions.length > 0 && (
                      <form className="question-form" onSubmit={saveAnswers}>
                        <h3>A little more about the fit</h3>
                        {analysis.questions.map((q) => (
                          <Field key={q.id} label={q.prompt}>
                            <select
                              required
                              value={answers[q.id] || ""}
                              onChange={(e) =>
                                setAnswers({
                                  ...answers,
                                  [q.id]: e.target.value,
                                })
                              }
                            >
                              <option value="">Choose an answer</option>
                              {q.options.map((o) => (
                                <option key={o.id} value={o.id}>
                                  {o.label}
                                </option>
                              ))}
                            </select>
                          </Field>
                        ))}
                        <button className="button" type="submit">
                          Continue to measurements ↗
                        </button>
                      </form>
                    )}
                    {analysis.workspace.confirmation && (
                      <details>
                        <summary>Change my answers</summary>
                        <Field label="Updated need">
                          <select
                            value={
                              answers.difficulty || answers.repair_case || ""
                            }
                            onChange={(e) =>
                              setAnswers(
                                track === "adapt"
                                  ? { difficulty: e.target.value }
                                  : { repair_case: e.target.value },
                              )
                            }
                          >
                            <option value="">Choose an updated need</option>
                            {(track === "adapt"
                              ? [
                                  "slipping",
                                  "pain",
                                  "cannot_wrap_fingers",
                                  "weak_grip",
                                  "other",
                                ]
                              : [
                                  "missing_pull_visible_holes",
                                  "hidden_mounting",
                                  "other",
                                  "not_sure",
                                ]
                            ).map((v) => (
                              <option key={v} value={v}>
                                {pretty(v)}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <button
                          className="button secondary"
                          disabled={!Object.keys(answers).length}
                          onClick={() =>
                            run("Updating your need", async () => {
                              setAnalysis(
                                await api<Analysis>(
                                  `/sessions/${sid}/answers`,
                                  { expected_revision: revision, ...answers },
                                ),
                              );
                              setAnswers({});
                            })
                          }
                        >
                          Save updated need
                        </button>
                      </details>
                    )}
                    {analysis.support.status === "supported" && (
                      <button className="button" onClick={() => setStep(2)}>
                        Continue to measurements ↗
                      </button>
                    )}
                  </section>
                  <aside className="card compact">
                    {analysis.workspace.image && (
                      <img
                        className="output-image"
                        alt="Your uploaded object"
                        src={`/api/sessions/${sid}/image`}
                      />
                    )}
                    <h3>A clear boundary</h3>
                    <p>
                      Adapt supports intact utensil handles. Repair supports
                      missing drawer pulls with visible holes and an intact
                      mounting surface.
                    </p>
                    <p>
                      Hidden threads, damaged structures, and food-contact parts
                      need a different approach.
                    </p>
                    <button className="button secondary" onClick={reset}>
                      Start another project
                    </button>
                  </aside>
                </div>
              )}
              {step === 2 && sid && (
                <Measure
                  key={sid}
                  sid={sid}
                  track={track}
                  revision={revision}
                  data={measurements}
                  setData={setMeasurements}
                  run={run}
                  next={getOptions}
                />
              )}
              {step === 3 && (
                <section className="card">
                  <Badge>04 / CHOOSE, THEN TEST</Badge>
                  <h2>A few ways forward.</h2>
                  <div className="proposal-grid">
                    {proposals.map((p) => (
                      <button
                        key={p.variant}
                        className={
                          "proposal " +
                          (variant === p.variant ? "selected" : "")
                        }
                        aria-pressed={variant === p.variant}
                        onClick={() => setVariant(p.variant)}
                      >
                        <span className="part-symbol" aria-hidden="true">
                          {track === "adapt" ? "▰" : "⊓"}
                        </span>
                        <h3>{pretty(p.variant)}</h3>
                        <p>{p.reason}</p>
                        <span className="muted small">
                          {track === "adapt"
                            ? `${p.parameters.outer_width_mm} × ${p.parameters.outer_thickness_mm} mm outside`
                            : `${p.parameters.standoff_mm} mm stand-off`}
                        </span>
                      </button>
                    ))}
                  </div>
                  <div className="field-grid">
                    <Field label="Material">
                      <select
                        value={material}
                        onChange={(e) => setMaterial(e.target.value)}
                      >
                        {(track === "adapt" ? ["TPU"] : ["PETG", "PLA"]).map(
                          (m) => (
                            <option key={m}>{m}</option>
                          ),
                        )}
                      </select>
                    </Field>
                  </div>
                  {track === "repair" && (
                    <div className="insight">
                      <h3>Confirm the mounting hardware</h3>
                      <p>
                        Through-bolts pass through the drawer face, bosses and
                        bar, with exposed nuts on top.
                      </p>
                      <div className="field-grid">
                        {[
                          ["bolt_diameter_mm", "Bolt diameter"],
                          ["face_thickness_mm", "Drawer-face thickness"],
                          ["bolt_length_mm", "Bolt usable length"],
                          ["nut_height_mm", "Nut height"],
                        ].map(([key, label]) => (
                          <Field key={key} label={label + " (mm)"}>
                            <input
                              type="number"
                              min="0.01"
                              step="any"
                              value={mounting[key] ?? ""}
                              onChange={(e) =>
                                setMounting({
                                  ...mounting,
                                  [key]: e.target.value,
                                })
                              }
                            />
                          </Field>
                        ))}
                      </div>
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={mountConfirmed}
                          onChange={(e) => setMountConfirmed(e.target.checked)}
                        />
                        I measured this hardware and confirmed that
                        through-bolts and external nuts suit this drawer.
                      </label>
                    </div>
                  )}
                  <p className="muted">
                    {track === "adapt"
                      ? "Test the 10 mm fit coupon before printing the full sleeve."
                      : "Light-duty only. Check layer orientation, mounting and strength in a physical trial."}
                  </p>
                  <div className="actions">
                    <button
                      className="button secondary"
                      onClick={() => setStep(2)}
                    >
                      Back to measurements
                    </button>
                    <button
                      className="button"
                      disabled={
                        track === "repair" &&
                        (!mountConfirmed ||
                          [
                            "bolt_diameter_mm",
                            "face_thickness_mm",
                            "bolt_length_mm",
                            "nut_height_mm",
                          ].some((k) => !mounting[k]))
                      }
                      onClick={generate}
                    >
                      Generate measured package ↗
                    </button>
                  </div>
                </section>
              )}
              {step === 4 && design && (
                <Results
                  key={design.id}
                  design={design}
                  refit={() => refit(design)}
                  run={run}
                  notify={setNotice}
                />
              )}
            </fieldset>
          </>
        )}
        {tab === "library" &&
          (library.length === 0 ? (
            <div className="card empty">
              <span>↻</span>
              <h2>Your first fit starts here.</h2>
              <p>
                Completed designs and downloads will appear in this workspace.
              </p>
              <button className="button" onClick={() => setTab("studio")}>
                Create a fit ↗
              </button>
            </div>
          ) : (
            <div className="library-grid">
              {library.map((d) => (
                <article className="card design-card" key={d.id}>
                  <img
                    alt="Illustrative design preview"
                    src={fileUrl(d.id, "final_concept.png")}
                  />
                  <Badge>{d.spec.track}</Badge>
                  <h3>
                    {pretty(d.spec.object_type)} / {d.spec.variant}
                  </h3>
                  <p>
                    {pretty(d.spec.verification_level)} · {d.spec.material}
                  </p>
                  <div className="actions">
                    <button
                      className="button secondary"
                      onClick={() => {
                        setDesign(d);
                        setStep(4);
                        setTab("studio");
                      }}
                    >
                      View files
                    </button>
                    <button className="text-button" onClick={() => refit(d)}>
                      Re-fit ↗
                    </button>
                  </div>
                </article>
              ))}
            </div>
          ))}
        {tab === "statistics" && stats && (
          <>
            <div className="stats-grid">
              {[
                [
                  "Designs generated",
                  stats.designs_generated,
                  "Files created, not successful repairs",
                ],
                [
                  "Adapt / Repair",
                  `${stats.adapt_designs} / ${stats.repair_designs}`,
                  "Both core product tracks",
                ],
                [
                  "Reported fit trials",
                  stats.reported_fit_trials,
                  `${stats.reported_fits} reported fits`,
                ],
                [
                  "Objects kept in use",
                  stats.reported_items_kept_in_use,
                  "User reported; Re-fit chains counted once",
                ],
              ].map(([label, value, detail]) => (
                <div className="card stat" key={String(label)}>
                  <span className="muted">{label}</span>
                  <strong>{value}</strong>
                  <small>{detail}</small>
                </div>
              ))}
            </div>
            <div className="studio-grid">
              <div className="green-card">
                <span className="mini-label">MATERIAL / ESTIMATED</span>
                <strong className="big-number">
                  {stats.solid_material_estimate_g.toFixed(1)}
                  <small> g</small>
                </strong>
                <p>
                  Combined solid material estimate for generated designs. This
                  is not actual filament consumed or waste avoided.
                </p>
              </div>
              <section className="card">
                <h2>Evidence over assumptions.</h2>
                <p>
                  {stats.sessions_started} sessions started. Physical
                  measurement accuracy awaits real-object evaluation.
                </p>
                <ul>
                  {stats.limitations.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
                <p>No CO₂ or cost savings are inferred.</p>
              </section>
            </div>
          </>
        )}
      </main>
      <footer>
        <span className="brand">
          ReFit<span className="brand-note">ADAPT. REPAIR. KEEP USING.</span>
        </span>
        <span>Measured dimensions. Honest limits.</span>
      </footer>
    </>
  );
}
