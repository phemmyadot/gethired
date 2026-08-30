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
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" onClick={onClose} />
      <div className="relative w-[540px] h-full bg-surface overflow-y-auto flex flex-col shadow-card-hover">
        <div className="flex items-start justify-between px-7 py-6 border-b border-border sticky top-0 bg-surface z-10">
          <div className="min-w-0">
            <div className="font-display text-xl font-semibold text-ink leading-snug">{match.job_title}</div>
            <div className="text-sm text-muted flex items-center gap-2 mt-2 flex-wrap">
              <span>{match.company}{match.location ? ` · ${match.location}` : ""}</span>
              <WorkModeTag mode={match.work_mode} />
              {match.apply_url && (
                <a
                  href={match.apply_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-medium text-accent hover:underline"
                >
                  View listing →
                </a>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <ScoreBadge score={match.score} />
            <button onClick={onClose} className="text-muted hover:text-ink text-xl leading-none w-8 h-8 flex items-center justify-center rounded-full hover:bg-panel transition-colors">×</button>
          </div>
        </div>

        <div className="px-7 py-6 flex flex-col gap-7">
          {/* Resume used + apply flow */}
          <section>
            <div className="text-xs font-medium text-muted uppercase tracking-wide mb-2.5">Resume matched</div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium bg-accent-soft text-accent px-3 py-1.5 rounded-full">
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
                  className="text-sm font-semibold px-4 py-1.5 rounded-full bg-ink text-paper hover:bg-ink/85 disabled:opacity-50 transition-colors"
                >
                  {generating ? "Generating…" : "Generate cover letter"}
                </button>
              ) : null}
            </div>
            {error && <div className="text-sm text-rose mt-2.5">{error}</div>}

            {!match.applied && coverLetter && (
              <div className="mt-5 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-medium text-muted uppercase tracking-wide">Cover letter — copy and paste into the application</div>
                  <button onClick={handleCopy} className="text-xs font-semibold text-accent hover:underline">
                    {copied ? "Copied ✓" : "Copy"}
                  </button>
                </div>
                <pre className="text-sm text-ink leading-relaxed whitespace-pre-wrap font-sans bg-panel rounded-xl p-5">
                  {coverLetter}
                </pre>

                <div className="flex items-center gap-3">
                  {match.apply_url && (
                    <a
                      href={match.apply_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium text-accent hover:underline flex-1 truncate"
                    >
                      Open application page →
                    </a>
                  )}
                  <button
                    onClick={handleMarkApplied}
                    disabled={marking}
                    className="text-sm font-semibold px-4 py-2 rounded-full bg-teal text-white hover:bg-teal/90 disabled:opacity-50 transition-colors whitespace-nowrap"
                  >
                    {marking ? "Saving…" : "Mark as applied"}
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* Claude reasoning */}
          <section>
            <div className="text-xs font-medium text-muted uppercase tracking-wide mb-2.5">Claude's assessment</div>
            <p className="text-sm text-ink leading-relaxed bg-panel rounded-xl p-5">
              {match.reasoning}
            </p>
          </section>

          {/* Selling points */}
          {match.selling_points?.length > 0 && (
            <section>
              <div className="text-xs font-medium text-muted uppercase tracking-wide mb-2.5">Selling points used</div>
              <ul className="flex flex-col gap-2">
                {match.selling_points.map((p, i) => (
                  <li key={i} className="flex gap-2.5 text-sm text-ink">
                    <span className="text-teal mt-0.5">✓</span> {p}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Missing skills */}
          {match.missing_skills?.length > 0 && (
            <section>
              <div className="text-xs font-medium text-muted uppercase tracking-wide mb-2.5">Gaps identified</div>
              <div className="flex flex-wrap gap-2">
                {match.missing_skills.map((s, i) => (
                  <span key={i} className="text-xs font-medium px-2.5 py-1 bg-rose-soft text-rose rounded-full">
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
