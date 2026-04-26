import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { configsApi, aiApi, sanitizerConfigsApi } from '../../api/client';
import type { SpecVerificationResponse, SanitizerConfig } from '../../api/client';
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
    sanitizer_config_id: '',
    is_active: true,
    extraction_spec: '{\n  "fields": {\n    "title": { "selector": "h1::text", "type": "css" }\n  }\n}',
    fetch_options: '',
    custom_headers: '',
  });

  const [sanitizerConfigs, setSanitizerConfigs] = useState<SanitizerConfig[]>([]);

  // AI mode state
  const [aiAvailable, setAiAvailable] = useState(false);
  const [aiChecked, setAiChecked] = useState(false);
  const [aiExpanded, setAiExpanded] = useState(false);
  const [aiUrl, setAiUrl] = useState('');
  const [aiDescription, setAiDescription] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');

  // Verification state
  const [verifyUrl, setVerifyUrl] = useState('');
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyResult, setVerifyResult] = useState<SpecVerificationResponse | null>(null);
  const [verifyError, setVerifyError] = useState('');

  // Sanitizer AI state
  const [sanitizerAiLoading, setSanitizerAiLoading] = useState(false);
  const [sanitizerAiError, setSanitizerAiError] = useState('');
  const [sanitizerAiDescription, setSanitizerAiDescription] = useState('');
  const [sanitizerAiResult, setSanitizerAiResult] = useState<{ rules: { field: string; transforms: { type: string; pattern?: string; replacement?: string; value?: string; index?: number }[] }[]; sample_before: Record<string, unknown> | null; sample_after: Record<string, unknown> | null } | null>(null);

  useEffect(() => {
    sanitizerConfigsApi.list(0, 200, true).then((res) => {
      setSanitizerConfigs(res.items);
    }).catch(() => {});
  }, []);

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
      // Pre-fill verification URL from AI generation URL
      if (aiUrl) setVerifyUrl(aiUrl);
      setAiError('');
    } catch (err) {
      setAiError(err instanceof Error ? err.message : 'AI generation failed');
    }
    setAiLoading(false);
  }

  async function handleVerify() {
    setVerifyError('');
    setVerifyLoading(true);
    setVerifyResult(null);

    try {
      let extraction_spec: Record<string, unknown> = {};
      try {
        extraction_spec = JSON.parse(form.extraction_spec || '{}');
      } catch {
        setVerifyError('Invalid JSON in Extraction Spec');
        setVerifyLoading(false);
        return;
      }

      if (!verifyUrl.trim()) {
        setVerifyError('Enter a target URL to verify against');
        setVerifyLoading(false);
        return;
      }

      const res = await aiApi.verifySpec({
        url: verifyUrl,
        extraction_spec,
        scraper_profile: form.scraper_profile,
        max_iterations: 2,
      });
      setVerifyResult(res);

      // If a refined spec was produced, update the form
      if (res.refined_spec) {
        setForm((prev) => ({
          ...prev,
          extraction_spec: JSON.stringify(res.refined_spec, null, 2),
        }));
      }
    } catch (err) {
      setVerifyError(err instanceof Error ? err.message : 'Verification failed');
    }
    setVerifyLoading(false);
  }

  async function handleGenerateSanitizer() {
    setSanitizerAiError('');
    setSanitizerAiLoading(true);
    setSanitizerAiResult(null);

    try {
      let extraction_spec: Record<string, unknown> = {};
      try {
        extraction_spec = JSON.parse(form.extraction_spec || '{}');
      } catch {
        setSanitizerAiError('Invalid JSON in Extraction Spec');
        setSanitizerAiLoading(false);
        return;
      }

      const url = verifyUrl.trim();
      if (!url) {
        setSanitizerAiError('Enter a target URL first (use the Verify section above)');
        setSanitizerAiLoading(false);
        return;
      }

      const res = await aiApi.suggestSanitizer({
        url,
        extraction_spec,
        description: sanitizerAiDescription || undefined,
        scraper_profile: form.scraper_profile,
      });
      setSanitizerAiResult(res);
    } catch (err) {
      setSanitizerAiError(err instanceof Error ? err.message : 'AI sanitizer generation failed');
    }
    setSanitizerAiLoading(false);
  }

  async function handleApplySanitizer() {
    if (!sanitizerAiResult) return;
    try {
      // Create the sanitizer config
      const created = await sanitizerConfigsApi.create({
        name: `Sanitizer for ${form.name || 'config'}`,
        description: `Auto-generated sanitizer`,
        is_active: true,
        rules: sanitizerAiResult.rules,
      });
      // Select it in the form
      setForm((prev) => ({ ...prev, sanitizer_config_id: created.id }));
      // Refresh the sanitizer configs list
      const res = await sanitizerConfigsApi.list(0, 200, true);
      setSanitizerConfigs(res.items);
      setSanitizerAiResult(null);
    } catch (err) {
      setSanitizerAiError(err instanceof Error ? err.message : 'Failed to create sanitizer config');
    }
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
        sanitizer_config_id: form.sanitizer_config_id || null,
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

            <div className="form-group">
              <label className="form-label">Sanitizer Config</label>
              <select
                className="form-input form-select"
                value={form.sanitizer_config_id}
                onChange={(e) => updateField('sanitizer_config_id', e.target.value)}
              >
                <option value="">None</option>
                {sanitizerConfigs.map((sc) => (
                  <option key={sc.id} value={sc.id}>{sc.name} ({sc.rules.length} rules)</option>
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

              {/* Verify Spec section */}
              {form.extraction_spec.trim() && form.extraction_spec.trim() !== '{\n  "fields": {\n    "title": { "selector": "h1::text", "type": "css" }\n  }\n}' && (
                <div style={{ marginTop: 16, borderTop: '1px solid var(--border-color)', paddingTop: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>Verify Spec</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>— test selectors against a real page</span>
                  </div>

                  <div className="form-group" style={{ marginBottom: 12 }}>
                    <label className="form-label" style={{ fontSize: '0.8rem' }}>Target URL</label>
                    <input
                      type="url"
                      className="form-input"
                      placeholder="https://example.com/product/123"
                      value={verifyUrl}
                      onChange={(e) => setVerifyUrl(e.target.value)}
                    />
                  </div>

                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={handleVerify}
                    disabled={verifyLoading || !verifyUrl.trim()}
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
                      'Verify Spec'
                    )}
                  </button>

                  {verifyError && (
                    <div style={{
                      marginTop: 10,
                      color: 'var(--status-failed)',
                      fontSize: '0.8rem',
                    }}>
                      {verifyError}
                    </div>
                  )}

                  {verifyResult && (
                    <div style={{
                      marginTop: 12,
                      background: 'var(--bg-tertiary)',
                      borderRadius: 'var(--radius-md)',
                      padding: 16,
                      border: `1px solid ${verifyResult.valid ? 'rgba(76,175,80,0.3)' : 'rgba(255,82,82,0.3)'}`,
                    }}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 10 }}>
                        {verifyResult.valid ? (
                          <span style={{ color: 'var(--status-success)' }}>All fields matched with clean values</span>
                        ) : (
                          <span style={{ color: 'var(--status-failed)' }}>
                            {verifyResult.passed_fields}/{verifyResult.total_fields} fields passed
                          </span>
                        )}
                      </div>

                      {verifyResult.page_warning && (
                        <div style={{
                          marginBottom: 10,
                          padding: '8px 12px',
                          background: 'rgba(255, 152, 0, 0.1)',
                          border: '1px solid rgba(255, 152, 0, 0.3)',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.75rem',
                          color: '#ff9800',
                        }}>
                          {verifyResult.page_warning}
                        </div>
                      )}

                      {verifyResult.field_results.map((fr) => (
                        <div key={fr.field_name} style={{
                          padding: '8px 0',
                          fontSize: '0.8rem',
                          borderBottom: '1px solid var(--border-color)',
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{
                              color: fr.matched && fr.value_quality === 'good' ? 'var(--status-success)'
                                : fr.matched ? '#ff9800' : 'var(--status-failed)',
                              fontSize: '1rem',
                              width: 16,
                              textAlign: 'center',
                            }}>
                              {fr.value_quality === 'good' ? '\u2713' : fr.value_quality === 'html' ? '\u26A0' : '\u2717'}
                            </span>
                            <span style={{ color: 'var(--text-primary)', fontWeight: 500, minWidth: 100 }}>
                              {fr.field_name}
                            </span>
                            <code style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', flex: 1 }}>
                              {fr.selector}
                            </code>
                            {fr.value_quality === 'html' && (
                              <span style={{
                                fontSize: '0.7rem',
                                padding: '2px 6px',
                                borderRadius: 4,
                                background: 'rgba(255, 152, 0, 0.15)',
                                color: '#ff9800',
                                border: '1px solid rgba(255, 152, 0, 0.3)',
                              }}>
                                HTML
                              </span>
                            )}
                            {fr.value_quality === 'empty' && (
                              <span style={{
                                fontSize: '0.7rem',
                                padding: '2px 6px',
                                borderRadius: 4,
                                background: 'rgba(255,82,82,0.1)',
                                color: 'var(--status-failed)',
                                border: '1px solid rgba(255,82,82,0.3)',
                              }}>
                                EMPTY
                              </span>
                            )}
                          </div>
                          {fr.matched && fr.sample_value && (
                            <div style={{
                              marginLeft: 24,
                              marginTop: 4,
                              padding: '6px 10px',
                              background: fr.value_quality === 'html'
                                ? 'rgba(255, 152, 0, 0.05)'
                                : fr.value_quality === 'good'
                                  ? 'rgba(76, 175, 80, 0.05)'
                                  : 'transparent',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.75rem',
                              fontFamily: 'var(--font-mono)',
                              color: fr.value_quality === 'html' ? '#ff9800' : 'var(--text-muted)',
                              wordBreak: 'break-all',
                              maxHeight: 80,
                              overflow: 'auto',
                            }}>
                              {fr.sample_value}
                            </div>
                          )}
                        </div>
                      ))}

                      {/* Extracted data summary */}
                      {verifyResult.extracted_data && Object.keys(verifyResult.extracted_data).length > 0 && (
                        <details style={{ marginTop: 12 }}>
                          <summary style={{
                            fontSize: '0.75rem',
                            color: 'var(--text-secondary)',
                            cursor: 'pointer',
                            marginBottom: 8,
                          }}>
                            Extracted data
                          </summary>
                          <pre style={{
                            background: 'var(--bg-primary)',
                            padding: 12,
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.7rem',
                            fontFamily: 'var(--font-mono)',
                            overflow: 'auto',
                            maxHeight: 200,
                            color: 'var(--text-secondary)',
                          }}>
                            {JSON.stringify(verifyResult.extracted_data, null, 2)}
                          </pre>
                        </details>
                      )}

                      {verifyResult.refined_spec && (
                        <div style={{ marginTop: 10, fontSize: '0.75rem', color: 'var(--status-success)' }}>
                          Spec auto-refined ({verifyResult.iterations_performed} iteration{verifyResult.iterations_performed !== 1 ? 's' : ''})
                          {verifyResult.model_used && ` using ${verifyResult.model_used}`}
                        </div>
                      )}

                      {!verifyResult.valid && !verifyResult.refined_spec && verifyResult.iterations_performed === 0 && (
                        <div style={{ marginTop: 8 }}>
                          <button
                            type="button"
                            className="btn btn-ghost"
                            onClick={handleVerify}
                            disabled={verifyLoading}
                            style={{ fontSize: '0.8rem' }}
                          >
                            Retry with AI refinement
                          </button>
                        </div>
                      )}

                      {/* Generate Sanitizer with AI */}
                      {verifyResult.extracted_data && Object.keys(verifyResult.extracted_data).length > 0 && aiAvailable && (
                        <div style={{ marginTop: 16, borderTop: '1px solid var(--border-color)', paddingTop: 16 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>Sanitize Extracted Data</span>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>— AI-generate rules to clean up field values</span>
                          </div>
                          <div className="form-group" style={{ marginBottom: 12 }}>
                            <label className="form-label" style={{ fontSize: '0.8rem' }}>What should be sanitized?</label>
                            <textarea
                              className="form-input"
                              value={sanitizerAiDescription}
                              onChange={(e) => setSanitizerAiDescription(e.target.value)}
                              rows={2}
                              placeholder="e.g. Price fields contain currency symbols like $18.99 USD, titles have extra whitespace"
                              style={{ resize: 'vertical' }}
                            />
                          </div>
                          <button
                            type="button"
                            className="btn btn-ghost"
                            onClick={handleGenerateSanitizer}
                            disabled={sanitizerAiLoading || !verifyUrl.trim()}
                            style={{
                              display: 'flex', alignItems: 'center', gap: 6,
                              fontSize: '0.8rem', width: '100%', justifyContent: 'center',
                              color: sanitizerAiResult ? 'var(--accent-primary)' : 'var(--text-secondary)',
                              border: sanitizerAiResult ? '1px solid var(--accent-primary-dim)' : '1px solid var(--border-color)',
                              background: sanitizerAiResult ? 'var(--accent-primary-dim)' : 'transparent',
                            }}
                          >
                            {sanitizerAiLoading ? (
                              <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Generating sanitizer...</>
                            ) : (
                              <><IconSparkle size={14} /> Generate Sanitizer with AI</>
                            )}
                          </button>
                          {sanitizerAiError && (
                            <div style={{ marginTop: 8, color: 'var(--status-failed)', fontSize: '0.8rem' }}>{sanitizerAiError}</div>
                          )}
                          {sanitizerAiResult && (
                            <div style={{ marginTop: 12 }}>
                              <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
                                AI suggested {sanitizerAiResult.rules.length} rule{sanitizerAiResult.rules.length !== 1 ? 's' : ''}
                              </div>
                              {sanitizerAiResult.rules.map((rule, i) => (
                                <div key={i} style={{ padding: '6px 10px', marginBottom: 4, background: 'var(--bg-primary)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem' }}>
                                  <span style={{ color: 'var(--accent-primary)', fontWeight: 500 }}>{rule.field}</span>
                                  {' → '}
                                  {rule.transforms.map((t, j) => (
                                    <span key={j} style={{ color: 'var(--text-muted)' }}>
                                      {j > 0 && ' → '}{t.type}
                                      {t.type === 'regex_replace' && <span>({t.pattern})</span>}
                                      {t.type === 'default' && <span>({t.value})</span>}
                                    </span>
                                  ))}
                                </div>
                              ))}
                              {sanitizerAiResult.sample_before && sanitizerAiResult.sample_after && (
                                <details style={{ marginTop: 8 }}>
                                  <summary style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                                    Before / After comparison
                                  </summary>
                                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
                                    <div>
                                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 4 }}>Before:</div>
                                      <pre style={{ background: 'var(--bg-primary)', padding: 8, borderRadius: 'var(--radius-sm)', fontSize: '0.7rem', fontFamily: 'var(--font-mono)', maxHeight: 150, overflow: 'auto' }}>
                                        {JSON.stringify(sanitizerAiResult.sample_before, null, 2)}
                                      </pre>
                                    </div>
                                    <div>
                                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 4 }}>After:</div>
                                      <pre style={{ background: 'var(--bg-primary)', padding: 8, borderRadius: 'var(--radius-sm)', fontSize: '0.7rem', fontFamily: 'var(--font-mono)', maxHeight: 150, overflow: 'auto' }}>
                                        {JSON.stringify(sanitizerAiResult.sample_after, null, 2)}
                                      </pre>
                                    </div>
                                  </div>
                                </details>
                              )}
                              <button
                                type="button"
                                className="btn btn-primary"
                                onClick={handleApplySanitizer}
                                style={{ marginTop: 12, width: '100%', justifyContent: 'center', fontSize: '0.8rem' }}
                              >
                                <IconPlus size={14} /> Create & Select This Sanitizer
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
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