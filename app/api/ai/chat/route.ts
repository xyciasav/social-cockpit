import { assistantTools, executeDemoTool, providerTools, SYSTEM_POLICY, type ToolContext } from "../../../../lib/ai/tools";

type Message = { role: "user" | "assistant" | "system" | "tool"; content: string; tool_call_id?: string };

export async function POST(request: Request) {
  try {
    const body = await request.json() as { message?: string; workspaceId?: string; currentView?: string; campaignId?: string; useAnalytics?: boolean };
    if (!body.message || typeof body.message !== "string" || body.message.length > 8000) return Response.json({ error: "A valid message is required." }, { status: 400 });
    if (body.workspaceId !== "ws_riverlight") return Response.json({ error: "Workspace access denied." }, { status: 403 });
    const context: ToolContext = { workspaceId: body.workspaceId, currentView: body.currentView || "Overview", campaignId: body.campaignId };
    const baseUrl = (process.env.LLM_BASE_URL || "").replace(/\/$/, "");
    const model = process.env.LLM_MODEL || "";
    if (!baseUrl || !model) return Response.json(demoAssistant(body.message, context, body.useAnalytics !== false));

    const messages: Message[] = [{ role: "system", content: `${SYSTEM_POLICY}\nCurrent view: ${context.currentView}. Analytics-aware generation: ${body.useAnalytics !== false ? "enabled" : "disabled"}.` }, { role: "user", content: body.message }];
    const activity: unknown[] = [];
    for (let turn = 0; turn < 5; turn++) {
      const response = await fetch(`${baseUrl}/v1/chat/completions`, { method: "POST", headers: { "content-type": "application/json", ...(process.env.LLM_API_KEY ? { authorization: `Bearer ${process.env.LLM_API_KEY}` } : {}) }, body: JSON.stringify({ model, temperature: Number(process.env.LLM_TEMPERATURE || 0.4), max_tokens: Number(process.env.LLM_MAX_TOKENS || 1200), messages, tools: providerTools, tool_choice: "auto" }) });
      if (!response.ok) throw new Error(`LLM provider returned ${response.status}`);
      const data = await response.json() as { choices?: Array<{ message?: { content?: string; tool_calls?: Array<{ id: string; function: { name: string; arguments: string } }> } }> };
      const answer = data.choices?.[0]?.message;
      if (!answer?.tool_calls?.length) return Response.json({ message: answer?.content || "I couldn't complete that request.", activity, provider: model });
      messages.push({ role: "assistant", content: answer.content || "" });
      for (const call of answer.tool_calls) {
        let args: Record<string, unknown>;
        try { args = JSON.parse(call.function.arguments); } catch { throw new Error("Provider returned invalid tool arguments"); }
        const result = executeDemoTool(call.function.name, args, context);
        activity.push({ tool: call.function.name, kind: assistantTools.find(t => t.name === call.function.name)?.kind, result });
        messages.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(result) });
      }
    }
    return Response.json({ error: "Tool loop limit reached." }, { status: 422 });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Assistant failed." }, { status: 500 });
  }
}

function demoAssistant(message: string, context: ToolContext, useAnalytics: boolean) {
  const lower = message.toLowerCase();
  const activity: Array<Record<string, unknown>> = [];
  const call = (name: string, args: Record<string, unknown>) => { const result = executeDemoTool(name, args, context); activity.push({ tool: name, kind: assistantTools.find(t => t.name === name)?.kind, result }); return result as Record<string, unknown>; };
  if (/create|draft|fill the gaps|three posts|3 posts/.test(lower)) {
    call("get_upcoming_events", { days: 60 }); call("get_content_calendar", { start: "2026-08-17", end: "2026-08-23" });
    if (useAnalytics) call("get_performance_insights", { days: 90, platform: "Instagram" });
    call("create_post_drafts", { campaignId: "cmp_fall", count: 3, topic: "Fall Community Night", useAnalytics });
    return { message: "Created 3 drafts for Tuesday at 6:30 PM, Thursday at 7:00 PM, and Saturday at 10:00 AM. I used the event details, open calendar slots, and your recent performance patterns. They’re waiting for your approval—nothing was published or scheduled.", activity, provider: "Safe demo mode" };
  }
  if (/approval|waiting/.test(lower)) { const result = call("get_pending_approvals", {}); return { message: `You have ${result.count} drafts waiting for approval: Volunteer spotlight, Festival countdown, and Know before you go.`, activity, provider: "Safe demo mode" }; }
  if (/perform|working|flyer|photo|analytics|best/.test(lower)) { call("get_performance_insights", { days: 90, platform: "Instagram" }); return { message: "Photo posts generated 31% higher median engagement than flyers on Instagram during the last 90 days. That’s based on 42 photo posts and 19 flyer posts, with high confidence. Tuesday evenings also produced 24% higher median reach across 38 posts (medium confidence).", activity, provider: "Safe demo mode" }; }
  call("find_content_gaps", { start: "2026-08-17", end: "2026-08-23" });
  return { message: "I found three useful openings next week: Tuesday 6:30 PM, Thursday 7:00 PM, and Saturday 10:00 AM. Volunteer content is underrepresented, and Thursday has no event coverage yet. Want me to prepare drafts for those gaps?", activity, provider: "Safe demo mode" };
}
