export type ToolKind = "read" | "draft_write";
export type ToolContext = { workspaceId: string; currentView: string; campaignId?: string };

export type AssistantTool = {
  kind: ToolKind;
  name: string;
  description: string;
  parameters: Record<string, unknown>;
};

const object = (properties: Record<string, unknown>, required: string[] = []) => ({
  type: "object", properties, required, additionalProperties: false,
});

export const assistantTools: AssistantTool[] = [
  { kind: "read", name: "get_upcoming_events", description: "List upcoming events in the active workspace.", parameters: object({ days: { type: "integer", minimum: 1, maximum: 180 } }) },
  { kind: "read", name: "get_content_calendar", description: "Get scheduled and draft content in a date range for the active workspace.", parameters: object({ start: { type: "string" }, end: { type: "string" } }, ["start", "end"]) },
  { kind: "read", name: "get_pending_approvals", description: "List drafts currently waiting for human approval.", parameters: object({}) },
  { kind: "read", name: "get_performance_insights", description: "Return evidence-backed analytics insights with samples and confidence.", parameters: object({ days: { type: "integer", minimum: 7, maximum: 730 }, platform: { type: "string" } }) },
  { kind: "read", name: "find_content_gaps", description: "Find open calendar slots and underrepresented content categories.", parameters: object({ start: { type: "string" }, end: { type: "string" } }, ["start", "end"]) },
  { kind: "draft_write", name: "create_post_drafts", description: "Create draft posts only. Every result enters the approval queue; this never schedules or publishes.", parameters: object({ campaignId: { type: "string" }, count: { type: "integer", minimum: 1, maximum: 12 }, topic: { type: "string", minLength: 2 }, useAnalytics: { type: "boolean" } }, ["count", "topic"]) },
  { kind: "draft_write", name: "update_post_draft", description: "Edit a draft caption. Approved, scheduled, or published posts cannot be changed.", parameters: object({ postId: { type: "string" }, caption: { type: "string", minLength: 1, maxLength: 5000 } }, ["postId", "caption"]) },
  { kind: "draft_write", name: "reschedule_post_draft", description: "Suggest a new time for a draft. The draft remains pending approval.", parameters: object({ postId: { type: "string" }, proposedAt: { type: "string" } }, ["postId", "proposedAt"]) },
];

export const providerTools = assistantTools.map(tool => ({
  type: "function",
  function: { name: tool.name, description: tool.description, parameters: tool.parameters, strict: true },
}));

export function assertToolCall(name: string, raw: unknown, context: ToolContext) {
  const tool = assistantTools.find(item => item.name === name);
  if (!tool) throw new Error("Unknown or prohibited tool");
  if (!context.workspaceId) throw new Error("Active workspace is required");
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("Tool arguments must be an object");
  const args = raw as Record<string, unknown>;
  const allowed = Object.keys((tool.parameters.properties || {}) as object);
  if (Object.keys(args).some(key => !allowed.includes(key))) throw new Error("Unexpected tool argument");
  return { tool, args, workspaceId: context.workspaceId };
}

export function executeDemoTool(name: string, args: Record<string, unknown>, context: ToolContext) {
  assertToolCall(name, args, context);
  const results: Record<string, unknown> = {
    get_upcoming_events: { events: [{ id: "evt_fall", name: "Fall Community Night", date: "2026-10-24", campaignId: "cmp_fall" }] },
    get_content_calendar: { posts: [{ id: "draft_1", date: "2026-08-18T18:30:00-07:00", status: "draft", topic: "Volunteer spotlight" }], openSlots: ["Tuesday 6:30 PM", "Thursday 7:00 PM", "Saturday 10:00 AM"] },
    get_pending_approvals: { count: 3, drafts: ["Volunteer spotlight", "Festival countdown", "Know before you go"] },
    get_performance_insights: { dateRange: `${args.days || 90} days`, insights: [{ finding: "Photo posts generated 31% higher median engagement than flyers on Instagram.", samples: { photos: 42, flyers: 19 }, confidence: "high" }, { finding: "Tuesday evening posts generated 24% higher median reach than weekday mornings.", sampleSize: 38, confidence: "medium" }] },
    find_content_gaps: { gaps: [{ day: "Tuesday", time: "6:30 PM", reason: "open high-performing slot" }, { day: "Thursday", time: "7:00 PM", reason: "no event content scheduled" }, { day: "Saturday", time: "10:00 AM", reason: "underrepresented volunteer content" }] },
    create_post_drafts: { created: Number(args.count), status: "pending_approval", ids: Array.from({ length: Number(args.count) }, (_, i) => `draft_ai_${Date.now()}_${i}`), publishingAttempted: false },
    update_post_draft: { id: args.postId, status: "pending_approval", updated: true },
    reschedule_post_draft: { id: args.postId, proposedAt: args.proposedAt, status: "pending_approval", scheduled: false },
  };
  return results[name];
}

export const SYSTEM_POLICY = `You are Social Cockpit's workspace-scoped social media manager. Use tools to inspect real application data. Never invent analytics. Cite sample size, date range, and confidence when available. You may create or modify drafts only. You can never approve, schedule, or publish. All created content must remain pending human approval. Never request or expose API keys. Current workspace data is the only authorized scope.`;
