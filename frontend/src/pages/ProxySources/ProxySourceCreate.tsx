import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { proxySourceApi } from '../../api/client';

export default function ProxySourceCreate() {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const [validationUrls, setValidationUrls] = useState('https://httpbin.org/ip');
  const [extractionSpec, setExtractionSpec] = useState('');
  const [sourceHeaders, setSourceHeaders] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

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
      }

      if (sourceHeaders.trim()) {
        try {
          data.source_headers = JSON.parse(sourceHeaders);
        } catch {
          setError('Source headers must be valid JSON');
          setSaving(false);
          return;
        }
      }

      const result = await proxySourceApi.create(data as any);
      navigate(`/proxy-sources/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create proxy source');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">New Proxy Source</h1>
          <p className="page-subtitle">Configure a proxy list source</p>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 720 }}>
        <form onSubmit={handleSubmit}>
          {error && (
            <div style={{ color: 'var(--status-failed)', marginBottom: 16, fontSize: '0.85rem' }}>
              {error}
            </div>
          )}

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
              />
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
              id="require_all"
            />
            <label htmlFor="require_all" style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Require all validation URLs to succeed
            </label>
          </div>

          <div className="form-group" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              id="is_active"
            />
            <label htmlFor="is_active" style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Active
            </label>
          </div>

          <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Creating...' : 'Create Source'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate('/proxy-sources')}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}