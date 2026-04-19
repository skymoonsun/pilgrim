import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { proxyApi, proxySourceApi } from '../../api/client';
import type { ValidProxy, ProxySourceConfig, ManualProxyCreateResult } from '../../api/client';
import { IconShield, IconTrash, IconPlus } from '../../components/icons/Icons';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';

export default function Proxies() {
  const [healthFilter, setHealthFilter] = useState('');
  const [protocolFilter, setProtocolFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [sources, setSources] = useState<ProxySourceConfig[]>([]);

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  // Add modal state
  const [showAdd, setShowAdd] = useState(false);
  const [addMode, setAddMode] = useState<'single' | 'bulk'>('single');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [addResult, setAddResult] = useState<ManualProxyCreateResult | null>(null);

  // Single form
  const [singleForm, setSingleForm] = useState({
    ip: '',
    port: '',
    protocol: 'http',
    username: '',
    password: '',
  });

  // Bulk form
  const [bulkText, setBulkText] = useState('');
  const [bulkProtocol, setBulkProtocol] = useState('http');

  // Infinite scroll
  const { items: proxies, total, loading, loadingMore, sentinelRef, reset } = useInfiniteScroll<ValidProxy>({
    fetchPage: (skip, limit) =>
      proxyApi.list({
        health: healthFilter || undefined,
        protocol: protocolFilter || undefined,
        ...(sourceFilter === 'manual' ? { manual_only: true } : sourceFilter ? { source_id: sourceFilter } : {}),
        skip,
        limit,
      } as any),
    pageSize: 50,
    deps: [healthFilter, protocolFilter, sourceFilter],
  });

  // Clear selection when filters change or list reloads
  useEffect(() => {
    setSelectedIds(new Set());
  }, [healthFilter, protocolFilter, sourceFilter]);

  // Load sources for filter dropdown
  useEffect(() => {
    proxySourceApi.list(0, 200).then((res) => setSources(res.items)).catch(() => {});
  }, []);

  const allVisibleSelected = proxies.length > 0 && proxies.every((p) => selectedIds.has(p.id));

  function toggleProxy(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllVisible() {
    if (allVisibleSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(proxies.map((p) => p.id)));
    }
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this proxy?')) return;
    try {
      await proxyApi.delete(id);
      setSelectedIds((prev) => { const n = new Set(prev); n.delete(id); return n; });
      reset();
    } catch (err) {
      alert(`Failed to delete: ${err instanceof Error ? err.message : err}`);
    }
  }

  async function handleBulkDelete() {
    if (selectedIds.size === 0) return;
    if (!confirm(`Delete ${selectedIds.size} selected proxy${selectedIds.size !== 1 ? 'ies' : 'y'}?`)) return;
    setDeleting(true);
    try {
      const res = await proxyApi.bulkDelete(Array.from(selectedIds));
      setSelectedIds(new Set());
      reset();
      alert(`Deleted ${res.deleted} proxies`);
    } catch (err) {
      alert(`Failed: ${err instanceof Error ? err.message : err}`);
    }
    setDeleting(false);
  }

  async function handleDeleteAll() {
    const filterDesc = getActiveFilterDescription();
    const msg = filterDesc
      ? `Delete ALL proxies matching: ${filterDesc}?`
      : 'Delete ALL proxies? This cannot be undone.';
    if (!confirm(msg)) return;
    setDeleting(true);
    try {
      const res = await proxyApi.deleteAll({
        source_id: sourceFilter && sourceFilter !== 'manual' ? sourceFilter : undefined,
        manual_only: sourceFilter === 'manual' ? true : undefined,
        protocol: protocolFilter || undefined,
        health: healthFilter || undefined,
      });
      setSelectedIds(new Set());
      reset();
      alert(`Deleted ${res.deleted} proxies`);
    } catch (err) {
      alert(`Failed: ${err instanceof Error ? err.message : err}`);
    }
    setDeleting(false);
  }

  function getActiveFilterDescription(): string {
    const parts: string[] = [];
    if (sourceFilter === 'manual') parts.push('Manual');
    else if (sourceFilter) {
      const src = sources.find((s) => s.id === sourceFilter);
      parts.push(src ? src.name : sourceFilter);
    }
    if (protocolFilter) parts.push(protocolFilter.toUpperCase());
    if (healthFilter) parts.push(healthFilter);
    return parts.join(', ');
  }

  function resetAddForm() {
    setSingleForm({ ip: '', port: '', protocol: 'http', username: '', password: '' });
    setBulkText('');
    setBulkProtocol('http');
    setAddError(null);
    setAddResult(null);
    setAddMode('single');
  }

  function openAddModal() {
    resetAddForm();
    setShowAdd(true);
  }

  async function handleAddSingle(e: React.FormEvent) {
    e.preventDefault();
    setAddError(null);
    setAddResult(null);
    setAdding(true);
    try {
      const result = await proxyApi.create({
        ip: singleForm.ip,
        port: parseInt(singleForm.port, 10),
        protocol: singleForm.protocol,
        username: singleForm.username || null,
        password: singleForm.password || null,
      });
      setAddResult(result);
      reset();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add proxy');
    }
    setAdding(false);
  }

  async function handleAddBulk(e: React.FormEvent) {
    e.preventDefault();
    setAddError(null);
    setAddResult(null);
    setAdding(true);
    try {
      const result = await proxyApi.createBulk({
        raw_text: bulkText,
        default_protocol: bulkProtocol,
      });
      setAddResult(result);
      reset();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add proxies');
    }
    setAdding(false);
  }

  if (loading && proxies.length === 0) {
    return (
      <div className="loading-overlay">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Valid Proxies</h1>
          <p className="page-subtitle">{total} prox{total !== 1 ? 'ies' : 'y'} total</p>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <select
            className="form-input form-select"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            style={{ width: 160 }}
          >
            <option value="">All sources</option>
            <option value="manual">Manual</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <select
            className="form-input form-select"
            value={healthFilter}
            onChange={(e) => setHealthFilter(e.target.value)}
            style={{ width: 140 }}
          >
            <option value="">All health</option>
            <option value="healthy">Healthy</option>
            <option value="degraded">Degraded</option>
            <option value="unhealthy">Unhealthy</option>
          </select>
          <select
            className="form-input form-select"
            value={protocolFilter}
            onChange={(e) => setProtocolFilter(e.target.value)}
            style={{ width: 120 }}
          >
            <option value="">All protocols</option>
            <option value="http">HTTP</option>
            <option value="https">HTTPS</option>
            <option value="socks4">SOCKS4</option>
            <option value="socks5">SOCKS5</option>
          </select>
          <button className="btn btn-primary" onClick={openAddModal}>
            <IconPlus size={16} /> Add Proxy
          </button>
        </div>
      </div>

      {/* Selection action bar */}
      {selectedIds.size > 0 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 20px',
          marginBottom: 16,
          background: 'rgba(0,240,255,0.06)',
          border: '1px solid rgba(0,240,255,0.2)',
          borderRadius: 'var(--radius-md)',
        }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>
            {selectedIds.size} selected
          </span>
          <button
            className="btn btn-secondary"
            onClick={handleBulkDelete}
            disabled={deleting}
            style={{ borderColor: 'var(--status-failed)', color: 'var(--status-failed)' }}
          >
            <IconTrash size={14} /> Delete Selected
          </button>
          <button
            className="btn btn-secondary"
            onClick={clearSelection}
          >
            Clear
          </button>
        </div>
      )}

      <div className="card table-card">
        <table>
          <thead>
            <tr>
              <th style={{ width: 40 }}>
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={toggleAllVisible}
                  style={{ accentColor: 'var(--accent-cyan)', cursor: 'pointer' }}
                />
              </th>
              <th>IP</th>
              <th>Port</th>
              <th>Protocol</th>
              <th>Source</th>
              <th>Health</th>
              <th>Avg Response</th>
              <th>Success / Fail</th>
              <th>Last Checked</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {proxies.length === 0 ? (
              <tr>
                <td colSpan={10}>
                  <div className="empty-state">
                    <div className="empty-state-icon"><IconShield size={48} /></div>
                    <div className="empty-state-text">No proxies found</div>
                    <div className="empty-state-sub">
                      Add a proxy source and fetch proxies, or add manual proxies
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              <>
                {proxies.map((proxy) => (
                  <tr key={proxy.id} style={{
                    background: selectedIds.has(proxy.id) ? 'rgba(0,240,255,0.06)' : undefined,
                  }}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(proxy.id)}
                        onChange={() => toggleProxy(proxy.id)}
                        style={{ accentColor: 'var(--accent-cyan)', cursor: 'pointer' }}
                      />
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>{proxy.ip}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{proxy.port}</td>
                    <td><span className="badge badge--queued">{proxy.protocol}</span></td>
                    <td>
                      {proxy.source_config_id ? (
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          {proxy.source_name || 'Source'}
                        </span>
                      ) : (
                        <span className="badge" style={{
                          background: 'rgba(0,240,255,0.1)',
                          color: 'var(--accent-cyan)',
                          border: '1px solid rgba(0,240,255,0.3)',
                          fontSize: '0.7rem',
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-sm)',
                        }}>
                          Manual
                        </span>
                      )}
                    </td>
                    <td>
                      <span className={`badge badge--${
                        proxy.health === 'healthy' ? 'success' :
                        proxy.health === 'degraded' ? 'running' : 'failed'
                      }`}>
                        {proxy.health}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      {proxy.avg_response_ms != null ? `${Math.round(proxy.avg_response_ms)}ms` : '—'}
                    </td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      <span style={{ color: 'var(--status-success)' }}>{proxy.success_count}</span>
                      {' / '}
                      <span style={{ color: 'var(--status-failed)' }}>{proxy.failure_count}</span>
                    </td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      {proxy.last_checked_at ? new Date(proxy.last_checked_at).toLocaleString() : '—'}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="action-btn action-btn--delete"
                        title="Delete"
                        onClick={() => handleDelete(proxy.id)}
                      >
                        <IconTrash size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
                {/* Sentinel element for infinite scroll */}
                <tr ref={sentinelRef as any}>
                  <td colSpan={10} style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {loadingMore && <div className="spinner" style={{ margin: '0 auto' }} />}
                    {!loadingMore && proxies.length < total && (
                      <span style={{ color: 'var(--text-muted)' }}>Scroll to load more...</span>
                    )}
                    {!loadingMore && proxies.length >= total && total > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
                        <span>All proxies loaded</span>
                        <button
                          className="btn btn-secondary"
                          onClick={handleDeleteAll}
                          disabled={deleting}
                          style={{ fontSize: '0.8rem', borderColor: 'var(--status-failed)', color: 'var(--status-failed)', padding: '4px 12px' }}
                        >
                          <IconTrash size={13} /> Delete All{getActiveFilterDescription() ? ` (${getActiveFilterDescription()})` : ''}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>

      {/* Add Proxy Modal */}
      {showAdd && createPortal(
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
        }} onClick={(e) => { if (e.target === e.currentTarget) setShowAdd(false); }}>
          <div style={{
            width: 520,
            maxHeight: '90vh',
            overflow: 'auto',
            background: '#1e2836',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 'var(--radius-lg)',
            padding: '20px 24px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>Add Proxy</h2>
              <button type="button" className="action-btn" onClick={() => setShowAdd(false)} style={{ fontSize: '1.2rem', color: 'var(--text-muted)' }}>✕</button>
            </div>

            {/* Mode toggle */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
              <button
                type="button"
                className={`btn ${addMode === 'single' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => { setAddMode('single'); setAddResult(null); setAddError(null); }}
                style={{ flex: 1, justifyContent: 'center' }}
              >
                Single
              </button>
              <button
                type="button"
                className={`btn ${addMode === 'bulk' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => { setAddMode('bulk'); setAddResult(null); setAddError(null); }}
                style={{ flex: 1, justifyContent: 'center' }}
              >
                Bulk Add
              </button>
            </div>

            {addError && (
              <div style={{
                background: 'var(--status-failed-bg)',
                border: '1px solid rgba(255,82,82,0.3)',
                borderRadius: 'var(--radius-md)',
                padding: '10px 14px',
                color: 'var(--status-failed)',
                fontSize: '0.85rem',
                marginBottom: 16,
              }}>
                {addError}
              </div>
            )}

            {addResult && (
              <div style={{
                background: 'rgba(76,175,80,0.1)',
                border: '1px solid rgba(76,175,80,0.3)',
                borderRadius: 'var(--radius-md)',
                padding: '10px 14px',
                color: 'var(--status-success)',
                fontSize: '0.85rem',
                marginBottom: 16,
              }}>
                Created {addResult.created} proxy{addResult.created !== 1 ? 'ies' : 'y'}
                {addResult.skipped > 0 && `, ${addResult.skipped} already existed (updated)`}
              </div>
            )}

            {addMode === 'single' ? (
              <form onSubmit={handleAddSingle}>
                <div className="form-group">
                  <label className="form-label">IP Address *</label>
                  <input
                    className="form-input"
                    value={singleForm.ip}
                    onChange={(e) => setSingleForm({ ...singleForm, ip: e.target.value })}
                    placeholder="1.2.3.4"
                    required
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Port *</label>
                    <input
                      className="form-input"
                      type="number"
                      value={singleForm.port}
                      onChange={(e) => setSingleForm({ ...singleForm, port: e.target.value })}
                      placeholder="8080"
                      min={1}
                      max={65535}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Protocol</label>
                    <select
                      className="form-input form-select"
                      value={singleForm.protocol}
                      onChange={(e) => setSingleForm({ ...singleForm, protocol: e.target.value })}
                    >
                      <option value="http">HTTP</option>
                      <option value="https">HTTPS</option>
                      <option value="socks4">SOCKS4</option>
                      <option value="socks5">SOCKS5</option>
                    </select>
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Username</label>
                    <input
                      className="form-input"
                      value={singleForm.username}
                      onChange={(e) => setSingleForm({ ...singleForm, username: e.target.value })}
                      placeholder="Optional"
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Password</label>
                    <input
                      className="form-input"
                      type="password"
                      value={singleForm.password}
                      onChange={(e) => setSingleForm({ ...singleForm, password: e.target.value })}
                      placeholder="Optional"
                    />
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
                  <button type="submit" className="btn btn-primary" disabled={adding} style={{ flex: 1, justifyContent: 'center' }}>
                    {adding ? 'Adding...' : 'Add Proxy'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleAddBulk}>
                <div className="form-group">
                  <label className="form-label">Proxy List *</label>
                  <textarea
                    className="form-input"
                    value={bulkText}
                    onChange={(e) => setBulkText(e.target.value)}
                    placeholder={'1.2.3.4:8080\nsocks5://user:pass@5.6.7.8:1080\nhttps://9.10.11.12:3128'}
                    rows={8}
                    style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Default Protocol</label>
                  <select
                    className="form-input form-select"
                    value={bulkProtocol}
                    onChange={(e) => setBulkProtocol(e.target.value)}
                  >
                    <option value="http">HTTP</option>
                    <option value="https">HTTPS</option>
                    <option value="socks4">SOCKS4</option>
                    <option value="socks5">SOCKS5</option>
                  </select>
                </div>
                <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
                  <button type="submit" className="btn btn-primary" disabled={adding} style={{ flex: 1, justifyContent: 'center' }}>
                    {adding ? 'Adding...' : 'Add Proxies'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
                </div>
              </form>
            )}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}