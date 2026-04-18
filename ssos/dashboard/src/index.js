import React from 'react';
import ReactDOM from 'react-dom/client';

function DeprecatedDashboard() {
  const box = {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#0b1020',
    color: '#e5eefc',
    fontFamily: 'system-ui, sans-serif',
    padding: '24px',
  };

  const card = {
    maxWidth: '720px',
    background: '#121a2f',
    border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: '16px',
    padding: '28px',
    boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
  };

  const code = {
    display: 'block',
    marginTop: '16px',
    padding: '12px 14px',
    borderRadius: '10px',
    background: '#0a0f1c',
    color: '#7dd3fc',
    fontFamily: 'ui-monospace, monospace',
  };

  return (
    <div style={box}>
      <div style={card}>
        <h1 style={{ marginTop: 0 }}>Legacy Dashboard Prototype</h1>
        <p>
          This React dashboard is no longer the primary SSOS demo surface.
          Use the standalone Mission Control dashboard for judging and operator demos.
        </p>
        <code style={code}>dashboard/public/index.html</code>
        <p style={{ marginBottom: 0 }}>
          The React app remains only as a placeholder so accidental launches do not present stale or partial UI.
        </p>
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<DeprecatedDashboard />);
