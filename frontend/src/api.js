// frontend/src/api.js

const API_BASE = "http://localhost:8000";

export async function login(secretKey) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // IMPORTANT for cookies
    body: JSON.stringify({ secretKey }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail || "Login failed");
  }
  return res.json();
}

export async function logout() {
  const res = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail || "Logout failed");
  }
  return res.json();
}

export async function me() {
  const res = await fetch(`${API_BASE}/auth/me`, {
    method: "GET",
    credentials: "include",
  });
  if (!res.ok) return { authed: false };
  return res.json();
}

export async function uploadVideo(file, folder, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/uploads`);
    xhr.withCredentials = true; // IMPORTANT for cookies

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error(data?.detail || "Upload failed"));
      } catch {
        reject(new Error("Failed to parse server response"));
      }
    };

    xhr.onerror = () => reject(new Error("Network error"));

    // -------- Upload progress + speed (bytes/sec) --------
    if (xhr.upload && onProgress) {
      let lastTime = performance.now();
      let lastLoaded = 0;

      // Exponential moving average for smoother speed
      let smoothedBps = 0;
      const alpha = 0.2;

      xhr.upload.onprogress = (evt) => {
        const total =
          evt.total && evt.total > 0
            ? evt.total
            : file?.size || 0;

        const loaded = evt.loaded || 0;

        const percent =
          total > 0
            ? Math.min(100, Math.round((loaded / total) * 100))
            : 0;

        const now = performance.now();
        const dt = (now - lastTime) / 1000;
        const dBytes = loaded - lastLoaded;

        if (dt >= 0.15 && dBytes >= 0) {
          const instBps = dBytes / dt;
          smoothedBps =
            smoothedBps === 0
              ? instBps
              : alpha * instBps + (1 - alpha) * smoothedBps;

          lastTime = now;
          lastLoaded = loaded;
        }

        onProgress({ percent, bps: smoothedBps });
      };
    }
    // ----------------------------------------------------

    const form = new FormData();
    form.append("file", file);
    form.append("folder", folder || "");

    xhr.send(form);
  });
}

export async function getStatus(uploadId) {
  const res = await fetch(`${API_BASE}/status/${encodeURIComponent(uploadId)}`, {
    credentials: "include",
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail || "Failed to fetch status");
  }
  return res.json();
}

export async function createFolder(parent, name) {
  const res = await fetch(`${API_BASE}/folders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ parent, name }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail || "Failed to create folder");
  }
  return res.json();
}
