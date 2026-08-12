import { env } from "cloudflare:workers";
import { jsonError, optionalTimestamp, requireWorkspace, requiredString, WorkspaceError } from "../../../lib/workspace";

export async function GET(request: Request) {
  try {
    const workspaceId = requireWorkspace(request); const url = new URL(request.url); const status = url.searchParams.get("status");
    const query = status ? env.DB.prepare("SELECT * FROM posts WHERE workspace_id=? AND status=? ORDER BY COALESCE(proposed_at,created_at)").bind(workspaceId,status) : env.DB.prepare("SELECT * FROM posts WHERE workspace_id=? ORDER BY COALESCE(proposed_at,created_at)").bind(workspaceId);
    return Response.json({ posts: (await query.all()).results });
  } catch (error) { return jsonError(error); }
}

export async function POST(request: Request) {
  try {
    const workspaceId = requireWorkspace(request); const body = await request.json() as Record<string,unknown>; const now=Date.now();
    const id=crypto.randomUUID(); const caption=requiredString(body.caption,"caption"); const proposedAt=optionalTimestamp(body.proposedAt,"proposedAt");
    const accountId=typeof body.accountId === "string" ? body.accountId : "acct_instagram";
    const account=await env.DB.prepare("SELECT id FROM social_accounts WHERE id=? AND workspace_id=?").bind(accountId,workspaceId).first();
    if(!account) throw new WorkspaceError("Account not found",404);
    await env.DB.batch([
      env.DB.prepare("INSERT INTO posts (id,workspace_id,account_id,campaign_id,event_id,status,proposed_at,caption,content_type,tone,cta,media_type,historical,created_at,updated_at) VALUES (?,?,?,?,?,'draft',?,?,?,?,?,?,0,?,?)").bind(id,workspaceId,accountId,body.campaignId||null,body.eventId||null,proposedAt,caption,body.contentType||"Announcement",body.tone||"Conversational",body.cta||"Learn more",body.mediaType||"Text only",now,now),
      env.DB.prepare("INSERT INTO approvals (id,workspace_id,post_id,status,requested_by,requested_at) VALUES (?,?,?,'pending','user',?)").bind(crypto.randomUUID(),workspaceId,id,now),
    ]);
    return Response.json({ id, status:"draft", approvalStatus:"pending" },{status:201});
  } catch(error){return jsonError(error)}
}
