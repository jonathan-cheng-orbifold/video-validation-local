import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getStatus } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function Status() {
  const { uploadId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let timer = null;
    let stopped = false;

    async function tick() {
      try {
        const s = await getStatus(uploadId);
        if (stopped) return;
        setData(s);
        setLoading(false);

        // Your current backend always writes metadata before returning from /uploads,
        // so status should be final immediately. This logic supports future async.
        if (s.status !== "good" && s.status !== "bad") {
          timer = setTimeout(tick, 1000);
        }
      } catch (e) {
        if (stopped) return;
        setError(e?.message || "Failed to fetch status");
        setLoading(false);
      }
    }

    tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [uploadId]);

  return (
    <div className="card">
      <h1 className="h1">Validation Status</h1>

      {loading && <p className="muted">Loading...</p>}
      {error && <div className="alert">{error}</div>}

      {data && (
        <div className="stack">
          <div className="row">
            <div>
              <div className="label">Upload ID</div>
              <div className="mono">{data.upload_id}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <StatusBadge status={data.status} />
            </div>
          </div>

          <div className="panel">
            <div className="label">Filename</div>
            <div>{data.filename}</div>

            <div className="spacer" />

            <div className="label">Validated At</div>
            <div className="mono">{data.validated_at || "-"}</div>

            {data.message && (
              <>
                <div className="spacer" />
                <div className="label">Message</div>
                <pre className="pre">{data.message}</pre>
              </>
            )}

            {Array.isArray(data.issues) && data.issues.length > 0 && (
              <>
                <div className="spacer" />
                <div className="label">Issues</div>
                <ul>
                  {data.issues.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
