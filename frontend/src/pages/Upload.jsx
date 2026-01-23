// frontend/src/pages/Upload.jsx

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
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

function joinFolder(a, b) {
  const left = (a || "").replace(/^\/+|\/+$/g, "");
  const right = (b || "").replace(/^\/+|\/+$/g, "");
  if (!left) return right;
  if (!right) return left;
  return `${left}/${right}`;
}

export default function Upload() {
  // Single-file mode (kept for convenience)
  const [file, setFile] = useState(null);

  // Folder mode (FileList -> Array<File>)
  const [folderFiles, setFolderFiles] = useState([]);

  // Optional base folder prefix (prepended in Wasabi)
  const [baseFolder, setBaseFolder] = useState("");

  // UI states
  const [progress, setProgress] = useState(0);
  const [uploadSpeedBps, setUploadSpeedBps] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // multi upload tracking
  const [currentIndex, setCurrentIndex] = useState(0);
  const [results, setResults] = useState([]); // [{ upload_id, filename, folder, status_url }]

  const mode = folderFiles.length > 0 ? "folder" : "single";
  const phase =
    busy && progress >= 100 ? "processing" : busy ? "uploading" : "idle";

  const fileInfo = useMemo(() => {
    if (mode === "folder") {
      const totalBytes = folderFiles.reduce((sum, f) => sum + (f?.size || 0), 0);
      const totalMB = (totalBytes / (1024 * 1024)).toFixed(2);
      return { count: folderFiles.length, totalMB };
    }
    if (!file) return null;
    return {
      name: file.name,
      sizeMB: (file.size / (1024 * 1024)).toFixed(2),
      type: file.type || "unknown",
    };
  }, [file, folderFiles, mode]);

  function handlePickSingleFile(e) {
    const f = e.target.files?.[0] || null;
    setFile(f);
    setFolderFiles([]);
    setResults([]);
    setError("");
  }

  function handlePickFolder(e) {
    const files = Array.from(e.target.files || []);
    // Filter out non-files just in case; keep all files (you can filter to video extensions if desired)
    setFolderFiles(files);
    setFile(null);
    setResults([]);
    setError("");
  }

  function getRelativeDirForFile(f) {
    // When selecting a directory, browsers provide webkitRelativePath, like:
    // "MyFolder/SubA/video.mp4"
    const rel = f.webkitRelativePath || "";
    if (!rel) return "";
    const parts = rel.split("/").filter(Boolean);
    if (parts.length <= 1) return ""; // file at root of selected folder
    return parts.slice(0, -1).join("/");
  }

  async function uploadOne(f) {
    const relDir = getRelativeDirForFile(f);
    const folderForThisFile = joinFolder(baseFolder, relDir);

    setProgress(0);
    setUploadSpeedBps(0);

    const resp = await uploadVideo(f, folderForThisFile, {
      onProgress: ({ percent, bps }) => {
        setProgress(percent);
        setUploadSpeedBps(bps);
      },
    });

    return resp;
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setResults([]);

    if (mode === "single") {
      if (!file) return;
    } else {
      if (!folderFiles.length) return;
    }

    setBusy(true);
    setProgress(0);
    setUploadSpeedBps(0);
    setCurrentIndex(0);

    try {
      if (mode === "single") {
        const resp = await uploadOne(file);
        setResults([
          {
            upload_id: resp.upload_id,
            filename: resp.filename,
            folder: resp.folder || "",
            status_url: resp.status_url,
          },
        ]);
      } else {
        const out = [];
        for (let i = 0; i < folderFiles.length; i++) {
          setCurrentIndex(i);
          const f = folderFiles[i];
          const resp = await uploadOne(f);
          out.push({
            upload_id: resp.upload_id,
            filename: resp.filename,
            folder: resp.folder || "",
            status_url: resp.status_url,
          });
        }
        setResults(out);
      }
    } catch (err) {
      setError(err?.message || "Upload failed");
    } finally {
      setBusy(false);
      setUploadSpeedBps(0);
    }
  }

  const currentFileLabel =
    mode === "folder" && folderFiles.length > 0
      ? `${currentIndex + 1} / ${folderFiles.length}: ${
          folderFiles[currentIndex]?.webkitRelativePath ||
          folderFiles[currentIndex]?.name ||
          ""
        }`
      : file?.name || "";

  return (
    <div className="card">
      <h1 className="h1">Upload Video</h1>
      <p className="muted">
        Upload a single file or select a folder. Folder uploads preserve the
        subfolder structure in Wasabi.
      </p>

      <form onSubmit={onSubmit} className="stack">
        {/* Optional base folder */}
        <div className="field">
          <label className="label">Wasabi Base Folder (optional)</label>
          <input
            type="text"
            placeholder="e.g. task-123/session-001"
            value={baseFolder}
            onChange={(e) => setBaseFolder(e.target.value)}
            disabled={busy}
          />
          <div className="help">
            Files will be uploaded under:{" "}
            <span className="mono">
              uploads/{baseFolder ? baseFolder.replace(/^\/+/, "") : "<root>"}/...
            </span>
          </div>
        </div>

        {/* Single file picker */}
        <div className="field">
          <label className="label">Single Video File</label>
          <input
            type="file"
            onChange={handlePickSingleFile}
            disabled={busy}
          />
          {mode === "single" && fileInfo && (
            <div className="help">
              <span>
                <b>{fileInfo.name}</b>
              </span>
              <span className="dot">•</span>
              <span>{fileInfo.sizeMB} MB</span>
              <span className="dot">•</span>
              <span>{fileInfo.type}</span>
            </div>
          )}
        </div>

        {/* Folder picker */}
        <div className="field">
          <label className="label">Folder Upload (multiple files)</label>
          <input
            type="file"
            multiple
            // directory upload (supported in Chromium-based browsers and Safari)
            webkitdirectory="true"
            directory="true"
            onChange={handlePickFolder}
            disabled={busy}
          />
          {mode === "folder" && fileInfo && (
            <div className="help">
              <span>
                <b>{fileInfo.count}</b> files selected
              </span>
              <span className="dot">•</span>
              <span>Total {fileInfo.totalMB} MB</span>
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
                  width: phase === "processing" ? "100%" : `${progress}%`,
                  opacity: phase === "processing" ? 0.6 : 1,
                }}
              />
            </div>

            <div className="progress-label">
              {mode === "folder" && currentFileLabel ? (
                <div className="mono" style={{ marginBottom: 6 }}>
                  {currentFileLabel}
                </div>
              ) : null}

              {phase === "uploading" && (
                <>Uploading… {progress}% • {formatBytesPerSec(uploadSpeedBps)}</>
              )}
              {phase === "processing" && <>Upload complete — processing…</>}
            </div>
          </div>
        )}

        {/* Error */}
        {error && <div className="alert">{error}</div>}

        <button
          className="btn"
          type="submit"
          disabled={
            busy ||
            (mode === "single" ? !file : folderFiles.length === 0)
          }
        >
          {phase === "uploading" && "Uploading..."}
          {phase === "processing" && "Processing..."}
          {phase === "idle" && (mode === "folder" ? "Upload Folder" : "Upload & Validate")}
        </button>

        {/* Results */}
        {results.length > 0 && (
          <div className="panel">
            <h2 className="h2">Uploaded</h2>
            <ul>
              {results.map((r) => (
                <li key={r.upload_id}>
                  <span className="mono">{r.folder ? `${r.folder}/` : ""}{r.filename}</span>{" "}
                  —{" "}
                  <a
                    href={r.status_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    View status
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </form>
    </div>
  );
}
