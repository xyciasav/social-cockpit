import { assistantTools, providerTools, SYSTEM_POLICY, type ToolContext } from "../../../../lib/ai/tools";
import { executeTool } from "../../../../lib/ai/execute";
import { env } from "cloudflare:workers";

type ToolCall = { id: string; type?: "function"; function: { name: string; arguments: string } };
type Message = { role: "user" | "assistant" | "system" | "tool"; content: string; tool_call_id?: string; tool_calls?: ToolCall[] };

export async function POST(request: Request) {
  try {
    const body = await request.json() as { message?: string; workspaceId?: string; currentView?: string; campaignId?: string; useAnalytics?: boolean };
    if (!body.message || typeof body.message !== "string" || body.message.length > 8000) return Response.json({ error: "A valid message is required." }, { status: 400 });
    if (body.workspaceId !== "ws_riverlight") return Response.json({ error: "Workspace access denied." }, { status: 403 });
    const context: ToolContext = { workspaceId: body.workspaceId, currentView: body.currentView || "Overview", campaignId: body.campaignId };
    const settings=await env.DB.prepare("SELECT * FROM workspace_settings WHERE workspace_id=?").bind(context.workspaceId).first<Record<string,unknown>>();
    const baseUrl = String(settings?.llm_base_url || process.env.LLM_BASE_URL || "").replace(/\/$/, "").replace(/\/v1$/i,"");
    const model = String(settings?.llm_model || process.env.LLM_MODEL || "");
    if (!baseUrl || !model) return Response.json({ error:"Configure LLM_BASE_URL and LLM_MODEL to use the assistant. No data was changed." },{status:503});

    const resources=(await env.DB.prepare("SELECT type,title,content,url,filename FROM resources WHERE workspace_id=? ORDER BY created_at DESC LIMIT 50").bind(context.workspaceId).all()).results;
    const messages: Message[] = [{ role: "system", content: `${SYSTEM_POLICY}\nYou help the user immediately. When asked to generate posts, write complete publish-ready captions and call create_post_drafts with those exact captions. Spread requested quantities evenly over the requested number of days. Do not create placeholders.\nORGANIZATION INFO:\n${String(settings?.organization_info||"")}\nVOICE AND TONE:\n${String(settings?.tone_prompt||"")}\nSAVED LIBRARY ITEMS:\n${JSON.stringify(resources)}\nCurrent view: ${context.currentView}.` }, { role: "user", content: body.message }];
    const activity: unknown[] = [];
    for (let turn = 0; turn < 5; turn++) {
      const response = await fetch(`${baseUrl}/v1/chat/completions`, { method: "POST", headers: { "content-type": "application/json", ...(process.env.LLM_API_KEY ? { authorization: `Bearer ${process.env.LLM_API_KEY}` } : {}) }, body: JSON.stringify({ model, temperature: Number(settings?.temperature ?? process.env.LLM_TEMPERATURE ?? 0.4), max_tokens: Number(settings?.max_tokens ?? process.env.LLM_MAX_TOKENS ?? 2000), messages, tools: providerTools, tool_choice: "auto" }) });
      const raw=await response.text();
      if (!response.ok) throw new Error(`LM Studio returned ${response.status}: ${raw.slice(0,300)}`);
      let data:{ choices?: Array<{ message?: { content?: string; tool_calls?: ToolCall[] } }> };try{data=JSON.parse(raw)}catch{throw new Error(`LM Studio returned non-JSON: ${raw.slice(0,300)}`)}
      const answer = data.choices?.[0]?.message;
      if (!answer?.tool_calls?.length) return Response.json({ message: answer?.content || "I couldn't complete that request.", activity, provider: model });
      messages.push({ role: "assistant", content: answer.content || "", tool_calls: answer.tool_calls });
      for (const call of answer.tool_calls) {
        let args: Record<string, unknown>;
        try { args = JSON.parse(call.function.arguments); } catch { throw new Error("Provider returned invalid tool arguments"); }
        const result = await executeTool(call.function.name, args, context);
        activity.push({ tool: call.function.name, kind: assistantTools.find(t => t.name === call.function.name)?.kind, result });
        messages.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(result) });
      }
    }
    return Response.json({ error: "Tool loop limit reached." }, { status: 422 });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Assistant failed." }, { status: 500 });
  }
}
