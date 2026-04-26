import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { configsApi, sanitizerConfigsApi } from '../../api/client';
import type { CrawlConfig, SanitizerConfig } from '../../api/client';
import { IconConfig } from '../../components/icons/Icons';

const PROFILES = ['fetcher', 'http_session', 'stealth', 'dynamic', 'spider'];

export default function ConfigEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [form, setForm] = useState({
    name: '',
    description: '',
    scraper_profile: 'fetcher',
    use_proxy: false,
    rotate_user_agent: true,
    custom_delay: '',
    max_concurrent: '',
    sanitizer_config_id: '',
    is_active: true,
    extraction_spec: '',
    fetch_options: '',
    custom_headers: '',
  });

  const [sanitizerConfigs, setSanitizerConfigs] = useState<SanitizerConfig[]>([]);

  useEffect(() => {
    sanitizerConfigsApi.list(0, 200, true).then((res) => {
      setSanitizerConfigs(res.items);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (id) loadConfig(id);
  }, [id]);

  async function loadConfig(configId: string) {
    setLoading(true);
    try {
      const config = await configsApi.get(configId);
      setForm({
        name: config.name,
        description: config.description || '',
        scraper_profile: config.scraper_profile,
        use_proxy: config.use_proxy,
        rotate_user_agent: config.rotate_user_agent,
        custom_delay: config.custom_delay?.toString() || '',
        max_concurrent: config.max_concurrent?.toString() || '',
        sanitizer_config_id: config.sanitizer_config_id || '',
        is_active: config.is_active,
        extraction_spec: config.extraction_spec ? JSON.stringify(config.extraction_spec, null, 2) : '',
        fetch_options: config.fetch_options ? JSON.stringify(config.fetch_options, null, 2) : '',
        custom_headers: config.custom_headers ? JSON.stringify(config.custom_headers, null, 2) : '',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Config not found');
    }
    setLoading(false);
  }

  function updateField(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!id) return;
    setError('');
    setSaving(true);

    try {
      let extraction_spec = {};
      try {
        extraction_spec = JSON.parse(form.extraction_spec || '{}');
      } catch {
        setError('Invalid JSON in Extraction Spec');
        setSaving(false);
        return;
      }

      let fetch_options = null;
      if (form.fetch_options.trim()) {
        try { fetch_options = JSON.parse(form.fetch_options); }
        catch { setError('Invalid JSON in Fetch Options'); setSaving(false); return; }
      }

      let custom_headers = null;
      if (form.custom_headers.trim()) {
        try { custom_headers = JSON.parse(form.custom_headers); }
        catch { setError('Invalid JSON in Custom Headers'); setSaving(false); return; }
      }

      const payload: Partial<CrawlConfig> = {
        name: form.name,
        description: form.description || null,
        scraper_profile: form.scraper_profile,
        use_proxy: form.use_proxy,
        rotate_user_agent: form.rotate_user_agent,
        custom_delay: form.custom_delay ? parseFloat(form.custom_delay) : null,
        max_concurrent: form.max_concurrent ? parseInt(form.max_concurrent) : null,
        sanitizer_config_id: form.sanitizer_config_id || null,
        is_active: form.is_active,
        extraction_spec,
        fetch_options,
        custom_headers,
      };

      await configsApi.update(id, payload);
      navigate(`/configurations/${id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed');
    }
    setSaving(false);
  }

  if (loading) {
    return <div className="loading-overlay"><div className="spinner" /></div>;
  }

  if (error && !form.name) {
    return (
      <div className="animate-in">
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <div className="empty-state-icon"><IconConfig size={48} /></div>
          <div className="empty-state-text">{error}</div>
          <Link to="/configurations" className="btn btn-secondary" style={{ marginTop: 16 }}>← Back</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Edit: {form.name}</h1>
          <p className="page-subtitle">Modify crawl configuration</p>
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

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          {/* Left */}
          <div className="card" style={{ padding: 28 }}>
            <h3 className="card-title" style={{ marginBottom: 20 }}>General</h3>
            <div className="form-group">
              <label className="form-label">Name *</label>
              <input type="text" className="form-input" value={form.name}
                onChange={(e) => updateField('name', e.target.value)} required maxLength={100} />
            </div>
            <div className="form-group">
              <label className="form-label">Description</label>
              <textarea className="form-input" value={form.description}
                onChange={(e) => updateField('description', e.target.value)}
                rows={3} style={{ resize: 'vertical' }} />
            </div>
            <div className="form-group">
              <label className="form-label">Scraper Profile</label>
              <select className="form-input form-select" value={form.scraper_profile}
                onChange={(e) => updateField('scraper_profile', e.target.value)}>
                {PROFILES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Sanitizer Config</label>
              <select className="form-input form-select" value={form.sanitizer_config_id}
                onChange={(e) => updateField('sanitizer_config_id', e.target.value)}>
                <option value="">None</option>
                {sanitizerConfigs.map((sc) => (
                  <option key={sc.id} value={sc.id}>{sc.name} ({sc.rules.length} rules)</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group">
                <label className="form-label">Custom Delay (s)</label>
                <input type="number" className="form-input" value={form.custom_delay}
                  onChange={(e) => updateField('custom_delay', e.target.value)} min="0" step="0.1" />
              </div>
              <div className="form-group">
                <label className="form-label">Max Concurrent</label>
                <input type="number" className="form-input" value={form.max_concurrent}
                  onChange={(e) => updateField('max_concurrent', e.target.value)} min="1" />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 24, marginTop: 8 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input type="checkbox" checked={form.use_proxy} onChange={(e) => updateField('use_proxy', e.target.checked)} />
                Use Proxy
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input type="checkbox" checked={form.rotate_user_agent} onChange={(e) => updateField('rotate_user_agent', e.target.checked)} />
                Rotate UA
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input type="checkbox" checked={form.is_active} onChange={(e) => updateField('is_active', e.target.checked)} />
                Active
              </label>
            </div>
          </div>

          {/* Right */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div className="card" style={{ padding: 28, flex: 1 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>Extraction Spec *</h3>
              <textarea className="form-input" value={form.extraction_spec}
                onChange={(e) => updateField('extraction_spec', e.target.value)}
                rows={8} required
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', resize: 'vertical', whiteSpace: 'pre' }} />
            </div>
            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>Fetch Options (JSON)</h3>
              <textarea className="form-input" value={form.fetch_options}
                onChange={(e) => updateField('fetch_options', e.target.value)}
                rows={4} placeholder='{"timeout": 30}'
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', resize: 'vertical', whiteSpace: 'pre' }} />
            </div>
            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>Custom Headers (JSON)</h3>
              <textarea className="form-input" value={form.custom_headers}
                onChange={(e) => updateField('custom_headers', e.target.value)}
                rows={3} placeholder='{"X-Custom": "value"}'
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', resize: 'vertical', whiteSpace: 'pre' }} />
            </div>
          </div>
        </div>

        <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
          <button type="submit" className="btn btn-primary" disabled={saving || !form.name}
            style={{ minWidth: 160, justifyContent: 'center' }}>
            {saving ? <><div className="spinner" /> Saving...</> : 'Save Changes'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(`/configurations/${id}`)}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
