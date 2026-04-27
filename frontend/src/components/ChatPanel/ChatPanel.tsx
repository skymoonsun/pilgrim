import { useState, useRef, useEffect, useCallback } from 'react';
import { aiApi } from '../../api/client';
import type { ChatMessage, ChatUrlContext, SpecVerificationResponse, SanitizerSuggestionResponse } from '../../api/client';
import { IconSparkle, IconPlus, IconX, IconCheck, IconRefresh, IconTrash } from '../icons/Icons';
import { toast } from '../ui/Toast';

interface ChatPanelProps {
  configId: string;
  scraperProfile: string;
  initialSpec: Record<string, unknown> | null;
  configName: string;
  headers?: Record<string, string> | null;
  cookies?: Record<string, string> | null;
  onApplySpec: (spec: Record<string, unknown>) => void;
  onVerifySpec: (url: string, spec: Record<string, unknown>) => Promise<SpecVerificationResponse>;
  onSuggestSanitizer: (url: string, spec: Record<string, unknown>, description?: string) => Promise<SanitizerSuggestionResponse>;
}

interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  spec?: Record<string, unknown>;
  urlContexts?: ChatUrlContext[];
  verifyResult?: SpecVerificationResponse;
  sanitizerResult?: { rules: { field: string; transforms: { type: string; pattern?: string; replacement?: string; value?: string; index?: number }[] }[]; sample_before: Record<string, unknown> | null; sample_after: Record<string, unknown> | null };
  applied?: boolean;
}

const STORAGE_KEY = (configId: string) => `pilgrim_chat_${configId}`;

let nextMsgId = 1;

