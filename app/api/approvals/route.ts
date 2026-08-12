import { env } from "cloudflare:workers";
import { jsonError, requireWorkspace } from "../../../lib/workspace";

export async function GET(request: Request) {
  try { const workspaceId=requireWorkspace(request); const rows=await env.DB.prepare("SELECT a.id approval_id,a.status approval_status,a.requested_at,p.* FROM approvals a JOIN posts p ON p.id=a.post_id AND p.workspace_id=a.workspace_id WHERE a.workspace_id=? ORDER BY a.requested_at DESC").bind(workspaceId).all(); return Response.json({approvals:rows.results}); } catch(error){return jsonError(error)}
}

export async function PATCH(request: Request) {
  try { const workspaceId=requireWorkspace(request); const body=await request.json() as {postId?:string;decision?:string;note?:string}; if(!body.postId||!["approved","rejected"].includes(body.decision||"")) return Response.json({error:"postId and valid decision are required"},{status:400});
    const post=await env.DB.prepare("SELECT status FROM posts WHERE id=? AND workspace_id=?").bind(body.postId,workspaceId).first<{status:string}>(); if(!post) return Response.json({error:"Post not found"},{status:404}); if(post.status!=="draft") return Response.json({error:"Only drafts can be reviewed"},{status:409});
    const now=Date.now(); await env.DB.batch([env.DB.prepare("UPDATE approvals SET status=?,decided_at=?,decided_by='user',note=? WHERE post_id=? AND workspace_id=?").bind(body.decision,now,body.note||null,body.postId,workspaceId),env.DB.prepare("UPDATE posts SET status=?,updated_at=? WHERE id=? AND workspace_id=?").bind(body.decision,now,body.postId,workspaceId)]); return Response.json({postId:body.postId,status:body.decision});
  } catch(error){return jsonError(error)}
}
