import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

/** Charge une ressource et permet de la recharger. */
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const reload = useCallback(async () => {
    try {
      const value = await loaderRef.current();
      setData(value);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "Une erreur est survenue."));
    }
  }, []);

  useEffect(() => {
    setData(null);
    setError(null);
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, reload, setData };
}

/** Recharge régulièrement tant que `active` est vrai (génération en cours, par exemple). */
export function usePoll(reload: () => Promise<void> | void, active: boolean, ms = 2500) {
  const ref = useRef(reload);
  ref.current = reload;
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => void ref.current(), ms);
    return () => window.clearInterval(id);
  }, [active, ms]);
}
