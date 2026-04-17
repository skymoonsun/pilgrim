import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { configsApi, aiApi } from '../../api/client';
import { IconPlus, IconSparkle } from '../../components/icons/Icons';

const PROFILES = ['fetcher', 'http_session', 'stealth', 'dynamic', 'spider'];

export default function ConfigCreate() {
  const navigate = useNavigate();
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
    is_active: true,
    extraction_spec: '{\n  "fields": {\n    "title": { "selector": "h1::text", "type": "css" }\n  }\n}',
    fetch_options: '',
    custom_headers: '',
  });

  // AI mode state
  const [aiAvailable, setAiAvailable] = useState(false);
  const [aiChecked, setAiChecked] = useState(false);
  const [aiExpanded, setAiExpanded] = useState(false);
  const [aiUrl, setAiUrl] = useState('');
  const [aiDescription, setAiDescription] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');

  useEffect(() => {
    aiApi.status().then((res) => {
      setAiAvailable(res.enabled && res.reachable);
      setAiChecked(true);
    }).catch(() => {
      // AI status endpoint unreachable — still show button
      // so user knows the feature exists; error shown on generate attempt
      setAiAvailable(false);
      setAiChecked(true);
    });
  }, []);

  function updateField(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAiGenerate(e: React.FormEvent) {
    e.preventDefault();
    setAiError('');
    setAiLoading(true);

    try {
      const res = await aiApi.generateSpec({
        url: aiUrl,
        description: aiDescription,
        scraper_profile: form.scraper_profile,
      });
      setForm((prev) => ({
        ...prev,
        extraction_spec: JSON.stringify(res.extraction_spec, null, 2),
      }));
      setAiError('');
    } catch (err) {
      setAiError(err instanceof Error ? err.message : 'AI generation failed');
    }
    setAiLoading(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
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
        try {
          fetch_options = JSON.parse(form.fetch_options);
        } catch {
          setError('Invalid JSON in Fetch Options');
          setSaving(false);
          return;
        }
      }

      let custom_headers = null;
      if (form.custom_headers.trim()) {
        try {
          custom_headers = JSON.parse(form.custom_headers);
        } catch {
          setError('Invalid JSON in Custom Headers');
          setSaving(false);
          return;
        }
      }

      const payload = {
        name: form.name,
        description: form.description || null,
        scraper_profile: form.scraper_profile,
        use_proxy: form.use_proxy,
        rotate_user_agent: form.rotate_user_agent,
        custom_delay: form.custom_delay ? parseFloat(form.custom_delay) : null,
        max_concurrent: form.max_concurrent ? parseInt(form.max_concurrent) : null,
        is_active: form.is_active,
        extraction_spec,
        fetch_options,
        custom_headers,
      };

      const created = await configsApi.create(payload);
      navigate(`/configurations/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create failed');
    }
    setSaving(false);
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">New Configuration</h1>
          <p className="page-subtitle">Create a new crawl config recipe</p>
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
          {/* Left column */}
          <div className="card" style={{ padding: 28 }}>
            <h3 className="card-title" style={{ marginBottom: 20 }}>General</h3>

            <div className="form-group">
              <label className="form-label">Name *</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. product-scraper"
                value={form.name}
                onChange={(e) => updateField('name', e.target.value)}
                required
                maxLength={100}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Description</label>
              <textarea
                className="form-input"
                placeholder="What does this config do?"
                value={form.description}
                onChange={(e) => updateField('description', e.target.value)}
                rows={3}
                style={{ resize: 'vertical' }}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Scraper Profile</label>
              <select
                className="form-input form-select"
                value={form.scraper_profile}
                onChange={(e) => updateField('scraper_profile', e.target.value)}
              >
                {PROFILES.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group">
                <label className="form-label">Custom Delay (s)</label>
                <input
                  type="number"
                  className="form-input"
                  placeholder="e.g. 1.5"
                  value={form.custom_delay}
                  onChange={(e) => updateField('custom_delay', e.target.value)}
                  min="0"
                  step="0.1"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Max Concurrent</label>
                <input
                  type="number"
                  className="form-input"
                  placeholder="e.g. 5"
                  value={form.max_concurrent}
                  onChange={(e) => updateField('max_concurrent', e.target.value)}
                  min="1"
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 24, marginTop: 8 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={form.use_proxy}
                  onChange={(e) => updateField('use_proxy', e.target.checked)}
                />
                Use Proxy
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={form.rotate_user_agent}
                  onChange={(e) => updateField('rotate_user_agent', e.target.checked)}
                />
                Rotate UA
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => updateField('is_active', e.target.checked)}
                />
                Active
              </label>
            </div>
          </div>

          {/* Right column */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div className="card" style={{ padding: 28, flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                <h3 className="card-title" style={{ marginBottom: 0 }}>Extraction Spec *</h3>
                {!aiChecked ? (
                  <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                ) : aiAvailable ? (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setAiExpanded(!aiExpanded)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      fontSize: '0.8rem',
                      color: aiExpanded ? 'var(--accent-primary)' : 'var(--text-secondary)',
                      border: aiExpanded ? '1px solid var(--accent-primary-dim)' : '1px solid var(--border-color)',
                      background: aiExpanded ? 'var(--accent-primary-dim)' : 'transparent',
                    }}
                  >
                    <IconSparkle size={14} />
                    Generate with AI
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled
                    title="AI service is not available. Check that PILGRIM_AI_ENABLED=true and Ollama is running."
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      fontSize: '0.8rem',
                      color: 'var(--text-muted)',
                      border: '1px solid var(--border-color)',
                      background: 'transparent',
                      opacity: 0.5,
                      cursor: 'not-allowed',
                    }}
                  >
                    <IconSparkle size={14} />
                    AI unavailable
                  </button>
                )}
              </div>

              {aiExpanded && (
                <div style={{
                  background: 'var(--bg-tertiary)',
                  borderRadius: 'var(--radius-md)',
                  padding: 16,
                  marginBottom: 16,
                  border: '1px solid var(--border-color)',
                }}>
                  <div className="form-group" style={{ marginBottom: 12 }}>
                    <label className="form-label" style={{ fontSize: '0.8rem' }}>Target URL</label>
                    <input
                      type="url"
                      className="form-input"
                      placeholder="https://example.com/product/123"
                      value={aiUrl}
                      onChange={(e) => setAiUrl(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group" style={{ marginBottom: 12 }}>
                    <label className="form-label" style={{ fontSize: '0.8rem' }}>What to extract?</label>
                    <textarea
                      className="form-input"
                      placeholder="e.g. Product name, price, stock status, and images"
                      value={aiDescription}
                      onChange={(e) => setAiDescription(e.target.value)}
                      rows={2}
                      style={{ resize: 'vertical' }}
                      required
                    />
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleAiGenerate}
                    disabled={aiLoading || !aiUrl || !aiDescription}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      justifyContent: 'center',
                      width: '100%',
                    }}
                  >
                    {aiLoading ? (
                      <><div className="spinner" /> Generating...</>
                    ) : (
                      <><IconSparkle size={14} /> Generate Spec</>
                    )}
                  </button>
                  {aiError && (
                    <div style={{
                      marginTop: 10,
                      color: 'var(--status-failed)',
                      fontSize: '0.8rem',
                    }}>
                      {aiError}
                    </div>
                  )}
                </div>
              )}

              <textarea
                className="form-input"
                value={form.extraction_spec}
                onChange={(e) => updateField('extraction_spec', e.target.value)}
                rows={8}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  resize: 'vertical',
                  whiteSpace: 'pre',
                }}
                required
              />
            </div>

            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>Fetch Options (JSON)</h3>
              <textarea
                className="form-input"
                value={form.fetch_options}
                onChange={(e) => updateField('fetch_options', e.target.value)}
                rows={4}
                placeholder='{"timeout": 30, "impersonate": "chrome_131"}'
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  resize: 'vertical',
                  whiteSpace: 'pre',
                }}
              />
            </div>

            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>Custom Headers (JSON)</h3>
              <textarea
                className="form-input"
                value={form.custom_headers}
                onChange={(e) => updateField('custom_headers', e.target.value)}
                rows={3}
                placeholder='{"X-Custom": "value"}'
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  resize: 'vertical',
                  whiteSpace: 'pre',
                }}
              />
            </div>
          </div>
        </div>

        <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={saving || !form.name}
            style={{ minWidth: 160, justifyContent: 'center' }}
          >
            {saving ? (
              <><div className="spinner" /> Saving...</>
            ) : (
              <><IconPlus size={16} /> Create Config</>
            )}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate('/configurations')}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}