import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { configsApi, scrapeApi } from '../../api/client';
import type { CrawlConfig, ScrapeResponse } from '../../api/client';
import { IconRocket, IconFlask } from '../../components/icons/Icons';

export default function ScrapePlayground() {
  const [searchParams] = useSearchParams();
  const [configs, setConfigs] = useState<CrawlConfig[]>([]);
  const [selectedConfig, setSelectedConfig] = useState(searchParams.get('config') || '');
  const [url, setUrl] = useState('');
  const [result, setResult] = useState<ScrapeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    configsApi.list(0, 100).then((res) => setConfigs(res.items));
  }, []);

  async function handleScrape(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedConfig || !url) return;
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const res = await scrapeApi.execute({
        config_id: selectedConfig,
        url,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scrape failed');
    }
    setLoading(false);
  }

  const selectedName = configs.find((c) => c.id === selectedConfig)?.name;

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Scrape Playground</h1>
          <p className="page-subtitle">Test your crawl configs with real URLs</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* ── Request panel ──────────────────────────── */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Request</h3>
          <form onSubmit={handleScrape}>
            <div className="form-group">
              <label className="form-label">Config</label>
              <select
                className="form-input form-select"
                value={selectedConfig}
                onChange={(e) => setSelectedConfig(e.target.value)}
              >
                <option value="">Select a config...</option>
                {configs.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.scraper_profile})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Target URL</label>
              <input
                type="url"
                className="form-input"
                placeholder="https://example.com/page"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
              />
            </div>

            {selectedName && (
              <div className="form-group">
                <label className="form-label">Config Details</label>
                <div
                  style={{
                    background: 'var(--bg-tertiary)',
                    borderRadius: 'var(--radius-md)',
                    padding: '12px 16px',
                    fontSize: '0.8rem',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <div>
                    <strong style={{ color: 'var(--text-primary)' }}>Profile:</strong>{' '}
                    {configs.find((c) => c.id === selectedConfig)?.scraper_profile}
                  </div>
                  <div style={{ marginTop: 4 }}>
                    <strong style={{ color: 'var(--text-primary)' }}>Proxy:</strong>{' '}
                    {configs.find((c) => c.id === selectedConfig)?.use_proxy ? 'Enabled' : 'Disabled'}
                  </div>
                </div>
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !selectedConfig || !url}
              style={{ width: '100%', justifyContent: 'center', marginTop: 8 }}
            >
              {loading ? (
                <>
                  <div className="spinner" />
                  Scraping...
                </>
              ) : (
                <>
                  <IconRocket size={16} />
                  Execute Scrape
                </>
              )}
            </button>
          </form>
        </div>

        {/* ── Response panel ─────────────────────────── */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Response</h3>

          {error && (
            <div
              style={{
                background: 'var(--status-failed-bg)',
                border: '1px solid rgba(255,82,82,0.3)',
                borderRadius: 'var(--radius-md)',
                padding: '14px 18px',
                color: 'var(--status-failed)',
                fontSize: '0.85rem',
              }}
            >
              {error}
            </div>
          )}

          {result && (
            <div>
              <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
                <span
                  className={`badge badge--${result.error ? 'failed' : 'success'}`}
                >
                  {result.http_status || (result.error ? 'Error' : 'OK')}
                </span>
                <span
                  style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}
                >
                  {result.duration_ms}ms
                </span>
              </div>

              {result.error && (
                <div
                  style={{
                    background: 'var(--status-failed-bg)',
                    borderRadius: 'var(--radius-md)',
                    padding: '14px 18px',
                    color: 'var(--status-failed)',
                    fontSize: '0.85rem',
                    marginBottom: 16,
                  }}
                >
                  {result.error}
                </div>
              )}

              {result.data && (
                <pre
                  style={{
                    background: 'var(--bg-tertiary)',
                    borderRadius: 'var(--radius-md)',
                    padding: 18,
                    fontSize: '0.78rem',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-secondary)',
                    overflow: 'auto',
                    maxHeight: 400,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {JSON.stringify(result.data, null, 2)}
                </pre>
              )}
            </div>
          )}

          {!result && !error && (
            <div className="empty-state">
              <div className="empty-state-icon"><IconFlask size={48} /></div>
              <div className="empty-state-text">Ready to scrape</div>
              <div className="empty-state-sub">
                Select a config, enter a URL, and hit execute
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