export default function ChatPanel({
  configId,
  scraperProfile,
  initialSpec,
  configName,
  headers,
  cookies,
  onApplySpec,
  onVerifySpec,
  onSuggestSanitizer,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [urlInputs, setUrlInputs] = useState<string[]>(['']);
  const [isLoading, setIsLoading] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isSanitizing, setIsSanitizing] = useState(false);
  const [error, setError] = useState('');
  const [lastSpec, setLastSpec] = useState<Record<string, unknown> | null>(initialSpec);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    const el = messagesContainerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, isVerifying, isSanitizing, scrollToBottom]);

  // Load chat history from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY(configId));
      if (stored) {
        const data = JSON.parse(stored);
        if (data.messages && Array.isArray(data.messages)) {
          setMessages(data.messages);
        }
        if (data.chatHistory && Array.isArray(data.chatHistory)) {
          setChatHistory(data.chatHistory);
        }
        if (data.lastSpec) {
          setLastSpec(data.lastSpec);
        }
        if (data.urlInputs && Array.isArray(data.urlInputs)) {
          setUrlInputs(data.urlInputs);
        }
        setHistoryLoaded(true);
        return;
      }
    } catch { /* ignore parse errors */ }

    // No stored history — add initial system message
    if (initialSpec && Object.keys(initialSpec).length > 0 && initialSpec.fields && Object.keys(initialSpec.fields as object).length > 0) {
      const fields = Object.keys(initialSpec.fields as object);
      setMessages([{
        id: `sys-${nextMsgId++}`,
        role: 'system',
        content: `Current config "${configName}" has ${fields.length} field${fields.length !== 1 ? 's' : ''}: ${fields.join(', ')}. Ask me to refine it!`,
      }]);
    } else {
      setMessages([{
        id: `sys-${nextMsgId++}`,
        role: 'system',
        content: 'Provide URLs and describe what data to extract. I\'ll generate an extraction spec for you.',
      }]);
    }
    setHistoryLoaded(true);
  }, [configId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist chat history to localStorage whenever it changes (after initial load)
  useEffect(() => {
    if (!historyLoaded) return;
    try {
      localStorage.setItem(STORAGE_KEY(configId), JSON.stringify({
        messages,
        chatHistory,
        lastSpec,
        urlInputs: urlInputs.filter(u => u.trim()),
      }));
    } catch { /* ignore quota errors */ }
  }, [messages, chatHistory, lastSpec, urlInputs, configId, historyLoaded]);

  function clearHistory() {
    const fields = initialSpec && initialSpec.fields ? Object.keys(initialSpec.fields as object) : [];
    const sysMsg: DisplayMessage = {
      id: `sys-${nextMsgId++}`,
      role: 'system',
      content: fields.length > 0
        ? `Current config "${configName}" has ${fields.length} field${fields.length !== 1 ? 's' : ''}: ${fields.join(', ')}. Ask me to refine it!`
        : 'Provide URLs and describe what data to extract. I\'ll generate an extraction spec for you.',
    };
    setMessages([sysMsg]);
    setChatHistory([]);
    setLastSpec(initialSpec);
    setUrlInputs(['']);
    setError('');
    try {
      localStorage.removeItem(STORAGE_KEY(configId));
    } catch { /* ignore */ }
  }

  function addUrlInput() {
    if (urlInputs.length < 5) {
      setUrlInputs([...urlInputs, '']);
    }
  }

  function removeUrlInput(index: number) {
    if (urlInputs.length > 1) {
      setUrlInputs(urlInputs.filter((_, i) => i !== index));
    }
  }

  function updateUrlInput(index: number, value: string) {
    const updated = [...urlInputs];
    updated[index] = value;
    setUrlInputs(updated);
  }

  async function handleSend() {
    const validUrls = urlInputs.map(u => u.trim()).filter(u => u.length > 0);
    if (validUrls.length === 0 && !inputText.trim()) return;
    if (validUrls.length === 0) {
      setError('Provide at least one URL');
      return;
    }

    const userContent = inputText.trim() || 'Generate extraction spec for this page';
    const userMsg: DisplayMessage = {
      id: `user-${nextMsgId++}`,
      role: 'user',
      content: userContent + (validUrls.length > 0 ? `\n\nURLs: ${validUrls.join(', ')}` : ''),
    };

    const newChatHistory: ChatMessage[] = [
      ...chatHistory,
      { role: 'user', content: userContent },
    ];

    setMessages(prev => [...prev, userMsg]);
    setInputText('');
    setIsLoading(true);
    setError('');

    try {
      const currentSpec = lastSpec && Object.keys(lastSpec).length > 0 ? lastSpec : null;
      const res = await aiApi.refineSpecChat({
        messages: newChatHistory,
        urls: validUrls,
        current_spec: currentSpec,
        scraper_profile: scraperProfile,
        headers: headers || undefined,
        cookies: cookies || undefined,
      });

      const assistantMsg: DisplayMessage = {
        id: `asst-${nextMsgId++}`,
        role: 'assistant',
        content: res.assistant_message,
        spec: res.extraction_spec,
        urlContexts: res.url_contexts,
      };

      setMessages(prev => [...prev, assistantMsg]);
      setLastSpec(res.extraction_spec);
      setChatHistory([
        ...newChatHistory,
        { role: 'assistant', content: res.assistant_message },
      ]);

      onApplySpec(res.extraction_spec);
      toast.success('Spec applied to form');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI refinement failed');
    }

    setIsLoading(false);
  }

  async function handleVerify(url: string) {
    if (!lastSpec || isVerifying) return;
    setIsVerifying(true);

    const verifyMsg: DisplayMessage = {
      id: `sys-${nextMsgId++}`,
      role: 'system',
      content: `Verifying spec on ${url}...`,
    };
    setMessages(prev => [...prev, verifyMsg]);

    try {
      const result = await onVerifySpec(url, lastSpec);
      const resultMsg: DisplayMessage = {
        id: `asst-${nextMsgId++}`,
        role: 'assistant',
        content: result.valid
          ? `All ${result.total_fields} fields matched with clean values.`
          : `${result.passed_fields}/${result.total_fields} fields passed. Failed: ${result.failed_fields.join(', ')}`,
        verifyResult: result,
      };
      setMessages(prev => [...prev, resultMsg]);

      if (result.refined_spec) {
        setLastSpec(result.refined_spec);
        onApplySpec(result.refined_spec);
        toast.success('Refined spec applied');
      }
    } catch (err) {
      const errorMsg: DisplayMessage = {
        id: `asst-${nextMsgId++}`,
        role: 'assistant',
        content: `Verification failed: ${err instanceof Error ? err.message : 'Unknown error'}`,
      };
      setMessages(prev => [...prev, errorMsg]);
    }

    setIsVerifying(false);
  }

  async function handleSanitize(url: string, description?: string) {
    if (!lastSpec || isSanitizing) return;
    setIsSanitizing(true);

    const sanitizeMsg: DisplayMessage = {
      id: `sys-${nextMsgId++}`,
      role: 'system',
      content: 'Generating sanitizer suggestions...',
    };
    setMessages(prev => [...prev, sanitizeMsg]);

    try {
      const result = await onSuggestSanitizer(url, lastSpec, description);
      const resultMsg: DisplayMessage = {
        id: `asst-${nextMsgId++}`,
        role: 'assistant',
        content: `Suggested ${result.rules.length} sanitizer rule${result.rules.length !== 1 ? 's' : ''}.`,
        sanitizerResult: { rules: result.rules as any, sample_before: result.sample_before, sample_after: result.sample_after },
      };
      setMessages(prev => [...prev, resultMsg]);
    } catch (err) {
      const errorMsg: DisplayMessage = {
        id: `asst-${nextMsgId++}`,
        role: 'assistant',
        content: `Sanitizer generation failed: ${err instanceof Error ? err.message : 'Unknown error'}`,
      };
      setMessages(prev => [...prev, errorMsg]);
    }

    setIsSanitizing(false);
  }

  function handleApplySpec(spec: Record<string, unknown>) {
    setLastSpec(spec);
    onApplySpec(spec);
    setMessages(prev => prev.map(m =>
      m.spec === spec ? { ...m, applied: true } : m
    ));
    toast.success('Spec applied to form');
  }

  const busy = isLoading || isVerifying || isSanitizing;

  return (
    <div className="chat-panel">
      <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '0 16px', marginTop: 8 }}>
        <button
          type="button"
          onClick={clearHistory}
          style={{ background: 'none', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '2px 8px', fontSize: '0.7rem', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <IconTrash size={11} /> Clear
        </button>
      </div>
      <div className="chat-messages" ref={messagesContainerRef}>
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-message chat-message--${msg.role}`}>
            {msg.role === 'system' && (
              <div className="chat-message-content chat-message-content--system">
                {msg.content}
              </div>
            )}
            {msg.role === 'user' && (
              <div className="chat-message-content chat-message-content--user">
                {msg.content.split('\n').map((line, i) => (
                  <span key={i}>{line}<br /></span>
                ))}
              </div>
            )}
            {msg.role === 'assistant' && (
              <div className="chat-message-content chat-message-content--assistant">
                <p style={{ margin: 0, marginBottom: 8 }}>{msg.content}</p>

                {msg.spec && (
                  <details className="chat-spec-preview">
                    <summary style={{ fontSize: '0.75rem', color: 'var(--accent-primary)', cursor: 'pointer', marginBottom: 6 }}>
                      Spec ({Object.keys(msg.spec.fields || {}).length} fields)
                    </summary>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', fontSize: '0.75rem', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr>
                            <th style={{ textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>Field</th>
                            <th style={{ textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>Selector</th>
                            <th style={{ textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(msg.spec.fields || {}).map(([name, field]: [string, any]) => (
                            <tr key={name}>
                              <td style={{ padding: '4px 8px', color: 'var(--text-primary)', fontWeight: 500 }}>{name}</td>
                              <td style={{ padding: '4px 8px', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>{field?.selector}</td>
                              <td style={{ padding: '4px 8px', fontSize: '0.7rem' }}>
                                <span style={{ padding: '2px 6px', borderRadius: 4, background: 'var(--bg-primary)', color: 'var(--text-secondary)' }}>{field?.type || 'css'}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {!msg.applied && !busy && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => handleApplySpec(msg.spec!)}
                        style={{ marginTop: 8, fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 4 }}
                      >
                        <IconCheck size={12} /> Apply to form
                      </button>
                    )}
                    {msg.applied && (
                      <span style={{ marginTop: 8, fontSize: '0.75rem', color: 'var(--status-success)', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <IconCheck size={12} /> Applied
                      </span>
                    )}
                  </details>
                )}

                {msg.verifyResult && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: msg.verifyResult.valid ? 'var(--status-success)' : 'var(--status-failed)' }}>
                      {msg.verifyResult.passed_fields}/{msg.verifyResult.total_fields} fields passed
                    </div>
                    {msg.verifyResult.field_results.map((fr) => (
                      <div key={fr.field_name} style={{ padding: '4px 0', fontSize: '0.75rem', borderBottom: '1px solid var(--border-color)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ color: fr.matched && fr.value_quality === 'good' ? 'var(--status-success)' : fr.matched ? '#ff9800' : 'var(--status-failed)' }}>
                            {fr.value_quality === 'good' ? '✓' : fr.value_quality === 'html' ? '⚠' : '✗'}
                          </span>
                          <span style={{ fontWeight: 500, minWidth: 80 }}>{fr.field_name}</span>
                          <code style={{ color: 'var(--text-muted)', fontSize: '0.7rem', flex: 1, wordBreak: 'break-all' }}>{fr.selector}</code>
                        </div>
                        {fr.sample_value && (
                          <div style={{ marginLeft: 22, marginTop: 2, padding: '4px 8px', background: 'var(--bg-primary)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--text-muted)', wordBreak: 'break-all', maxHeight: 60, overflow: 'auto' }}>
                            {fr.sample_value}
                          </div>
                        )}
                      </div>
                    ))}
                    {msg.verifyResult.extracted_data && Object.keys(msg.verifyResult.extracted_data).length > 0 && (
                      <details style={{ marginTop: 8 }}>
                        <summary style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', cursor: 'pointer', marginBottom: 4 }}>
                          Extracted data
                        </summary>
                        <pre style={{ background: 'var(--bg-primary)', padding: 10, borderRadius: 'var(--radius-sm)', fontSize: '0.7rem', fontFamily: 'var(--font-mono)', overflow: 'auto', maxHeight: 200, color: 'var(--text-secondary)' }}>
                          {JSON.stringify(msg.verifyResult.extracted_data, null, 2)}
                        </pre>
                      </details>
                    )}
                    {msg.verifyResult.refined_spec && (
                      <div style={{ marginTop: 6, fontSize: '0.75rem', color: 'var(--status-success)' }}>
                        Auto-refined ({msg.verifyResult.iterations_performed} iteration{msg.verifyResult.iterations_performed !== 1 ? 's' : ''})
                        {msg.verifyResult.model_used && ` using ${msg.verifyResult.model_used}`}
                      </div>
                    )}
                  </div>
                )}

                {msg.sanitizerResult && (
                  <div style={{ marginTop: 8 }}>
                    {msg.sanitizerResult.rules.map((rule, i) => (
                      <div key={i} style={{ padding: '4px 8px', marginBottom: 3, background: 'var(--bg-primary)', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem' }}>
                        <span style={{ color: 'var(--accent-primary)', fontWeight: 500 }}>{rule.field}</span>
                        {' → '}
                        {rule.transforms.map((t, j) => (
                          <span key={j} style={{ color: 'var(--text-muted)' }}>
                            {j > 0 && ' → '}{t.type}
                            {t.type === 'regex_replace' && <span>({t.pattern})</span>}
                          </span>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {msg.spec && !msg.verifyResult && !msg.sanitizerResult && (
                  <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                    {urlInputs.filter(u => u.trim()).length > 0 && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => handleVerify(urlInputs.filter(u => u.trim())[0])}
                        disabled={busy}
                        style={{ fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: 4 }}
                      >
                        {isVerifying ? (
                          <><div className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Verifying...</>
                        ) : (
                          <><IconRefresh size={11} /> Verify on URL</>
                        )}
                      </button>
                    )}
                    {urlInputs.filter(u => u.trim()).length > 0 && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => handleSanitize(urlInputs.filter(u => u.trim())[0])}
                        disabled={busy}
                        style={{ fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: 4 }}
                      >
                        {isSanitizing ? (
                          <><div className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Sanitizing...</>
                        ) : (
                          <><IconSparkle size={11} /> Suggest Sanitizer</>
                        )}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="chat-message chat-message--assistant">
            <div className="chat-message-content chat-message-content--assistant">
              <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
              <span style={{ marginLeft: 8, fontSize: '0.8rem', color: 'var(--text-muted)' }}>Analyzing...</span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div style={{ padding: '8px 12px', color: 'var(--status-failed)', fontSize: '0.8rem' }}>
          {error}
        </div>
      )}

      <div className="chat-url-inputs">
        {urlInputs.map((url, i) => (
          <div key={i} style={{ display: 'flex', gap: 4 }}>
            <input
              type="url"
              className="form-input"
              placeholder={i === 0 ? 'https://example.com/product/123' : 'Additional URL'}
              value={url}
              onChange={(e) => updateUrlInput(i, e.target.value)}
              style={{ flex: 1, fontSize: '0.8rem' }}
            />
            {urlInputs.length > 1 && (
              <button
                type="button"
                onClick={() => removeUrlInput(i)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '0 4px' }}
              >
                <IconX size={14} />
              </button>
            )}
          </div>
        ))}
        {urlInputs.length < 5 && (
          <button
            type="button"
            onClick={addUrlInput}
            style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: '1px dashed var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.75rem' }}
          >
            <IconPlus size={12} /> Add URL
          </button>
        )}
      </div>

      <div className="chat-input-area">
        <textarea
          className="form-input"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Describe what to extract or what needs fixing..."
          rows={2}
          style={{ resize: 'vertical', fontSize: '0.85rem' }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSend}
          disabled={isLoading || urlInputs.every(u => !u.trim())}
          style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', justifyContent: 'center', marginTop: 8 }}
        >
          {isLoading ? (
            <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Refining...</>
          ) : (
            <><IconSparkle size={14} /> Refine</>
          )}
        </button>
      </div>
    </div>
  );
}