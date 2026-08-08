"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "./api";
import { useAuth } from "./auth";
import { getActiveWorkspace, setActiveWorkspace } from "./tokens";
import type { Role, Workspace } from "./types";

type WorkspaceState = {
  workspaces: Workspace[];
  active: Workspace | null;
  role: Role | null;
  ready: boolean;
  setActive: (id: string) => void;
  refresh: () => Promise<Workspace[]>;
};

const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const load = useCallback(async (): Promise<Workspace[]> => {
    const list = await api.listWorkspaces();
    setWorkspaces(list);
    // Keep the stored active workspace if it's still one we belong to.
    const stored = getActiveWorkspace();
    const chosen = list.find((w) => w.id === stored) ?? list[0] ?? null;
    setActiveId(chosen?.id ?? null);
    setActiveWorkspace(chosen?.id ?? null);
    return list;
  }, []);

  useEffect(() => {
    if (!auth.ready) return;
    if (!auth.isAuthenticated) {
      setWorkspaces([]);
      setActiveId(null);
      setReady(true);
      return;
    }
    load()
      .catch(() => setWorkspaces([]))
      .finally(() => setReady(true));
  }, [auth.ready, auth.isAuthenticated, load]);

  const setActive = useCallback((id: string) => {
    setActiveId(id);
    setActiveWorkspace(id);
  }, []);

  const active = useMemo(
    () => workspaces.find((w) => w.id === activeId) ?? null,
    [workspaces, activeId],
  );

  const value = useMemo<WorkspaceState>(
    () => ({ workspaces, active, role: active?.role ?? null, ready, setActive, refresh: load }),
    [workspaces, active, ready, setActive, load],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceState {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within <WorkspaceProvider>");
  return ctx;
}
