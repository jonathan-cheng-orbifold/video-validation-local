// frontend/src/App.jsx

import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import Task from "./pages/Task";
import Upload from "./pages/Upload";
import Status from "./pages/Status";
import Login from "./pages/Login";
import { me } from "./api";

function ProtectedRoute({ children }) {
  const [authed, setAuthed] = useState(null); // null=loading, true/false
  const location = useLocation();

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await me();
        if (!mounted) return;
        setAuthed(!!res.authed);
      } catch {
        if (!mounted) return;
        setAuthed(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [location.pathname]);

  if (authed === null) {
    return (
      <div className="card">
        <p className="muted">Checking session...</p>
      </div>
    );
  }

  if (!authed) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/upload" replace />} />
        <Route path="/login" element={<Login />} />

        <Route
          path="/task"
          element={
            <ProtectedRoute>
              <Task />
            </ProtectedRoute>
          }
        />
        <Route
          path="/upload"
          element={
            <ProtectedRoute>
              <Upload />
            </ProtectedRoute>
          }
        />
        <Route
          path="/status/:uploadId"
          element={
            <ProtectedRoute>
              <Status />
            </ProtectedRoute>
          }
        />

        <Route path="*" element={<Navigate to="/upload" replace />} />
      </Routes>
    </Layout>
  );
}
