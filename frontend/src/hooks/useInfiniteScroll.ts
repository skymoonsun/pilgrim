import { useEffect, useRef, useCallback, useState } from 'react';

/**
 * Hook for infinite scroll pagination.
 *
 * Usage:
 *   const { items, total, loading, loadingMore, sentinelRef, reset } = useInfiniteScroll({
 *     fetchPage: (skip, limit) => api.list(skip, limit),
 *     pageSize: 50,
 *   });
 */
export function useInfiniteScroll<T>({
  fetchPage,
  pageSize = 50,
  deps = [],
}: {
  fetchPage: (skip: number, limit: number) => Promise<{ items: T[]; total: number }>;
  pageSize?: number;
  deps?: unknown[];
}): {
  items: T[];
  total: number;
  loading: boolean;
  loadingMore: boolean;
  sentinelRef: (node: HTMLElement | null) => void;
  reset: () => void;
} {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const skipRef = useRef(0);
  const hasMoreRef = useRef(true);
  const loadingRef = useRef(true);
  const sentinelNodeRef = useRef<HTMLElement | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  const loadInitial = useCallback(async () => {
    loadingRef.current = true;
    setLoading(true);
    setItems([]);
    skipRef.current = 0;
    hasMoreRef.current = true;
    try {
      const res = await fetchPage(0, pageSize);
      setItems(res.items);
      setTotal(res.total);
      skipRef.current = res.items.length;
      hasMoreRef.current = res.items.length < res.total;
    } catch (err) {
      console.error('Failed to load:', err);
    }
    loadingRef.current = false;
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageSize, ...deps]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMoreRef.current || loadingRef.current) return;
    setLoadingMore(true);
    try {
      const res = await fetchPage(skipRef.current, pageSize);
      setItems((prev) => [...prev, ...res.items]);
      setTotal(res.total);
      skipRef.current += res.items.length;
      hasMoreRef.current = skipRef.current < res.total;
    } catch (err) {
      console.error('Failed to load more:', err);
    }
    setLoadingMore(false);
  }, [fetchPage, pageSize, loadingMore]);

  // Initial load + reset on deps change
  useEffect(() => {
    loadInitial();
  }, [loadInitial]);

  // IntersectionObserver for infinite scroll
  useEffect(() => {
    if (observerRef.current) observerRef.current.disconnect();

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMoreRef.current && !loadingMore) {
          loadMore();
        }
      },
      { rootMargin: '200px' },
    );

    if (sentinelNodeRef.current) {
      observerRef.current.observe(sentinelNodeRef.current);
    }

    return () => observerRef.current?.disconnect();
  }, [loadMore, loadingMore]);

  // Callback ref to attach sentinel element
  const sentinelRef = useCallback((node: HTMLElement | null) => {
    sentinelNodeRef.current = node;
    if (observerRef.current) {
      observerRef.current.disconnect();
      if (node) observerRef.current.observe(node);
    }
  }, []);

  const reset = useCallback(() => {
    loadInitial();
  }, [loadInitial]);

  return { items, total, loading, loadingMore, sentinelRef, reset };
}