import { createRoot } from 'react-dom/client';
import { useEffect, useRef } from 'react';
import { IconAlertTriangle } from '../icons/Icons';

interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}

let container: HTMLDivElement | null = null;
let root: ReturnType<typeof createRoot> | null = null;

function getRoot() {
  if (!container) {
    container = document.createElement('div');
    container.id = 'confirm-dialog-root';
    document.body.appendChild(container);
    root = createRoot(container);
  }
  return root!;
}

export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    const r = getRoot();

    function handleConfirm() {
      r.render(null);
      resolve(true);
    }

    function handleCancel() {
      r.render(null);
      resolve(false);
    }

    r.render(<ConfirmDialogInner {...options} onConfirm={handleConfirm} onCancel={handleCancel} />);
  });
}

function ConfirmDialogInner({
  title,
  message,
  confirmLabel,
  cancelLabel,
  danger,
  onConfirm,
  onCancel,
}: ConfirmOptions & { onConfirm: () => void; onCancel: () => void }) {
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onCancel]);

  return (
    <div
      ref={backdropRef}
      className="overlay-backdrop"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
        {danger && (
          <div className="confirm-dialog-icon danger">
            <IconAlertTriangle size={22} />
          </div>
        )}
        <h3 className="confirm-dialog-title">{title}</h3>
        <p className="confirm-dialog-message">{message}</p>
        <div className="confirm-dialog-actions">
          <button className="btn btn-secondary" onClick={onCancel}>
            {cancelLabel ?? 'Cancel'}
          </button>
          <button
            className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm}
          >
            {confirmLabel ?? (danger ? 'Delete' : 'Confirm')}
          </button>
        </div>
      </div>
    </div>
  );
}