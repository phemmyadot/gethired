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
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" onClick={onClose} />
      <div className="relative bg-surface rounded-xl2 shadow-card-hover w-[440px] p-7 flex flex-col gap-5">
        <div className="font-display text-xl font-semibold text-ink">Upload resume</div>

        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-muted uppercase tracking-wide">Label (e.g. "Backend Engineer")</label>
          <input
            className="bg-panel text-ink text-sm rounded-xl px-4 py-2.5 outline-none focus:ring-2 focus:ring-accent/40 transition-shadow"
            value={label}
            onChange={e => setLabel(e.target.value)}
            placeholder="Backend Engineer"
          />
        </div>

        <div
          className="border-2 border-dashed border-border rounded-xl p-8 flex flex-col items-center gap-2 cursor-pointer hover:border-accent/50 hover:bg-accent-soft/40 transition-colors"
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

        {error && <div className="text-sm text-rose">{error}</div>}

        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onClose} className="text-sm font-medium text-muted px-4 py-2.5 hover:text-ink transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="text-sm font-semibold bg-ink text-paper px-5 py-2.5 rounded-full hover:bg-ink/85 disabled:opacity-50 transition-colors"
          >
            {loading ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}
