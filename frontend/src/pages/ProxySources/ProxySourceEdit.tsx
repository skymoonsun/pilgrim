import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { proxySourceApi, aiApi } from '../../api/client';
import type { ProxySourceSuggestionResponse, ProxySourceVerifyResult } from '../../api/client';
import { IconGlobe, IconSparkle } from '../../components/icons/Icons';

export default function ProxySourceEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [form, setForm] = useState({
    name: '',
    description: '',
    url: '',
    format_type: 'raw_text',
    require_all_urls: true,
    validation_timeout: 10,
    fetch_interval_seconds: 3600,
    proxy_ttl_seconds: 86400,
    is_active: true,
  });

  const [validationUrls, setValidationUrls] = useState('');
  const [extractionSpec, setExtractionSpec] = useState('');
  const [sourceHeaders, setSourceHeaders] = useState('');

  // AI state
  const [aiAvailable, setAiAvailable] = useState(false);
  const [aiExpanded, setAiExpanded] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');
  const [aiResult, setAiResult] = useState<ProxySourceSuggestionResponse | null>(null);

  // Verify state
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyResult, setVerifyResult] = useState<ProxySourceVerifyResult | null>(null);
  const [verifyError, setVerifyError] = useState('');

  useEffect(() => {
    aiApi.status().then((res) => {
      setAiAvailable(res.enabled && res.reachable);
    }).catch(() => setAiAvailable(false));
  }, []);

  useEffect(() => {
    if (id) loadSource(id);
  }, [id]);

  async function loadSource(sourceId: string) {
    setLoading(true);
    try {
      const source = await proxySourceApi.get(sourceId);
      setForm({
        name: source.name,
        description: source.description || '',
        url: source.url,
        format_type: source.format_type,
        require_all_urls: source.require_all_urls,
        validation_timeout: source.validation_timeout,
        fetch_interval_seconds: source.fetch_interval_seconds,
        proxy_ttl_seconds: source.proxy_ttl_seconds,
        is_active: source.is_active,
      });
      const urls = (source.validation_urls as any)?.urls || [];
      setValidationUrls(urls.join('\n'));
      setExtractionSpec(source.extraction_spec ? JSON.stringify(source.extraction_spec, null, 2) : '');
      setSourceHeaders(source.source_headers ? JSON.stringify(source.source_headers, null, 2) : '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Proxy source not found');
    }
    setLoading(false);
  }

  async function handleAiSuggest(e: React.FormEvent) {
    e.preventDefault();
    if (!form.url.trim()) {
      setAiError('Enter a source URL first');
      return;
    }
    setAiError('');
    setAiLoading(true);
    setAiResult(null);
    setVerifyResult(null);
    setVerifyError('');

    try {
      const res = await aiApi.suggestProxySource({ url: form.url });
      setAiResult(res);
      // Auto-fill form fields
      setForm((prev) => ({
        ...prev,
        format_type: res.format_type,
        name: prev.name || res.suggested_name,
        description: prev.description || res.description,
      }));
      if (res.extraction_spec) {
        setExtractionSpec(JSON.stringify(res.extraction_spec, null, 2));
      }
    } catch (err) {
      setAiError(err instanceof Error ? err.message : 'AI analysis failed');
    }
    setAiLoading(false);
  }

  async function handleVerify() {
    setVerifyError('');
    setVerifyLoading(true);
    setVerifyResult(null);

    try {
      let extraction_spec: Record<string, unknown> | null = null;
      if (extractionSpec.trim()) {
        try {
          extraction_spec = JSON.parse(extractionSpec);
        } catch {
          setVerifyError('Extraction spec must be valid JSON');
          setVerifyLoading(false);
          return;
        }
      }

      if (!form.url.trim()) {
        setVerifyError('Enter a source URL first');
        setVerifyLoading(false);
        return;
      }

      const res = await aiApi.verifyProxySource({
        url: form.url,
        format_type: form.format_type,
        extraction_spec,
      });
      setVerifyResult(res);
    } catch (err) {
      setVerifyError(err instanceof Error ? err.message : 'Verification failed');
    }
    setVerifyLoading(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!id) return;
    setError('');
    setSaving(true);

    try {
      const data: Record<string, unknown> = {
        name: form.name,
        description: form.description || null,
        url: form.url,
        format_type: form.format_type,
        require_all_urls: form.require_all_urls,
        validation_timeout: form.validation_timeout,
        fetch_interval_seconds: form.fetch_interval_seconds,
        proxy_ttl_seconds: form.proxy_ttl_seconds,
        is_active: form.is_active,
      };

      data.validation_urls = { urls: validationUrls.split('\n').map((u) => u.trim()).filter(Boolean) };

      if (extractionSpec.trim()) {
        try {
          data.extraction_spec = JSON.parse(extractionSpec);
        } catch {
          setError('Extraction spec must be valid JSON');
          setSaving(false);
          return;
        }
      } else {
        data.extraction_spec = null;
      }

      if (sourceHeaders.trim()) {
        try {
          data.source_headers = JSON.parse(sourceHeaders);
        } catch {
          setError('Source headers must be valid JSON');
          setSaving(false);
          return;
        }
      } else {
        data.source_headers = null;
      }

      await proxySourceApi.update(id, data as any);
      navigate('/proxy-sources/' + id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update proxy source');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="loading-overlay"><div className="spinner" /></div>;
  }

  if (error && !form.name) {
    return (
      <div className="animate-in">
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <div className="empty-state-icon"><IconGlobe size={48} /></div>
          <div className="empty-state-text">{error}</div>
          <Link to="/proxy-sources" className="btn btn-secondary" style={{ marginTop: 16 }}>Back</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Edit: {form.name}</h1>
          <p className="page-subtitle">Modify proxy source configuration</p>
        </div>
      </div>

      {error && (
        <div style={{
          background: 'var(--status-failed-bg)',
          border: '1px solid rgba(255,82,82,0.3)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 18px',
          color: 'var(--status-failed)',
          fontSize: '0.85rem',
          marginBottom: 20,
        }}>
          {error}
        </div>
      )}

      {/* AI Analysis Panel */}
      {aiAvailable && (
        <div className="card" style={{ marginBottom: 24, padding: 20 }}>
          <div
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
            onClick={() => setAiExpanded(!aiExpanded)}
          >
            <IconSparkle size={18} style={{ color: 'var(--accent-cyan)' }} />
            <span style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              AI Analysis
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
              {aiExpanded ? 'Hide' : 'Show'}
            </span>
          </div>

          {aiExpanded && (
            <form onSubmit={handleAiSuggest} style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
                <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                  <label className="form-label">Source URL to analyze</label>
                  <input
                    className="form-input"
                    value={form.url}
                    onChange={(e) => setForm({ ...form, url: e.target.value })}
                    placeholder="https://example.com/proxies.txt"
                  />
                </div>
                <button type="submit" className="btn btn-primary" disabled={aiLoading} style={{ whiteSpace: 'nowrap' }}>
                  <IconSparkle size={16} /> {aiLoading ? 'Analyzing...' : 'Analyze'}
                </button>
              </div>

              {aiError && (
                <div style={{ color: 'var(--status-failed)', fontSize: '0.85rem', marginTop: 8 }}>
                  {aiError}
                </div>
              )}

              {aiResult && (
                <div style={{
                  marginTop: 16,
                  padding: 16,
                  background: 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-md)',
                }}>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 8 }}>
                    Detected: <span className="badge badge--queued">{aiResult.format_type}</span>
                    {' '}via <span style={{ fontFamily: 'var(--font-mono)' }}>{aiResult.model_used}</span>
                    {' '}({aiResult.content_length} chars)
                  </div>

                  {aiResult.sample_proxies.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                        Sample proxies:
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {aiResult.sample_proxies.map((p, i) => (
                          <span key={i} style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.8rem',
                            padding: '4px 8px',
                            background: 'var(--bg-primary)',
                            borderRadius: 'var(--radius-sm)',
                            color: 'var(--accent-cyan)',
                          }}>
                            {p.protocol}://{p.ip}:{p.port}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </form>
          )}
        </div>
      )}

      <div className="card" style={{ maxWidth: 720 }}>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Name *</label>
            <input
              className="form-input"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g., Free Proxy List"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Description</label>
            <input
              className="form-input"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Optional description"
            />
          </div>

          <div className="form-group">
            <label className="form-label">Source URL *</label>
            <input
              className="form-input"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              placeholder="https://example.com/proxies.txt"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Format</label>
            <select
              className="form-input form-select"
              value={form.format_type}
              onChange={(e) => setForm({ ...form, format_type: e.target.value })}
            >
              <option value="raw_text">Raw Text (ip:port)</option>
              <option value="json">JSON</option>
              <option value="csv">CSV</option>
              <option value="xml">XML</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Validation URLs (one per line)</label>
            <textarea
              className="form-input"
              value={validationUrls}
              onChange={(e) => setValidationUrls(e.target.value)}
              placeholder="https://httpbin.org/ip"
              rows={3}
            />
          </div>

          {form.format_type !== 'raw_text' && (
            <div className="form-group">
              <label className="form-label">Extraction Spec (JSON)</label>
              <textarea
                className="form-input"
                value={extractionSpec}
                onChange={(e) => setExtractionSpec(e.target.value)}
                placeholder='{"list_path": "data", "fields": {"ip": "ip_address", "port": "port"}}'
                rows={4}
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}
              />
            </div>
          )}

          {/* Verify Proxy Parsing section */}
          {form.url.trim() && (
            <div style={{ marginTop: 16, borderTop: '1px solid var(--border-color)', paddingTop: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>Verify Parsing</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>— test if the config extracts proxies</span>
              </div>

              <button
                type="button"
                className="btn btn-ghost"
                onClick={handleVerify}
                disabled={verifyLoading}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: '0.8rem',
                  width: '100%',
                  justifyContent: 'center',
                }}
              >
                {verifyLoading ? (
                  <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Verifying...</>
                ) : (
                  'Verify Parsing'
                )}
              </button>

              {verifyError && (
                <div style={{ marginTop: 10, color: 'var(--status-failed)', fontSize: '0.8rem' }}>
                  {verifyError}
                </div>
              )}

              {verifyResult && (
                <div style={{
                  marginTop: 12,
                  background: 'var(--bg-tertiary)',
                  borderRadius: 'var(--radius-md)',
                  padding: 16,
                  border: `1px solid ${verifyResult.success ? 'rgba(76,175,80,0.3)' : 'rgba(255,82,82,0.3)'}`,
                }}>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 10 }}>
                    {verifyResult.success ? (
                      <span style={{ color: 'var(--status-success)' }}>
                        Successfully parsed {verifyResult.total_parsed} prox{verifyResult.total_parsed !== 1 ? 'ies' : 'y'}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--status-failed)' }}>Parsing failed</span>
                    )}
                  </div>

                  {verifyResult.error && (
                    <div style={{
                      marginBottom: 10,
                      padding: '8px 12px',
                      background: 'rgba(255,82,82,0.1)',
                      border: '1px solid rgba(255,82,82,0.3)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.75rem',
                      color: 'var(--status-failed)',
                    }}>
                      {verifyResult.error}
                    </div>
                  )}

                  {verifyResult.sample_proxies.length > 0 && (
                    <div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 6 }}>
                        Sample proxies ({verifyResult.total_parsed} total, showing first {verifyResult.sample_proxies.length}):
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {verifyResult.sample_proxies.map((p, i) => (
                          <span key={i} style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.8rem',
                            padding: '4px 8px',
                            background: 'var(--bg-primary)',
                            borderRadius: 'var(--radius-sm)',
                            color: verifyResult.success ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                          }}>
                            {p.protocol}://{p.ip}:{p.port}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div style={{ marginTop: 8, fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    Fetched {verifyResult.content_length} chars as {verifyResult.format_type}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Source Headers (JSON, optional)</label>
            <textarea
              className="form-input"
              value={sourceHeaders}
              onChange={(e) => setSourceHeaders(e.target.value)}
              placeholder='{"Authorization": "Bearer ..."}'
              rows={2}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
            <div className="form-group">
              <label className="form-label">Validation Timeout (s)</label>
              <input
                className="form-input"
                type="number"
                value={form.validation_timeout}
                onChange={(e) => setForm({ ...form, validation_timeout: Number(e.target.value) })}
                min={1}
                max={120}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Fetch Interval (s)</label>
              <input
                className="form-input"
                type="number"
                value={form.fetch_interval_seconds}
                onChange={(e) => setForm({ ...form, fetch_interval_seconds: Number(e.target.value) })}
                min={60}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Proxy TTL (s)</label>
              <input
                className="form-input"
                type="number"
                value={form.proxy_ttl_seconds}
                onChange={(e) => setForm({ ...form, proxy_ttl_seconds: Number(e.target.value) })}
                min={60}
              />
            </div>
          </div>

          <div className="form-group" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={form.require_all_urls}
              onChange={(e) => setForm({ ...form, require_all_urls: e.target.checked })}
              id="edit_require_all"
            />
            <label htmlFor="edit_require_all" style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Require all validation URLs to succeed
            </label>
          </div>

          <div className="form-group" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              id="edit_is_active"
            />
            <label htmlFor="edit_is_active" style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Active
            </label>
          </div>

          <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate('/proxy-sources/' + id)}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}