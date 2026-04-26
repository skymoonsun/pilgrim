import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';
import { useEffect, useState, useCallback } from 'react';
import { IconCheck, IconX } from '../icons/Icons';

type ToastType = 'success' | 'error' | 'info';

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
  exiting?: boolean;
}

let container: HTMLDivElement | null = null;
let root: ReturnType<typeof createRoot> | null = null;
let nextId = 0;
let setToastsCallback: ((toasts: ToastItem[]) => void) | null = null;
let activeToasts: ToastItem[] = [];

function getRoot() {
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-root';
    document.body.appendChild(container);
    root = createRoot(container);
  }
  return root!;
}

function renderToasts() {
  const r = getRoot();
  r.render(<ToastContainer toasts={activeToasts} onDismiss={dismissToast} />);
}

function addToast(type: ToastType, message: string) {
  const id = nextId++;
  activeToasts = [...activeToasts, { id, type, message }];
  setToastsCallback?.(activeToasts);
  renderToasts();
  setTimeout(() => dismissStart(id), 4000);
}

function dismissStart(id: number) {
  const idx = activeToasts.findIndex((t) => t.id === id);
  if (idx === -1) return;
  if (activeToasts[idx].exiting) return;
  activeToasts = activeToasts.map((t) => (t.id === id ? { ...t, exiting: true } : t));
  setToastsCallback?.(activeToasts);
  renderToasts();
  setTimeout(() => {
    activeToasts = activeToasts.filter((t) => t.id !== id);
    setToastsCallback?.(activeToasts);
    renderToasts();
  }, 300);
}

function dismissToast(id: number) {
  dismissStart(id);
}

export const toast = {
  success(message: string) { addToast('success', message); },
  error(message: string) { addToast('error', message); },
  info(message: string) { addToast('info', message); },
};

function ToastContainer({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: number) => void }) {
  if (toasts.length === 0) return null;

  return createPortal(
    <div className="toast-container">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast toast--${t.type}${t.exiting ? ' toast--exit' : ''}`}
          onClick={() => onDismiss(t.id)}
          role="alert"
        >
          <span className={`toast-icon toast-icon--${t.type}`}>
            {t.type === 'success' && <IconCheck size={16} />}
            {t.type === 'error' && <IconX size={16} />}
            {t.type === 'info' && <InfoIcon size={16} />}
          </span>
          <span className="toast-message">{t.message}</span>
        </div>
      ))}
    </div>,
    document.body
  );
}

function InfoIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}