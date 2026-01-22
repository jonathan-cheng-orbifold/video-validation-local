import { Link, NavLink } from "react-router-dom";

export default function Layout({ children }) {
  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <Link className="brand" to="/">Ego/Exo Video Validation</Link>
          <nav className="nav">
            <NavLink to="/task" className={({isActive}) => isActive ? "navlink active" : "navlink"}>Task</NavLink>
            <NavLink to="/upload" className={({isActive}) => isActive ? "navlink active" : "navlink"}>Upload</NavLink>
          </nav>
        </div>
      </header>

      <main className="main">
        <div className="container">{children}</div>
      </main>

      <footer className="footer">
        <div className="container footer-inner">
          <span>Local MVP • Backend: :8000 • Frontend: :8080</span>
        </div>
      </footer>
    </div>
  );
}
