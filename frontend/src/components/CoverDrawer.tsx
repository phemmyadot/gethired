import { type Application } from "../lib/api";

export function CoverDrawer({ app, onClose }: { app: Application; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" onClick={onClose} />
      <div className="relative w-[560px] h-full bg-surface overflow-y-auto flex flex-col shadow-card-hover">
        <div className="flex items-start justify-between px-7 py-6 border-b border-border sticky top-0 bg-surface">
          <div>
            <div className="font-display text-xl font-semibold text-ink">{app.job_title}</div>
            <div className="text-sm text-muted mt-1">{app.company} · {app.resume_label}</div>
          </div>
          <button onClick={onClose} className="text-muted hover:text-ink text-xl w-8 h-8 flex items-center justify-center rounded-full hover:bg-panel transition-colors">×</button>
        </div>
        <div className="px-7 py-6">
          <div className="text-xs font-medium text-muted uppercase tracking-wide mb-3">Cover letter sent</div>
          <pre className="text-sm text-ink leading-relaxed whitespace-pre-wrap font-sans bg-panel rounded-xl p-5">
            {app.cover_letter || "No cover letter on record."}
          </pre>
        </div>
      </div>
    </div>
  );
}
