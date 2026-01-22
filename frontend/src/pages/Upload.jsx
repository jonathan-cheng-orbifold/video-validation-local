// frontend/src/pages/Upload.jsx

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadVideo } from "../api";

export default function Upload() {
  const [file, setFile] = useState(null);
  const [folder, setFolder] = useState("");
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const navigate = useNavigate();

  const fileInfo = useMemo(() => {
    if (!file) return null;
    return {
      name: file.name,
      sizeMB: (file.size / (1024 * 1024)).toFixed(2),
      type: file.type || "unknown",
    };
  }, [file]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (!file) return;

    setBusy(true);
    setProgress(0);

    try {
      const resp = await uploadVideo(file, folder, {
        onProgress: (p) => setProgress(p),
      });

      navigate(`/status/${resp.upload_id}`);
    } catch (err) {
      setError(err?.message || "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h1 className="h1">Upload Video</h1>
      <p className="muted">
        Upload an ego/exo video. Validation runs immediately after upload.
      </p>

      <form onSubmit={onSubmit} className="stack">
        {/* Folder input */}
        <div className="field">
          <label className="label">Wasabi Subfolder (optional)</label>
          <input
            type="text"
            placeholder="e.g. task-123/session-001"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            disabled={busy}
          />
          <div className="help">
            Upload path:{" "}
            <span className="mono">
              uploads/{folder ? folder.replace(/^\/+/, "") : "<root>"}/
            </span>
          </div>
        </div>

        {/* File input */}
        <div className="field">
          <label className="label">Video File</label>
          <input
            type="file"
            accept="video/mp4,video/quicktime,video/*"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            disabled={busy}
          />

          {fileInfo && (
            <div className="help">
              <span><b>{fileInfo.name}</b></span>
              <span className="dot">•</span>
              <span>{fileInfo.sizeMB} MB</span>
              <span className="dot">•</span>
              <span>{fileInfo.type}</span>
            </div>
          )}
        </div>

        {/* Progress */}
        {busy && (
          <div className="progress">
            <div
              className="progress-bar"
              style={{ width: `${progress}%` }}
            />
            <div className="progress-label">{progress}%</div>
          </div>
        )}

        {/* Error */}
        {error && <div className="alert">{error}</div>}

        <button className="btn" type="submit" disabled={!file || busy}>
          {busy ? "Uploading..." : "Upload & Validate"}
        </button>
      </form>
    </div>
  );
}
