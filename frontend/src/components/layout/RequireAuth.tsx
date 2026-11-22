import { useEffect, useState } from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { verifyToken } from '../../api/auth';

/** Auth guard — geçerli token yoksa /login'e yönlendirir. */
export default function RequireAuth() {
  const [status, setStatus] = useState<'checking' | 'ok' | 'denied'>('checking');

  useEffect(() => {
    let cancelled = false;
    verifyToken().then((ok: boolean) => {
      if (!cancelled) setStatus(ok ? 'ok' : 'denied');
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === 'checking') {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: '40vh' }}>
        <span>Checking session…</span>
      </div>
    );
  }
  if (status === 'denied') return <Navigate to="/login" replace />;
  return <Outlet />;
}
