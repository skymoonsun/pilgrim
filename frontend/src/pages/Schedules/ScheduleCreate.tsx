import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { schedulesApi, configsApi, proxySourceApi } from '../../api/client';
import type { CrawlConfig, ProxySourceConfig, ScheduleCreateData, ConfigLinkUrlsCreate, ScheduleType } from '../../api/client';
import { IconPlus, IconTrash, IconCalendar, IconMail, IconGlobe } from '../../components/icons/Icons';

interface ConfigEntry {
  config_id: string;
  urls: { url: string; label: string }[];
}

export default function ScheduleCreate() {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [configs, setConfigs] = useState<CrawlConfig[]>([]);
  const [proxySources, setProxySources] = useState<ProxySourceConfig[]>([]);

  const [form, setForm] = useState({
    name: '',
    description: '',
    timezone: 'UTC',
    scheduleKind: 'crawl' as ScheduleType,
    scheduleType: 'interval' as 'interval' | 'cron',
    cron_expression: '',
    interval_minutes: '60',
    default_queue: 'crawl_default',
    configEntries: [] as ConfigEntry[],
    selectedProxySourceIds: [] as string[],
    enableCallback: false,
    callbackUrl: '',
    callbackMethod: 'POST',
    callbackHeaders: '',
    callbackFieldMapping: '{\n  "field_mapping": {},\n  "static_fields": {},\n  "wrap_key": "results"\n}',
    callbackBatchResults: true,
    callbackRetryCount: '3',
    enableEmailNotification: false,
    emailRecipients: '',
    emailSubjectTemplate: 'Pilgrim: {{schedule_name}} completed',
    emailFieldMapping: '{}',
    emailOnSuccess: true,
    emailOnFailure: true,
    emailBatchResults: true,
    emailIncludeMetadata: true,
  });

  useEffect(() => {
    configsApi.list(0, 200).then((res) => setConfigs(res.items));
    proxySourceApi.list(0, 200).then((res) => setProxySources(res.items));
  }, []);

  function updateField(field: string, value: unknown) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  // ── Config entry management ───────────────────────────────────

  function addConfigEntry(configId: string) {
    setForm((prev) => ({
      ...prev,
      configEntries: [
        ...prev.configEntries,
        { config_id: configId, urls: [{ url: '', label: '' }] },
      ],
    }));
  }

  function removeConfigEntry(index: number) {
    setForm((prev) => ({
      ...prev,
      configEntries: prev.configEntries.filter((_, i) => i !== index),
    }));
  }

  function addUrlToConfig(configIndex: number) {
    setForm((prev) => {
      const entries = [...prev.configEntries];
      entries[configIndex] = {
        ...entries[configIndex],
        urls: [...entries[configIndex].urls, { url: '', label: '' }],
      };
      return { ...prev, configEntries: entries };
    });
  }

  function removeUrlFromConfig(configIndex: number, urlIndex: number) {
    setForm((prev) => {
      const entries = [...prev.configEntries];
      entries[configIndex] = {
        ...entries[configIndex],
        urls: entries[configIndex].urls.filter((_, i) => i !== urlIndex),
      };
      return { ...prev, configEntries: entries };
    });
  }

  function updateUrlInConfig(configIndex: number, urlIndex: number, field: 'url' | 'label', value: string) {
    setForm((prev) => {
      const entries = [...prev.configEntries];
      const urls = [...entries[configIndex].urls];
      urls[urlIndex] = { ...urls[urlIndex], [field]: value };
      entries[configIndex] = { ...entries[configIndex], urls };
      return { ...prev, configEntries: entries };
    });
  }

  // ── Proxy source management ───────────────────────────────────

  function toggleProxySource(id: string) {
    setForm((prev) => ({
      ...prev,
      selectedProxySourceIds: prev.selectedProxySourceIds.includes(id)
        ? prev.selectedProxySourceIds.filter((s) => s !== id)
        : [...prev.selectedProxySourceIds, id],
    }));
  }

  // ── Available items (not already selected) ──────────────────

  const selectedConfigIds = form.configEntries.map((e) => e.config_id);
  const availableConfigs = configs.filter((c) => !selectedConfigIds.includes(c.id));
  const availableProxySources = proxySources.filter(
    (s) => !form.selectedProxySourceIds.includes(s.id)
  );

  // ── Submit ────────────────────────────────────────────────────

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
        schedule_type: form.scheduleKind,
      };

      if (form.scheduleType === 'cron') {
        data.cron_expression = form.cron_expression;
      } else {
        data.interval_seconds = parseInt(form.interval_minutes) * 60;
      }

      if (form.scheduleKind === 'crawl') {
        const config_links: ConfigLinkUrlsCreate[] = form.configEntries
          .filter((entry) => entry.urls.some((u) => u.url.trim()))
          .map((entry) => ({
            config_id: entry.config_id,
            urls: entry.urls
              .filter((u) => u.url.trim())
              .map((u) => ({ url: u.url, label: u.label || null })),
          }));
        data.config_links = config_links;
      } else {
        data.proxy_source_links = form.selectedProxySourceIds.map((id) => ({
          proxy_source_id: id,
        }));
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

      if (form.enableEmailNotification && form.emailRecipients.trim()) {
        let email_field_mapping = {};
        try {
          email_field_mapping = JSON.parse(form.emailFieldMapping || '{}');
        } catch {
          setError('Invalid JSON in email field mapping');
          setSaving(false);
          return;
        }

        data.email_notification = {
          recipient_emails: form.emailRecipients.split(',').map((e: string) => e.trim()).filter((e: string) => e),
          subject_template: form.emailSubjectTemplate,
          field_mapping: email_field_mapping,
          include_metadata: form.emailIncludeMetadata,
          batch_results: form.emailBatchResults,
          on_success: form.emailOnSuccess,
          on_failure: form.emailOnFailure,
        };
      }

      const created = await schedulesApi.create(data);
      navigate(`/schedules/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create failed');
    }
    setSaving(false);
  }

  function getConfigName(id: string) {
    return configs.find((c) => c.id === id)?.name || id.slice(0, 8);
  }

  function getProxySourceName(id: string) {
    return proxySources.find((s) => s.id === id)?.name || id.slice(0, 8);
  }

  const canSubmit = form.name && (
    (form.scheduleKind === 'crawl' && form.configEntries.length > 0) ||
    (form.scheduleKind === 'proxy_source' && form.selectedProxySourceIds.length > 0)
  );

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">New Schedule</h1>
          <p className="page-subtitle">Create a recurring schedule for crawl jobs or proxy source fetches</p>
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

          {/* ── Left: General + Timing ── */}
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

              {/* Schedule Kind Selector */}
              <div className="form-group">
                <label className="form-label">Schedule Type</label>
                <div style={{ display: 'flex', gap: 12 }}>
                  {(['crawl', 'proxy_source'] as const).map((kind) => (
                    <button type="button" key={kind}
                      className={`btn ${form.scheduleKind === kind ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => {
                        updateField('scheduleKind', kind);
                        if (kind === 'crawl') {
                          updateField('selectedProxySourceIds', []);
                        } else {
                          updateField('configEntries', []);
                        }
                      }}
                      style={{ flex: 1, justifyContent: 'center' }}>
                      {kind === 'crawl' ? 'Crawl Schedule' : 'Proxy Source Schedule'}
                    </button>
                  ))}
                </div>
                {form.scheduleKind === 'proxy_source' && (
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 6 }}>
                    Fetches and validates proxies from linked sources on each trigger
                  </div>
                )}
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

            {/* Callback */}
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
                      Use $.data.*, $.url, $.metadata.* paths
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 16, alignItems: 'end' }}>
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

            {/* Email Notification */}
            <div className="card" style={{ padding: 28 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h3 className="card-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <IconMail size={18} /> Email Notification (Optional)
                </h3>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={form.enableEmailNotification}
                    onChange={(e) => updateField('enableEmailNotification', e.target.checked)} />
                  Enable
                </label>
              </div>

              {form.enableEmailNotification && (
                <>
                  <div className="form-group">
                    <label className="form-label">Recipients (comma-separated)</label>
                    <input type="text" className="form-input" placeholder="user@example.com, admin@example.com"
                      value={form.emailRecipients}
                      onChange={(e) => updateField('emailRecipients', e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Subject Template</label>
                    <input type="text" className="form-input" value={form.emailSubjectTemplate}
                      onChange={(e) => updateField('emailSubjectTemplate', e.target.value)} />
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>
                      Use {'{{schedule_name}}'}, {'{{job_id}}'}, etc. as placeholders
                    </div>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Field Mapping (JSON)</label>
                    <textarea className="form-input" rows={4} value={form.emailFieldMapping}
                      onChange={(e) => updateField('emailFieldMapping', e.target.value)}
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', whiteSpace: 'pre' }} />
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>
                      Use $.data.*, $.url, $.metadata.* paths (same as callback)
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.emailOnSuccess}
                        onChange={(e) => updateField('emailOnSuccess', e.target.checked)} />
                      On Success
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.emailOnFailure}
                        onChange={(e) => updateField('emailOnFailure', e.target.checked)} />
                      On Failure
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.emailBatchResults}
                        onChange={(e) => updateField('emailBatchResults', e.target.checked)} />
                      Batch Results
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.emailIncludeMetadata}
                        onChange={(e) => updateField('emailIncludeMetadata', e.target.checked)} />
                      Include Metadata
                    </label>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* ── Right: Targets ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

            {form.scheduleKind === 'crawl' ? (
              <>
                {/* Add config selector */}
                {availableConfigs.length > 0 && (
                  <div className="card" style={{ padding: 28 }}>
                    <h3 className="card-title" style={{ marginBottom: 16 }}>Add Config + URLs</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {availableConfigs.map((config) => (
                        <button type="button" key={config.id}
                          onClick={() => addConfigEntry(config.id)}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 10,
                            padding: '10px 14px',
                            background: 'var(--bg-tertiary)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: 'var(--radius-md)',
                            cursor: 'pointer',
                            color: 'var(--text-primary)',
                            transition: 'all 0.15s ease',
                            width: '100%',
                            textAlign: 'left',
                          }}>
                          <IconPlus size={14} />
                          <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{config.name}</div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{config.scraper_profile}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Selected config entries with their URLs */}
                {form.configEntries.map((entry, ci) => (
                  <div key={entry.config_id} className="card" style={{
                    padding: 28,
                    border: '1px solid var(--accent-cyan)',
                    boxShadow: '0 0 12px rgba(0,240,255,0.06)',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                      <h3 className="card-title" style={{ margin: 0 }}>
                        <span style={{ color: 'var(--accent-cyan)' }}>{getConfigName(entry.config_id)}</span>
                      </h3>
                      <button type="button" className="action-btn" onClick={() => removeConfigEntry(ci)}
                        style={{ color: 'var(--status-failed)' }}>
                        <IconTrash size={16} />
                      </button>
                    </div>

                    <label className="form-label">Target URLs for this config</label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {entry.urls.map((urlItem, ui) => (
                        <div key={ui} style={{ display: 'flex', gap: 8, alignItems: 'start' }}>
                          <div style={{ flex: 1 }}>
                            <input type="url" className="form-input" placeholder="https://example.com/page"
                              value={urlItem.url} onChange={(e) => updateUrlInConfig(ci, ui, 'url', e.target.value)}
                              style={{ marginBottom: 4 }} />
                            <input type="text" className="form-input" placeholder="Label (optional)"
                              value={urlItem.label} onChange={(e) => updateUrlInConfig(ci, ui, 'label', e.target.value)}
                              style={{ fontSize: '0.8rem' }} />
                          </div>
                          {entry.urls.length > 1 && (
                            <button type="button" className="action-btn" onClick={() => removeUrlFromConfig(ci, ui)}
                              style={{ marginTop: 6 }}>
                              <IconTrash size={14} />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                    <button type="button" className="btn btn-secondary" onClick={() => addUrlToConfig(ci)}
                      style={{ marginTop: 10 }}>
                      <IconPlus size={14} /> Add URL
                    </button>
                  </div>
                ))}

                {form.configEntries.length === 0 && (
                  <div className="card" style={{ padding: 40, textAlign: 'center' }}>
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      Select configs from the list above to add URL targets
                    </div>
                  </div>
                )}
              </>
            ) : (
              <>
                {/* Proxy source selector */}
                {availableProxySources.length > 0 && (
                  <div className="card" style={{ padding: 28 }}>
                    <h3 className="card-title" style={{ marginBottom: 16 }}>Add Proxy Sources</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {availableProxySources.map((source) => (
                        <button type="button" key={source.id}
                          onClick={() => toggleProxySource(source.id)}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 10,
                            padding: '10px 14px',
                            background: 'var(--bg-tertiary)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: 'var(--radius-md)',
                            cursor: 'pointer',
                            color: 'var(--text-primary)',
                            transition: 'all 0.15s ease',
                            width: '100%',
                            textAlign: 'left',
                          }}>
                          <IconPlus size={14} />
                          <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{source.name}</div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{source.format_type} — {source.url.slice(0, 50)}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Selected proxy sources */}
                {form.selectedProxySourceIds.map((sourceId) => (
                  <div key={sourceId} className="card" style={{
                    padding: 20,
                    border: '1px solid var(--accent-cyan)',
                    boxShadow: '0 0 12px rgba(0,240,255,0.06)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                  }}>
                    <IconGlobe size={18} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                        {getProxySourceName(sourceId)}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        {proxySources.find((s) => s.id === sourceId)?.url.slice(0, 60)}
                      </div>
                    </div>
                    <button type="button" className="action-btn" onClick={() => toggleProxySource(sourceId)}
                      style={{ color: 'var(--status-failed)' }}>
                      <IconTrash size={16} />
                    </button>
                  </div>
                ))}

                {form.selectedProxySourceIds.length === 0 && (
                  <div className="card" style={{ padding: 40, textAlign: 'center' }}>
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      Select proxy sources from the list above
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
          <button type="submit" className="btn btn-primary"
            disabled={saving || !canSubmit}
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