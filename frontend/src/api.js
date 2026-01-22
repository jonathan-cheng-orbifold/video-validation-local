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

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable) {
          onProgress(Math.round((evt.loaded / evt.total) * 100));
        }
      };
    }

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
