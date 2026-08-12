export const DEFAULT_WORKSPACE_ID = "ws_riverlight";

export function requireWorkspace(request: Request) {
  const workspaceId = request.headers.get("x-workspace-id") || DEFAULT_WORKSPACE_ID;
  if (workspaceId !== DEFAULT_WORKSPACE_ID) throw new WorkspaceError("Workspace access denied", 403);
  return workspaceId;
}

export class WorkspaceError extends Error {
  constructor(message: string, public status = 400) { super(message); }
}

export function jsonError(error: unknown) {
  const status = error instanceof WorkspaceError ? error.status : 500;
  return Response.json({ error: error instanceof Error ? error.message : "Unexpected error" }, { status });
}

export function requiredString(value: unknown, field: string, max = 5000) {
  if (typeof value !== "string" || !value.trim() || value.length > max) throw new WorkspaceError(`${field} is required`);
  return value.trim();
}

export function optionalTimestamp(value: unknown, field: string) {
  if (value === undefined || value === null || value === "") return null;
  const time = new Date(String(value)).getTime();
  if (!Number.isFinite(time)) throw new WorkspaceError(`${field} must be a valid date`);
  return time;
}
