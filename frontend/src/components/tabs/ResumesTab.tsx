import { useState } from "react";
import { deleteResume, type Resume } from "../../lib/api";
import { UploadModal } from "../UploadModal";

export function ResumesTab({ resumes, onRefresh }: { resumes: Resume[]; onRefresh: () => void }) {
  const [showUpload, setShowUpload] = useState(false);

  async function handleDelete(id: string) {
    if (!confirm("Remove this resume?")) return;
    await deleteResume(id);
    onRefresh();
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted">{resumes.length} active resume{resumes.length !== 1 ? "s" : ""}</div>
        <button
          onClick={() => setShowUpload(true)}
          className="text-sm font-semibold bg-ink text-paper px-4 py-2.5 rounded-full hover:bg-ink/85 transition-colors"
        >
          + Upload resume
        </button>
      </div>

      <div className="flex flex-col gap-3">
        {resumes.map(r => (
          <div key={r.id} className="flex items-center gap-4 bg-surface rounded-xl2 border border-border/60 shadow-card px-5 py-4">
            <div className="w-11 h-11 rounded-xl bg-accent-soft flex items-center justify-center text-xl shrink-0">📄</div>
            <div className="flex-1 min-w-0">
              <div className="font-medium text-ink">{r.label}</div>
              <div className="text-xs text-muted truncate mt-0.5">{r.filename}</div>
            </div>
            <div className="text-xs text-muted whitespace-nowrap">
              {new Date(r.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
            </div>
            <button
              onClick={() => handleDelete(r.id)}
              className="text-xs font-medium text-muted hover:text-rose transition-colors ml-2"
            >
              Remove
            </button>
          </div>
        ))}
        {resumes.length === 0 && (
          <div className="py-16 text-center text-muted text-sm bg-surface rounded-xl2 border border-dashed border-border">
            No resumes yet. Upload one to get started.
          </div>
        )}
      </div>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onDone={() => { setShowUpload(false); onRefresh(); }}
        />
      )}
    </div>
  );
}
