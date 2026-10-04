// Tiny observable store: panels and map subscribe; nothing else holds UI state.
type Listener<T> = (s: T, prev: T) => void;

export interface UIState {
  selectedId: string | null;
  tab: "connected" | "rejected" | "ranked";
}

export function createStore<T extends object>(initial: T) {
  let state = initial;
  const listeners = new Set<Listener<T>>();
  return {
    get: () => state,
    set(patch: Partial<T>) {
      const prev = state;
      state = { ...state, ...patch };
      listeners.forEach((l) => l(state, prev));
    },
    subscribe(l: Listener<T>) {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
}

export const ui = createStore<UIState>({ selectedId: null, tab: "connected" });
