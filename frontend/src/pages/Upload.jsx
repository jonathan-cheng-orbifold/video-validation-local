// frontend/src/pages/Upload.jsx

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadVideo } from "../api";

function formatBytesPerSec(bps) {
  if (!Number.isFinite(bps) || bps <= 0) return "—";
  const units = ["B/s", "KB/s", "MB/s", "GB/s"];
  let i = 0;
  let v = bps;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function Upload() {
  const [file, setFile] = useState(null);
  const [folder, setFolder] = useState("");
  const [progress, setProgress] = useState(0);
  const [uploadSpeedBps, setUploadSpeedBps] = useState(0);
  const [busy, setBusy] = useState(false);
  const phase =
    busy && progress >= 100 ? "validating" :
    busy ? "uploading" :
    "idle";
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
    setUploadSpeedBps(0);

    try {
      const resp = await uploadVideo(file, folder, {
        onProgress: ({ percent, bps }) => {
          setProgress(percent);
          setUploadSpeedBps(bps);
        },
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
          <div>
            <div className="progress">
              <div
                className="progress-bar"
                style={{
                  width: phase === "validating" ? "100%" : `${progress}%`,
                  opacity: phase === "validating" ? 0.6 : 1,
                }}
              />
            </div>

            <div className="progress-label">
              {phase === "uploading" && (
                <>
                  Uploading… {progress}% • {formatBytesPerSec(uploadSpeedBps)}
                </>
              )}

              {phase === "validating" && (
                <>
                  Upload complete — validating video…
                </>
              )}
            </div>
          </div>
        )}

        {/* Error */}
        {error && <div className="alert">{error}</div>}

        <button className="btn" type="submit" disabled={!file || busy}>
          {phase === "uploading" && "Uploading..."}
          {phase === "validating" && "Validating..."}
          {phase === "idle" && "Upload & Validate"}
        </button>
      </form>
    </div>
  );
}
