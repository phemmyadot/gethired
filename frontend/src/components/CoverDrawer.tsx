import { type Application } from "../lib/api";

export function CoverDrawer({ app, onClose }: { app: Application; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/70" onClick={onClose} />
      <div className="relative w-[560px] h-full bg-surface border-l border-border overflow-y-auto flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-surface">
          <div>
            <div className="font-semibold text-text">{app.job_title}</div>
            <div className="text-sm text-muted">{app.company} · {app.resume_label}</div>
          </div>
          <button onClick={onClose} className="text-muted hover:text-text text-xl">×</button>
        </div>
        <div className="px-6 py-5">
          <div className="text-xs text-muted mb-3">Cover letter sent</div>
          <pre className="text-sm text-text leading-relaxed whitespace-pre-wrap font-sans bg-panel border border-border rounded p-5">
            {app.cover_letter || "No cover letter on record."}
          </pre>
        </div>
      </div>
    </div>
  );
}
