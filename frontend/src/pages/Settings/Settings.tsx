import { IconShield } from '../../components/icons/Icons';

export default function Settings() {
  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Application configuration</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>General</h3>
          <div className="form-group">
            <label className="form-label">Default Queue</label>
            <select className="form-input form-select" defaultValue="crawl_default">
              <option value="crawl_high">crawl_high (priority)</option>
              <option value="crawl_default">crawl_default (standard)</option>
              <option value="crawl_low">crawl_low (backfill)</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Default Concurrency</label>
            <input type="number" className="form-input" defaultValue={2} min={1} max={10} />
          </div>
          <button className="btn btn-primary">Save Changes</button>
        </div>

        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Proxy Configuration</h3>
          <div className="empty-state" style={{ padding: '40px 20px' }}>
            <div className="empty-state-icon"><IconShield size={48} /></div>
            <div className="empty-state-text">Coming Soon</div>
            <div className="empty-state-sub">
              Proxy pool management will be available in a future release
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
