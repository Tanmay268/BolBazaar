import { useCallback, useEffect, useState } from "react";
import { ApiFailure, api } from "../api";
import { timeAgo } from "../format";
import type { BugReportRow } from "../types";

const STATUSES = [["open", "Open"], ["in_progress", "In progress"], ["resolved", "Resolved"], ["wontfix", "Won't fix"]] as const;
const CATEGORY: Record<string, string> = { broken: "Broken", wrong_result: "Wrong result", voice: "Voice", suggestion: "Suggestion", other: "Other" };

/** Admin triage: newest reports first, expand for details, set status and leave a note the reporter can see. */
export function AdminBugs() {
  const [rows, setRows] = useState<BugReportRow[] | null>(null);
  const [filter, setFilter] = useState("open");
  const [open, setOpen] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setRows(null);
    api.adminBugReports(filter || undefined).then((r) => setRows(r.reports)).catch((e) => { setRows([]); setError(e instanceof ApiFailure ? e.message : "Couldn't load reports."); });
  }, [filter]);
  useEffect(load, [load]);

  async function setStatus(r: BugReportRow, status: string) {
    try { await api.updateBugReport(r.id, status, notes[r.id] ?? r.adminNote ?? undefined); load(); }
    catch (e) { setError(e instanceof ApiFailure ? e.message : "Couldn't update."); }
  }

  return (
    <section className="mpanel">
      <header><h2>Bug reports{rows ? ` (${rows.length})` : ""}</h2></header>
      <div className="bug-filter">
        <label>Show <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All</option>{STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      </div>
      {error && <div className="error cat-error" role="alert">{error}</div>}
      {!rows ? <div className="skel-list"><div className="skel" /><div className="skel" /></div> : !rows.length ? <p className="empty empty-sm cat-note">No reports here.</p> : (
        <div className="bug-list">
          {rows.map((r) => (
            <div key={r.id} className="bug-item">
              <button className="bug-head" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>
                <span className="chip">{CATEGORY[r.category] ?? r.category}</span>
                <b>{r.title}</b>
                <small>{r.reporter} ({r.role}) · {timeAgo(r.createdAt)}</small>
                <span className={r.status === "resolved" ? "chip" : "chip-red"}>{STATUSES.find(([v]) => v === r.status)?.[1] ?? r.status}</span>
              </button>
              {open === r.id && (
                <div className="bug-detail">
                  <p>{r.description}</p>
                  {Object.keys(r.context).length > 0 && <pre>{JSON.stringify(r.context, null, 2)}</pre>}
                  <small>ID {r.id}</small>
                  <div className="bug-actions">
                    <input value={notes[r.id] ?? r.adminNote ?? ""} onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })} placeholder="Note for the reporter (optional)" maxLength={300} aria-label="Note" />
                    {STATUSES.filter(([v]) => v !== r.status).map(([v, l]) => <button key={v} className="btn btn-outline btn-sm" onClick={() => void setStatus(r, v)}>{l}</button>)}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
