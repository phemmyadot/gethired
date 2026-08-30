import { useState, useRef } from "react";
import { uploadResume } from "../lib/api";

export function UploadModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [label, setLabel] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleSubmit() {
    if (!file || !label.trim()) { setError("Label and file are required."); return; }
    setLoading(true);
    try {
      await uploadResume(file, label.trim());
      onDone();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-ink/80" onClick={onClose} />
      <div className="relative bg-surface border border-border rounded w-[420px] p-6 flex flex-col gap-4">
        <div className="text-sm font-semibold text-text">Upload resume</div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">Label (e.g. "Backend Engineer")</label>
          <input
            className="bg-panel border border-border text-text text-sm rounded px-3 py-2 outline-none focus:border-teal/60 transition-colors"
            value={label}
            onChange={e => setLabel(e.target.value)}
            placeholder="Backend Engineer"
          />
        </div>

        <div
          className="border-2 border-dashed border-border rounded p-6 flex flex-col items-center gap-2 cursor-pointer hover:border-teal/40 transition-colors"
          onClick={() => inputRef.current?.click()}
        >
          <span className="text-2xl">📄</span>
          <span className="text-sm text-muted">
            {file ? file.name : "Click to select PDF or DOCX"}
          </span>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt"
            className="hidden"
            onChange={e => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {error && <div className="text-xs text-rose">{error}</div>}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="text-sm text-muted px-4 py-2 hover:text-text transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="text-sm bg-teal text-ink font-semibold px-4 py-2 rounded hover:bg-teal/90 disabled:opacity-50 transition-colors"
          >
            {loading ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}
