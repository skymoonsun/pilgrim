import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { sanitizerConfigsApi, aiApi } from '../../api/client';
import { IconPlus, IconSparkle } from '../../components/icons/Icons';

const TRANSFORM_TYPES = [
  { value: 'strip', label: 'Strip whitespace' },
  { value: 'to_lower', label: 'Lowercase' },
  { value: 'to_upper', label: 'Uppercase' },
  { value: 'to_number', label: 'To number' },
  { value: 'to_int', label: 'To integer' },
  { value: 'regex_replace', label: 'Regex replace' },
  { value: 'extract_number', label: 'Extract number' },
  { value: 'trim_prefix', label: 'Trim prefix' },
  { value: 'trim_suffix', label: 'Trim suffix' },
  { value: 'default', label: 'Default value' },
  { value: 'split_take', label: 'Split & take' },
];

interface RuleForm {
  field: string;
  transforms: { type: string; pattern: string; replacement: string; value: string; index: string }[];
}

export default function SanitizerConfigCreate() {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [rules, setRules] = useState<RuleForm[]>([]);

  // AI state
  const [aiAvailable, setAiAvailable] = useState(false);
  const [aiChecked, setAiChecked] = useState(false);
  const [aiExpanded, setAiExpanded] = useState(false);
  const [aiUrl, setAiUrl] = useState('');
  const [aiExtractionSpec, setAiExtractionSpec] = useState('');
  const [aiDescription, setAiDescription] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');
  const [aiResult, setAiResult] = useState<{ rules: { field: string; transforms: { type: string; pattern?: string; replacement?: string; value?: string; index?: number }[] }[]; sample_before: Record<string, unknown> | null; sample_after: Record<string, unknown> | null } | null>(null);

  useEffect(() => {
    aiApi.status().then((res) => {
      setAiAvailable(res.enabled && res.reachable);
      setAiChecked(true);
    }).catch(() => {
      setAiAvailable(false);
      setAiChecked(true);
    });
  }, []);

  async function handleAiGenerate(e: React.FormEvent) {
    e.preventDefault();
    setAiError('');
    setAiLoading(true);
    setAiResult(null);
    try {
      let extraction_spec: Record<string, unknown> = {};
      try {
        extraction_spec = JSON.parse(aiExtractionSpec || '{}');
      } catch {
        setAiError('Invalid JSON in Extraction Spec');
        setAiLoading(false);
        return;
      }
      const res = await aiApi.suggestSanitizer({
        url: aiUrl,
        extraction_spec,
        description: aiDescription || undefined,
      });
      setAiResult(res);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : 'AI generation failed');
    }
    setAiLoading(false);
  }

  function handleApplyAiResult() {
    if (!aiResult) return;
    const newRules: RuleForm[] = aiResult.rules.map(r => ({
      field: r.field,
      transforms: r.transforms.map(t => ({
        type: t.type,
        pattern: t.pattern || '',
        replacement: t.replacement || '',
        value: t.value || '',
        index: t.index != null ? String(t.index) : '',
      })),
    }));
    setRules(newRules);
    if (!name.trim() && aiDescription.trim()) {
      setName(aiDescription.trim().slice(0, 100));
    }
    setAiExpanded(false);
    setAiResult(null);
  }

  function addRule() {
    setRules([...rules, { field: '', transforms: [{ type: 'strip', pattern: '', replacement: '', value: '', index: '' }] }]);
  }

  function removeRule(idx: number) {
    setRules(rules.filter((_, i) => i !== idx));
  }

  function updateRuleField(idx: number, field: string) {
    setRules(rules.map((r, i) => i === idx ? { ...r, field } : r));
  }

  function addTransform(ruleIdx: number) {
    setRules(rules.map((r, i) => i === ruleIdx ? { ...r, transforms: [...r.transforms, { type: 'strip', pattern: '', replacement: '', value: '', index: '' }] } : r));
  }

  function removeTransform(ruleIdx: number, tIdx: number) {
    setRules(rules.map((r, i) => i === ruleIdx ? { ...r, transforms: r.transforms.filter((_, j) => j !== tIdx) } : r));
  }

  function updateTransform(ruleIdx: number, tIdx: number, key: string, val: string) {
    setRules(rules.map((r, i) => {
      if (i !== ruleIdx) return r;
      const transforms = r.transforms.map((t, j) => j === tIdx ? { ...t, [key]: val } : t);
      return { ...r, transforms };
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) { setError('Name is required'); return; }
    setError('');
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        description: description.trim() || null,
        is_active: isActive,
        rules: rules.map(r => ({
          field: r.field.trim(),
          transforms: r.transforms
            .filter(t => t.type)
            .map(t => {
              const transform: Record<string, unknown> = { type: t.type };
              if (t.type === 'regex_replace') {
                transform.pattern = t.pattern;
                transform.replacement = t.replacement;
              } else if (t.type === 'trim_prefix' || t.type === 'trim_suffix' || t.type === 'default') {
                transform.value = t.value;
              } else if (t.type === 'split_take') {
                transform.pattern = t.pattern;
                transform.index = t.index ? parseInt(t.index, 10) : 0;
              }
              return transform;
            }),
        })).filter(r => r.field),
      };
      const result = await sanitizerConfigsApi.create(payload);
      navigate(`/sanitizer-configs/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create sanitizer config');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">New Sanitizer Config</h1>
      </div>

      <form onSubmit={handleSubmit} style={{ maxWidth: 800 }}>
        {error && <div className="error-banner" style={{ marginBottom: 16 }}>{error}</div>}

        <div className="card" style={{ padding: 28, marginBottom: 24 }}>
          <div className="form-group">
            <label className="form-label">Name *</label>
            <input type="text" className="form-input" value={name} onChange={e => setName(e.target.value)} placeholder="e.g., Price Cleaner" required />
          </div>
          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="form-input" value={description} onChange={e => setDescription(e.target.value)} placeholder="What this sanitizer does..." rows={2} />
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
            Active
          </label>
        </div>

        {/* AI Generate section */}
        <div className="card" style={{ padding: 28, marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h3 className="card-title" style={{ marginBottom: 0 }}>Generate with AI</h3>
            {!aiChecked ? (
              <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
            ) : aiAvailable ? (
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setAiExpanded(!aiExpanded)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem',
                  color: aiExpanded ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  border: aiExpanded ? '1px solid var(--accent-primary-dim)' : '1px solid var(--border-color)',
                  background: aiExpanded ? 'var(--accent-primary-dim)' : 'transparent',
                }}
              >
                <IconSparkle size={14} />
                Generate with AI
              </button>
            ) : (
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', opacity: 0.5 }}>
                <IconSparkle size={14} /> AI unavailable
              </span>
            )}
          </div>

          {aiExpanded && (
            <div style={{ background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', padding: 16, marginBottom: 16, border: '1px solid var(--border-color)' }}>
              <div className="form-group" style={{ marginBottom: 12 }}>
                <label className="form-label" style={{ fontSize: '0.8rem' }}>Target URL *</label>
                <input type="url" className="form-input" placeholder="https://example.com/product/123" value={aiUrl} onChange={e => setAiUrl(e.target.value)} required />
              </div>
              <div className="form-group" style={{ marginBottom: 12 }}>
                <label className="form-label" style={{ fontSize: '0.8rem' }}>Extraction Spec (JSON) *</label>
                <textarea className="form-input" value={aiExtractionSpec} onChange={e => setAiExtractionSpec(e.target.value)} rows={4} placeholder='{"fields": {"price": {"selector": ".price::text", "type": "css"}}}' style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }} />
              </div>
              <div className="form-group" style={{ marginBottom: 12 }}>
                <label className="form-label" style={{ fontSize: '0.8rem' }}>What to sanitize? (optional)</label>
                <textarea className="form-input" value={aiDescription} onChange={e => setAiDescription(e.target.value)} rows={2} placeholder="e.g. Clean up prices, remove currency symbols, normalize titles" />
              </div>
              <button type="button" className="btn btn-primary" onClick={handleAiGenerate} disabled={aiLoading || !aiUrl || !aiExtractionSpec.trim()} style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center', width: '100%' }}>
                {aiLoading ? <><div className="spinner" /> Generating...</> : <><IconSparkle size={14} /> Generate Sanitizer Rules</>}
              </button>
              {aiError && <div style={{ marginTop: 10, color: 'var(--status-failed)', fontSize: '0.8rem' }}>{aiError}</div>}

              {aiResult && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
                    AI suggested {aiResult.rules.length} rule{aiResult.rules.length !== 1 ? 's' : ''}
                  </div>
                  {aiResult.rules.map((rule, i) => (
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
                  {aiResult.sample_before && aiResult.sample_after && (
                    <details style={{ marginTop: 8 }}>
                      <summary style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>Before / After comparison</summary>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
                        <div>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 4 }}>Before:</div>
                          <pre style={{ background: 'var(--bg-primary)', padding: 8, borderRadius: 'var(--radius-sm)', fontSize: '0.7rem', fontFamily: 'var(--font-mono)', maxHeight: 150, overflow: 'auto' }}>{JSON.stringify(aiResult.sample_before, null, 2)}</pre>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 4 }}>After:</div>
                          <pre style={{ background: 'var(--bg-primary)', padding: 8, borderRadius: 'var(--radius-sm)', fontSize: '0.7rem', fontFamily: 'var(--font-mono)', maxHeight: 150, overflow: 'auto' }}>{JSON.stringify(aiResult.sample_after, null, 2)}</pre>
                        </div>
                      </div>
                    </details>
                  )}
                  <button type="button" className="btn btn-primary" onClick={handleApplyAiResult} style={{ marginTop: 12, width: '100%', justifyContent: 'center', fontSize: '0.8rem' }}>
                    Apply These Rules
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="card" style={{ padding: 28, marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h3 className="card-title" style={{ marginBottom: 0 }}>Sanitizer Rules</h3>
            <button type="button" className="btn btn-secondary" onClick={addRule} style={{ fontSize: '0.8rem' }}>
              <IconPlus size={14} /> Add Rule
            </button>
          </div>

          {rules.length === 0 && (
            <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
              <p>No rules yet. Add a rule to define how extracted fields should be transformed.</p>
              <p style={{ fontSize: '0.8rem' }}>Example: field "price" → strip currency symbols → convert to number</p>
            </div>
          )}

          {rules.map((rule, rIdx) => (
            <div key={rIdx} style={{ marginBottom: 16, padding: 16, border: '1px solid var(--border-color)', borderRadius: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
                  <label className="form-label" style={{ fontSize: '0.75rem' }}>Field Name</label>
                  <input type="text" className="form-input" value={rule.field} onChange={e => updateRuleField(rIdx, e.target.value)} placeholder="e.g., price" />
                </div>
                <button type="button" className="action-btn action-btn--danger" onClick={() => removeRule(rIdx)} style={{ marginTop: 16 }}>
                  <IconPlus size={14} style={{ transform: 'rotate(45deg)' }} />
                </button>
              </div>
              {rule.transforms.map((t, tIdx) => (
                <div key={tIdx} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                  <select className="form-input" value={t.type} onChange={e => updateTransform(rIdx, tIdx, 'type', e.target.value)} style={{ maxWidth: 180 }}>
                    {TRANSFORM_TYPES.map(tt => <option key={tt.value} value={tt.value}>{tt.label}</option>)}
                  </select>
                  {(t.type === 'regex_replace') && (
                    <>
                      <input type="text" className="form-input" value={t.pattern} onChange={e => updateTransform(rIdx, tIdx, 'pattern', e.target.value)} placeholder="Pattern" style={{ flex: 1 }} />
                      <input type="text" className="form-input" value={t.replacement} onChange={e => updateTransform(rIdx, tIdx, 'replacement', e.target.value)} placeholder="Replacement" style={{ flex: 1 }} />
                    </>
                  )}
                  {(t.type === 'trim_prefix' || t.type === 'trim_suffix' || t.type === 'default') && (
                    <input type="text" className="form-input" value={t.value} onChange={e => updateTransform(rIdx, tIdx, 'value', e.target.value)} placeholder="Value" style={{ flex: 1 }} />
                  )}
                  {t.type === 'split_take' && (
                    <>
                      <input type="text" className="form-input" value={t.pattern} onChange={e => updateTransform(rIdx, tIdx, 'pattern', e.target.value)} placeholder="Separator" style={{ flex: 1 }} />
                      <input type="number" className="form-input" value={t.index} onChange={e => updateTransform(rIdx, tIdx, 'index', e.target.value)} placeholder="Index" style={{ maxWidth: 80 }} />
                    </>
                  )}
                  {t.type === 'extract_number' && <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Extracts first number from string</span>}
                  {(t.type === 'strip' || t.type === 'to_lower' || t.type === 'to_upper' || t.type === 'to_number' || t.type === 'to_int') && (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>No params needed</span>
                  )}
                  <button type="button" className="action-btn action-btn--danger" onClick={() => removeTransform(rIdx, tIdx)} title="Remove transform">
                    <IconPlus size={12} style={{ transform: 'rotate(45deg)' }} />
                  </button>
                </div>
              ))}
              <button type="button" className="btn btn-ghost" onClick={() => addTransform(rIdx)} style={{ fontSize: '0.75rem', padding: '2px 8px' }}>
                + Add Transform
              </button>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
          <button type="submit" className="btn btn-primary" disabled={saving || !name.trim()} style={{ minWidth: 160, justifyContent: 'center' }}>
            {saving ? <><div className="spinner" /> Saving...</> : <><IconPlus size={16} /> Create Sanitizer</>}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/sanitizer-configs')}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}