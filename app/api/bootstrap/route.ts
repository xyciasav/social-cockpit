import { env } from "cloudflare:workers";
import { jsonError, requireWorkspace } from "../../../lib/workspace";

const schema = [
  `CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS social_accounts (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, platform TEXT NOT NULL, name TEXT NOT NULL, followers INTEGER)`,
  `CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL, starts_at INTEGER, ends_at INTEGER)`,
  `CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, campaign_id TEXT, name TEXT NOT NULL, description TEXT, location TEXT, starts_at INTEGER NOT NULL, ends_at INTEGER, url TEXT, created_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, account_id TEXT NOT NULL, campaign_id TEXT, event_id TEXT, provider_post_id TEXT, status TEXT NOT NULL DEFAULT 'draft', proposed_at INTEGER, scheduled_at INTEGER, published_at INTEGER, caption TEXT, permalink TEXT, content_type TEXT, tone TEXT, cta TEXT, media_type TEXT, historical INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, post_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'pending', requested_by TEXT NOT NULL, requested_at INTEGER NOT NULL, decided_at INTEGER, decided_by TEXT, note TEXT)`,
  `CREATE TABLE IF NOT EXISTS resources (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, type TEXT NOT NULL, title TEXT NOT NULL, content TEXT, url TEXT, object_key TEXT, filename TEXT, mime_type TEXT, created_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS workspace_settings (workspace_id TEXT PRIMARY KEY, tone_prompt TEXT NOT NULL DEFAULT '', organization_info TEXT NOT NULL DEFAULT '', llm_base_url TEXT NOT NULL DEFAULT 'http://host.docker.internal:1234', llm_model TEXT NOT NULL DEFAULT 'qwen', temperature REAL NOT NULL DEFAULT 0.4, max_tokens INTEGER NOT NULL DEFAULT 2000, updated_at INTEGER NOT NULL)`,
];

export async function POST(request: Request) {
  try {
    const workspaceId = requireWorkspace(request); const now = Date.now();
    await env.DB.batch(schema.map(sql => env.DB.prepare(sql)));
    await env.DB.batch([
      env.DB.prepare("INSERT OR IGNORE INTO workspaces (id,name,created_at) VALUES (?,?,?)").bind(workspaceId,"Riverlight HQ",now),
      env.DB.prepare("INSERT OR IGNORE INTO social_accounts (id,workspace_id,platform,name,followers) VALUES (?,?,?,?,?)").bind("acct_instagram",workspaceId,"Instagram","@riverlighthq",8426),
      env.DB.prepare("INSERT OR IGNORE INTO social_accounts (id,workspace_id,platform,name,followers) VALUES (?,?,?,?,?)").bind("acct_facebook",workspaceId,"Facebook","Riverlight HQ",12180),
      env.DB.prepare("INSERT OR IGNORE INTO workspace_settings (workspace_id,updated_at) VALUES (?,?)").bind(workspaceId,now),
    ]);
    return Response.json({ workspaceId, initialized: true });
  } catch (error) { return jsonError(error); }
}
