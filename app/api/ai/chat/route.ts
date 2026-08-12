import { assistantTools, providerTools, SYSTEM_POLICY, type ToolContext } from "../../../../lib/ai/tools";
import { executeTool } from "../../../../lib/ai/execute";

type ToolCall = { id: string; type?: "function"; function: { name: string; arguments: string } };
type Message = { role: "user" | "assistant" | "system" | "tool"; content: string; tool_call_id?: string; tool_calls?: ToolCall[] };

export async function POST(request: Request) {
  try {
    const body = await request.json() as { message?: string; workspaceId?: string; currentView?: string; campaignId?: string; useAnalytics?: boolean };
    if (!body.message || typeof body.message !== "string" || body.message.length > 8000) return Response.json({ error: "A valid message is required." }, { status: 400 });
    if (body.workspaceId !== "ws_riverlight") return Response.json({ error: "Workspace access denied." }, { status: 403 });
    const context: ToolContext = { workspaceId: body.workspaceId, currentView: body.currentView || "Overview", campaignId: body.campaignId };
    const baseUrl = (process.env.LLM_BASE_URL || "").replace(/\/$/, "");
    const model = process.env.LLM_MODEL || "";
    if (!baseUrl || !model) return Response.json({ error:"Configure LLM_BASE_URL and LLM_MODEL to use the assistant. No data was changed." },{status:503});

    const messages: Message[] = [{ role: "system", content: `${SYSTEM_POLICY}\nYou help the user immediately. When asked to generate posts, write complete publish-ready captions and call create_post_drafts with those exact captions. Do not create placeholders. Current view: ${context.currentView}. Analytics-aware generation: ${body.useAnalytics !== false ? "enabled" : "disabled"}.` }, { role: "user", content: body.message }];
    const activity: unknown[] = [];
    for (let turn = 0; turn < 5; turn++) {
      const response = await fetch(`${baseUrl}/v1/chat/completions`, { method: "POST", headers: { "content-type": "application/json", ...(process.env.LLM_API_KEY ? { authorization: `Bearer ${process.env.LLM_API_KEY}` } : {}) }, body: JSON.stringify({ model, temperature: Number(process.env.LLM_TEMPERATURE || 0.4), max_tokens: Number(process.env.LLM_MAX_TOKENS || 1200), messages, tools: providerTools, tool_choice: "auto" }) });
      if (!response.ok) throw new Error(`LLM provider returned ${response.status}`);
      const data = await response.json() as { choices?: Array<{ message?: { content?: string; tool_calls?: ToolCall[] } }> };
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
