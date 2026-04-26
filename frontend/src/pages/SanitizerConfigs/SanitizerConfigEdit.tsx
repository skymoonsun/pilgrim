import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { sanitizerConfigsApi } from '../../api/client';
import { IconEdit } from '../../components/icons/Icons';

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

function toRuleForms(rules: { field: string; transforms: { type: string; pattern?: string; replacement?: string; value?: string; index?: number }[] }[]): RuleForm[] {
  return rules.map(r => ({
    field: r.field,
    transforms: r.transforms.map(t => ({
      type: t.type,
      pattern: t.pattern || '',
      replacement: t.replacement || '',
      value: t.value || '',
      index: t.index != null ? String(t.index) : '',
    })),
  }));
}

export default function SanitizerConfigEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [rules, setRules] = useState<RuleForm[]>([]);

  useEffect(() => {
    if (!id) return;
    sanitizerConfigsApi.get(id).then(c => {
      setName(c.name);
      setDescription(c.description || '');
      setIsActive(c.is_active);
      setRules(toRuleForms(c.rules));
    }).finally(() => setLoading(false));
  }, [id]);

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
    if (!name.trim() || !id) return;
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
      await sanitizerConfigsApi.update(id, payload);
      navigate(`/sanitizer-configs/${id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update sanitizer config');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="loading-overlay"><div className="spinner" /></div>;

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">Edit Sanitizer Config</h1>
      </div>

      <form onSubmit={handleSubmit} style={{ maxWidth: 800 }}>
        {error && <div className="error-banner" style={{ marginBottom: 16 }}>{error}</div>}

        <div className="card" style={{ padding: 28, marginBottom: 24 }}>
          <div className="form-group">
            <label className="form-label">Name *</label>
            <input type="text" className="form-input" value={name} onChange={e => setName(e.target.value)} required />
          </div>
          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="form-input" value={description} onChange={e => setDescription(e.target.value)} rows={2} />
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
            Active
          </label>
        </div>

        <div className="card" style={{ padding: 28, marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h3 className="card-title" style={{ marginBottom: 0 }}>Sanitizer Rules</h3>
            <button type="button" className="btn btn-secondary" onClick={addRule} style={{ fontSize: '0.8rem' }}>
              + Add Rule
            </button>
          </div>

          {rules.map((rule, rIdx) => (
            <div key={rIdx} style={{ marginBottom: 16, padding: 16, border: '1px solid var(--border-color)', borderRadius: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
                  <label className="form-label" style={{ fontSize: '0.75rem' }}>Field Name</label>
                  <input type="text" className="form-input" value={rule.field} onChange={e => updateRuleField(rIdx, e.target.value)} placeholder="e.g., price" />
                </div>
                <button type="button" className="action-btn action-btn--danger" onClick={() => removeRule(rIdx)} style={{ marginTop: 16 }}>
                  <IconEdit size={14} style={{ transform: 'rotate(45deg)' }} />
                </button>
              </div>
              {rule.transforms.map((t, tIdx) => (
                <div key={tIdx} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                  <select className="form-input" value={t.type} onChange={e => updateTransform(rIdx, tIdx, 'type', e.target.value)} style={{ maxWidth: 180 }}>
                    {TRANSFORM_TYPES.map(tt => <option key={tt.value} value={tt.value}>{tt.label}</option>)}
                  </select>
                  {t.type === 'regex_replace' && (
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
                  {(t.type === 'strip' || t.type === 'to_lower' || t.type === 'to_upper' || t.type === 'to_number' || t.type === 'to_int' || t.type === 'extract_number') && (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>No params needed</span>
                  )}
                  <button type="button" className="action-btn action-btn--danger" onClick={() => removeTransform(rIdx, tIdx)} title="Remove transform">
                    <IconEdit size={12} style={{ transform: 'rotate(45deg)' }} />
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
            {saving ? <><div className="spinner" /> Saving...</> : 'Save Changes'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(`/sanitizer-configs/${id}`)}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}