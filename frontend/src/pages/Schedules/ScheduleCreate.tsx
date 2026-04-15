import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { schedulesApi, configsApi } from '../../api/client';
import type { CrawlConfig, ScheduleCreateData } from '../../api/client';
import { IconPlus, IconTrash, IconCalendar } from '../../components/icons/Icons';

export default function ScheduleCreate() {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [configs, setConfigs] = useState<CrawlConfig[]>([]);

  const [form, setForm] = useState({
    name: '',
    description: '',
    timezone: 'UTC',
    scheduleType: 'interval' as 'interval' | 'cron',
    cron_expression: '',
    interval_minutes: '60',
    default_queue: 'crawl_default',
    selectedConfigIds: [] as string[],
    urls: [{ url: '', label: '' }],
    enableCallback: false,
    callbackUrl: '',
    callbackMethod: 'POST',
    callbackHeaders: '',
    callbackFieldMapping: '{\n  "field_mapping": {},\n  "static_fields": {},\n  "wrap_key": "results"\n}',
    callbackBatchResults: true,
    callbackRetryCount: '3',
  });

  useEffect(() => {
    configsApi.list(0, 100).then((res) => setConfigs(res.items));
  }, []);

  function updateField(field: string, value: unknown) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function addUrl() {
    setForm((prev) => ({
      ...prev,
      urls: [...prev.urls, { url: '', label: '' }],
    }));
  }

  function removeUrl(index: number) {
    setForm((prev) => ({
      ...prev,
      urls: prev.urls.filter((_, i) => i !== index),
    }));
  }

  function updateUrl(index: number, field: 'url' | 'label', value: string) {
    setForm((prev) => {
      const urls = [...prev.urls];
      urls[index] = { ...urls[index], [field]: value };
      return { ...prev, urls };
    });
  }

  function toggleConfig(configId: string) {
    setForm((prev) => {
      const ids = prev.selectedConfigIds.includes(configId)
        ? prev.selectedConfigIds.filter((id) => id !== configId)
        : [...prev.selectedConfigIds, configId];
      return { ...prev, selectedConfigIds: ids };
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSaving(true);

    try {
      const data: ScheduleCreateData = {
        name: form.name,
        description: form.description || null,
        timezone: form.timezone,
        default_queue: form.default_queue,
        config_ids: form.selectedConfigIds,
        urls: form.urls
          .filter((u) => u.url.trim())
          .map((u) => ({ url: u.url, label: u.label || null })),
      };

      if (form.scheduleType === 'cron') {
        data.cron_expression = form.cron_expression;
      } else {
        data.interval_seconds = parseInt(form.interval_minutes) * 60;
      }

      if (form.enableCallback && form.callbackUrl) {
        let field_mapping = {};
        try {
          field_mapping = JSON.parse(form.callbackFieldMapping || '{}');
        } catch {
          setError('Invalid JSON in field mapping');
          setSaving(false);
          return;
        }

        let headers = null;
        if (form.callbackHeaders.trim()) {
          try {
            headers = JSON.parse(form.callbackHeaders);
          } catch {
            setError('Invalid JSON in callback headers');
            setSaving(false);
            return;
          }
        }

        data.callback = {
          url: form.callbackUrl,
          method: form.callbackMethod,
          headers,
          field_mapping,
          batch_results: form.callbackBatchResults,
          retry_count: parseInt(form.callbackRetryCount),
        };
      }

      const created = await schedulesApi.create(data);
      navigate(`/schedules/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create failed');
    }
    setSaving(false);
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">New Schedule</h1>
          <p className="page-subtitle">Create a recurring crawl schedule</p>
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

          {/* ── Left: General + Schedule ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>General</h3>
              <div className="form-group">
                <label className="form-label">Name *</label>
                <input type="text" className="form-input" placeholder="e.g. Daily Product Scrape"
                  value={form.name} onChange={(e) => updateField('name', e.target.value)}
                  required maxLength={200} />
              </div>
              <div className="form-group">
                <label className="form-label">Description</label>
                <textarea className="form-input" placeholder="What does this schedule do?"
                  value={form.description} onChange={(e) => updateField('description', e.target.value)}
                  rows={2} style={{ resize: 'vertical' }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div className="form-group">
                  <label className="form-label">Timezone</label>
                  <input type="text" className="form-input" value={form.timezone}
                    onChange={(e) => updateField('timezone', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Queue</label>
                  <select className="form-input form-select" value={form.default_queue}
                    onChange={(e) => updateField('default_queue', e.target.value)}>
                    <option value="crawl_high">crawl_high</option>
                    <option value="crawl_default">crawl_default</option>
                    <option value="crawl_low">crawl_low</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>Schedule Timing</h3>
              <div className="form-group">
                <label className="form-label">Type</label>
                <div style={{ display: 'flex', gap: 12 }}>
                  {(['interval', 'cron'] as const).map((type) => (
                    <button type="button" key={type}
                      className={`btn ${form.scheduleType === type ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => updateField('scheduleType', type)}
                      style={{ flex: 1, justifyContent: 'center' }}>
                      {type === 'interval' ? 'Interval' : 'Cron Expression'}
                    </button>
                  ))}
                </div>
              </div>
              {form.scheduleType === 'interval' ? (
                <div className="form-group">
                  <label className="form-label">Interval (minutes)</label>
                  <input type="number" className="form-input" min="1"
                    value={form.interval_minutes}
                    onChange={(e) => updateField('interval_minutes', e.target.value)} />
                </div>
              ) : (
                <div className="form-group">
                  <label className="form-label">Cron Expression</label>
                  <input type="text" className="form-input" placeholder="0 */6 * * *"
                    value={form.cron_expression}
                    onChange={(e) => updateField('cron_expression', e.target.value)} />
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
                    min hour day month weekday
                  </div>
                </div>
              )}
            </div>

            {/* Configs */}
            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>Crawl Configs *</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {configs.map((config) => (
                  <label key={config.id} style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 14px',
                    background: form.selectedConfigIds.includes(config.id) ? 'rgba(0,240,255,0.08)' : 'var(--bg-tertiary)',
                    border: `1px solid ${form.selectedConfigIds.includes(config.id) ? 'var(--accent-cyan)' : 'var(--border-subtle)'}`,
                    borderRadius: 'var(--radius-md)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}>
                    <input type="checkbox" checked={form.selectedConfigIds.includes(config.id)}
                      onChange={() => toggleConfig(config.id)} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.85rem' }}>{config.name}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{config.scraper_profile}</div>
                    </div>
                  </label>
                ))}
                {configs.length === 0 && (
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No configs available. Create one first.</p>
                )}
              </div>
            </div>
          </div>

          {/* ── Right: URLs + Callback ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>Target URLs *</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {form.urls.map((urlItem, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'start' }}>
                    <div style={{ flex: 1 }}>
                      <input type="url" className="form-input" placeholder="https://example.com/page"
                        value={urlItem.url} onChange={(e) => updateUrl(i, 'url', e.target.value)}
                        style={{ marginBottom: 4 }} />
                      <input type="text" className="form-input" placeholder="Label (optional)"
                        value={urlItem.label} onChange={(e) => updateUrl(i, 'label', e.target.value)}
                        style={{ fontSize: '0.8rem' }} />
                    </div>
                    {form.urls.length > 1 && (
                      <button type="button" className="action-btn" onClick={() => removeUrl(i)}
                        style={{ marginTop: 6 }}>
                        <IconTrash size={16} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <button type="button" className="btn btn-secondary" onClick={addUrl}
                style={{ marginTop: 12 }}>
                <IconPlus size={14} /> Add URL
              </button>
            </div>

            <div className="card" style={{ padding: 28 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h3 className="card-title" style={{ margin: 0 }}>Callback (Optional)</h3>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={form.enableCallback}
                    onChange={(e) => updateField('enableCallback', e.target.checked)} />
                  Enable
                </label>
              </div>

              {form.enableCallback && (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
                    <div className="form-group">
                      <label className="form-label">Webhook URL</label>
                      <input type="url" className="form-input" placeholder="https://api.example.com/webhook"
                        value={form.callbackUrl} onChange={(e) => updateField('callbackUrl', e.target.value)} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Method</label>
                      <select className="form-input form-select" value={form.callbackMethod}
                        onChange={(e) => updateField('callbackMethod', e.target.value)}>
                        <option>POST</option>
                        <option>PUT</option>
                        <option>PATCH</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Headers (JSON)</label>
                    <textarea className="form-input" rows={2}
                      placeholder='{"Authorization": "Bearer token123"}'
                      value={form.callbackHeaders}
                      onChange={(e) => updateField('callbackHeaders', e.target.value)}
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }} />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Field Mapping (JSON)</label>
                    <textarea className="form-input" rows={6}
                      value={form.callbackFieldMapping}
                      onChange={(e) => updateField('callbackFieldMapping', e.target.value)}
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', whiteSpace: 'pre' }} />
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>
                      Use $.data.*, $.url, $.metadata.* paths. See docs for details.
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 16 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.callbackBatchResults}
                        onChange={(e) => updateField('callbackBatchResults', e.target.checked)} />
                      Batch Results
                    </label>
                    <div className="form-group" style={{ flex: 0 }}>
                      <label className="form-label" style={{ fontSize: '0.75rem' }}>Retries</label>
                      <input type="number" className="form-input" min="0" max="10" style={{ width: 70 }}
                        value={form.callbackRetryCount}
                        onChange={(e) => updateField('callbackRetryCount', e.target.value)} />
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
          <button type="submit" className="btn btn-primary" disabled={saving || !form.name}
            style={{ minWidth: 180, justifyContent: 'center' }}>
            {saving ? (
              <><div className="spinner" /> Creating...</>
            ) : (
              <><IconCalendar size={16} /> Create Schedule</>
            )}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/schedules')}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
