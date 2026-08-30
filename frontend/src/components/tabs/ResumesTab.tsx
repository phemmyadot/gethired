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
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted">{resumes.length} active resume{resumes.length !== 1 ? "s" : ""}</div>
        <button
          onClick={() => setShowUpload(true)}
          className="text-xs bg-teal text-ink font-semibold px-3 py-1.5 rounded hover:bg-teal/90 transition-colors"
        >
          + Upload resume
        </button>
      </div>

      <div className="flex flex-col gap-2">
        {resumes.map(r => (
          <div key={r.id} className="flex items-center gap-4 bg-panel border border-border rounded px-4 py-3">
            <span className="text-lg">📄</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-text">{r.label}</div>
              <div className="text-xs text-muted truncate">{r.filename}</div>
            </div>
            <div className="text-xs text-muted whitespace-nowrap">
              {new Date(r.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
            </div>
            <button
              onClick={() => handleDelete(r.id)}
              className="text-xs text-muted hover:text-rose transition-colors ml-2"
            >
              remove
            </button>
          </div>
        ))}
        {resumes.length === 0 && (
          <div className="py-12 text-center text-muted text-sm border border-dashed border-border rounded">
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
