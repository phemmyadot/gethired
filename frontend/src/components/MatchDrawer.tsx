import { useState } from "react";
import { generateCoverLetterForMatch, markMatchApplied, type Match } from "../lib/api";
import { ScoreBadge, StatusPill, WorkModeTag } from "./ui";

export function MatchDrawer({ match, onClose, onApplied, onViewApplication }: {
  match: Match; onClose: () => void; onApplied: () => void; onViewApplication: (applicationId: string) => void;
}) {
  const [generating, setGenerating] = useState(false);
  const [marking, setMarking] = useState(false);
  const [error, setError] = useState("");
  const [coverLetter, setCoverLetter] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const result = await generateCoverLetterForMatch(match.job_id, match.resume_id);
      setCoverLetter(result.cover_letter);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleCopy() {
    if (!coverLetter) return;
    await navigator.clipboard.writeText(coverLetter);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleMarkApplied() {
    setMarking(true);
    setError("");
    try {
      await markMatchApplied(match.job_id, match.resume_id, coverLetter ?? "");
      onApplied();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setMarking(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/70" onClick={onClose} />
      <div className="relative w-[520px] h-full bg-surface border-l border-border overflow-y-auto flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-surface z-10">
          <div>
            <div className="font-semibold text-text">{match.job_title}</div>
            <div className="text-sm text-muted flex items-center gap-2">
              <span>{match.company}</span>
              <WorkModeTag mode={match.work_mode} />
              {match.apply_url && (
                <a
                  href={match.apply_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-sky hover:underline"
                >
                  view listing →
                </a>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ScoreBadge score={match.score} />
            <button onClick={onClose} className="text-muted hover:text-text text-xl leading-none">×</button>
          </div>
        </div>

        <div className="px-6 py-5 flex flex-col gap-6">
          {/* Resume used + apply flow */}
          <section>
            <div className="text-xs text-muted mb-2">Resume matched</div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm bg-teal/10 border border-teal/30 text-teal px-3 py-1 rounded">
                {match.resume_label}
              </span>
              {match.applied ? (
                match.application_id ? (
                  <button
                    onClick={() => onViewApplication(match.application_id!)}
                    className="hover:opacity-80 transition-opacity"
                  >
                    <StatusPill status={match.apply_status ?? "applied"} />
                  </button>
                ) : (
                  <StatusPill status={match.apply_status ?? "applied"} />
                )
              ) : !coverLetter ? (
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="text-xs bg-teal text-ink font-semibold px-3 py-1.5 rounded hover:bg-teal/90 disabled:opacity-50 transition-colors"
                >
                  {generating ? "Generating…" : "Generate cover letter"}
                </button>
              ) : null}
            </div>
            {error && <div className="text-xs text-rose mt-2">{error}</div>}

            {!match.applied && coverLetter && (
              <div className="mt-4 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs text-muted">Cover letter — copy and paste into the application</div>
                  <button onClick={handleCopy} className="text-xs text-teal hover:underline">
                    {copied ? "Copied ✓" : "Copy"}
                  </button>
                </div>
                <pre className="text-sm text-text leading-relaxed whitespace-pre-wrap font-sans bg-panel border border-border rounded p-4">
                  {coverLetter}
                </pre>

                <div className="flex items-center gap-2">
                  {match.apply_url && (
                    <a
                      href={match.apply_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-sky hover:underline flex-1 truncate"
                    >
                      Open application page →
                    </a>
                  )}
                  <button
                    onClick={handleMarkApplied}
                    disabled={marking}
                    className="text-xs bg-teal text-ink font-semibold px-3 py-1.5 rounded hover:bg-teal/90 disabled:opacity-50 transition-colors whitespace-nowrap"
                  >
                    {marking ? "Saving…" : "Mark as applied"}
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* Claude reasoning */}
          <section>
            <div className="text-xs text-muted mb-2">Claude's assessment</div>
            <p className="text-sm text-text leading-relaxed bg-panel border border-border rounded p-4">
              {match.reasoning}
            </p>
          </section>

          {/* Selling points */}
          {match.selling_points?.length > 0 && (
            <section>
              <div className="text-xs text-muted mb-2">Selling points used</div>
              <ul className="flex flex-col gap-1.5">
                {match.selling_points.map((p, i) => (
                  <li key={i} className="flex gap-2 text-sm text-text">
                    <span className="text-teal mt-0.5">✓</span> {p}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Missing skills */}
          {match.missing_skills?.length > 0 && (
            <section>
              <div className="text-xs text-muted mb-2">Gaps identified</div>
              <div className="flex flex-wrap gap-2">
                {match.missing_skills.map((s, i) => (
                  <span key={i} className="text-xs px-2 py-1 bg-rose/10 border border-rose/30 text-rose rounded">
                    {s}
                  </span>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
