"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Tab = "Overview" | "Content" | "Campaigns" | "Recommendations" | "Imports";
const tabs: Tab[] = ["Overview", "Content", "Campaigns", "Recommendations", "Imports"];

const posts = [
  { title: "Neighbors make the night", platform: "Instagram", type: "Community story", reach: 8240, engagement: 9.8, delta: 122, tone: "Conversational", media: "Photo", date: "Aug 8" },
  { title: "3 days until Riverlight", platform: "Instagram", type: "Countdown", reach: 6790, engagement: 8.4, delta: 78, tone: "Excited", media: "Video", date: "Aug 6" },
  { title: "Everything to know before Saturday", platform: "Facebook", type: "Event information", reach: 5140, engagement: 5.2, delta: 31, tone: "Informational", media: "Graphic", date: "Aug 5" },
  { title: "Volunteer call: welcome crew", platform: "Facebook", type: "Volunteer", reach: 2380, engagement: 3.1, delta: -18, tone: "Urgent", media: "Flyer", date: "Aug 2" },
];

const hourly = [22, 31, 26, 42, 54, 49, 72, 68, 86, 78, 96, 90];

function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    overview: "M3 3h7v7H3zM14 3h7v4h-7zM14 11h7v10h-7zM3 14h7v7H3z",
    campaign: "M4 13V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8M3 21h18M7 17h10",
    spark: "m12 3-1.7 5.3L5 10l5.3 1.7L12 17l1.7-5.3L19 10l-5.3-1.7z",
    import: "M12 3v12m0 0 4-4m-4 4-4-4M5 21h14",
    arrow: "M5 12h14m-5-5 5 5-5 5",
    chevron: "m9 18 6-6-6-6",
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={paths[name]} /></svg>;
}

function Sparkline({ values = hourly }: { values?: number[] }) {
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${42 - (v / 100) * 38}`).join(" ");
  return <svg className="sparkline" viewBox="0 0 100 44" preserveAspectRatio="none"><defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#c8ff5a" stopOpacity=".22"/><stop offset="1" stopColor="#c8ff5a" stopOpacity="0"/></linearGradient></defs><polygon points={`0,44 ${pts} 100,44`} fill="url(#fill)"/><polyline points={pts} fill="none" stroke="#c8ff5a" strokeWidth="2" vectorEffect="non-scaling-stroke"/></svg>;
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("Overview");
  const [range, setRange] = useState("Last 30 days");
  const [optimize, setOptimize] = useState(true);
  const [file, setFile] = useState<string>("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<string[][]>([]);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const importReady = rows.length > 0;

  const detected = useMemo(() => headers.map(h => ({ source: h, target: detectField(h) })), [headers]);

  async function loadFile(f?: File) {
    if (!f) return;
    const text = await f.text();
    const lines = text.split(/\r?\n/).filter(Boolean).slice(0, 7);
    const parsed = lines.map(line => line.split(/,(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)/).map(v => v.replace(/^\"|\"$/g, "").trim()));
    setFile(f.name); setHeaders(parsed[0] || []); setRows(parsed.slice(1));
  }

  return <div className={`app-shell ${assistantOpen ? "assistant-visible" : ""}`}>
    <aside>
      <div className="brand"><div className="brandmark">SC</div><div><strong>Social Cockpit</strong><span>Performance intelligence</span></div></div>
      <nav aria-label="Main navigation">
        {tabs.map((item, i) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}><Icon name={["overview","import","campaign","spark","import"][i]} />{item}{item === "Recommendations" && <em>4</em>}</button>)}
      </nav>
      <div className="side-bottom"><div className="workspace-dot">RH</div><div><strong>Riverlight HQ</strong><span>3 accounts connected</span></div><Icon name="chevron" /></div>
    </aside>

    <main>
      <header><div><span className="eyebrow">RIVERLIGHT HQ / ANALYTICS</span><h1>{tab}</h1></div><div className="header-actions"><label className="select">{range}<select value={range} onChange={e => setRange(e.target.value)}><option>Last 30 days</option><option>Last 90 days</option><option>This year</option></select></label><button className="primary" onClick={() => setTab("Imports")}>Import data <Icon name="arrow" /></button></div></header>

      {tab === "Overview" && <Overview range={range} />}
      {tab === "Content" && <ContentWorkspace />}
      {tab === "Campaigns" && <Campaigns />}
      {tab === "Recommendations" && <Recommendations optimize={optimize} setOptimize={setOptimize} />}
      {tab === "Imports" && <Imports file={file} headers={headers} rows={rows} detected={detected} input={input} loadFile={loadFile} importReady={importReady} />}
    </main>
    <button className="ask-ai" onClick={() => setAssistantOpen(true)}><span>✦</span> Ask AI</button>
    <AssistantPanel open={assistantOpen} close={() => setAssistantOpen(false)} currentView={tab} useAnalytics={optimize} />
  </div>;
}

type Draft = { id:string; caption:string; status:string; proposed_at:number|null; content_type:string; account_id:string; approval_status?:string };

function ContentWorkspace(){
  const [drafts,setDrafts]=useState<Draft[]>([]); const [caption,setCaption]=useState(""); const [date,setDate]=useState(""); const [loading,setLoading]=useState(true); const [error,setError]=useState("");
  const apiHeaders={"content-type":"application/json","x-workspace-id":"ws_riverlight"};
  async function refresh(){setLoading(true);try{await fetch("/api/bootstrap",{method:"POST",headers:apiHeaders});const res=await fetch("/api/approvals",{headers:apiHeaders});const data=await res.json();if(!res.ok)throw new Error(data.error);setDrafts(data.approvals||[]);setError("")}catch(e){setError(e instanceof Error?e.message:"Unable to load content")}finally{setLoading(false)}}
  useEffect(()=>{refresh()},[]);
  async function create(){if(!caption.trim())return;const res=await fetch("/api/posts",{method:"POST",headers:apiHeaders,body:JSON.stringify({caption,proposedAt:date||null,contentType:"Announcement",tone:"Conversational",cta:"Learn more",mediaType:"Text only"})});const data=await res.json();if(!res.ok){setError(data.error);return}setCaption("");setDate("");await refresh()}
  async function decide(postId:string,decision:"approved"|"rejected"){const res=await fetch("/api/approvals",{method:"PATCH",headers:apiHeaders,body:JSON.stringify({postId,decision})});const data=await res.json();if(!res.ok){setError(data.error);return}await refresh()}
  return <section className="content-workspace"><article className="panel draft-builder"><span className="kicker">NEW CONTENT</span><h2>Create a real draft</h2><p>Drafts are stored in the active workspace and enter the approval queue automatically.</p><label>Caption<textarea value={caption} onChange={e=>setCaption(e.target.value)} placeholder="Write the post caption…" rows={7}/></label><label>Proposed date and time<input type="datetime-local" value={date} onChange={e=>setDate(e.target.value)}/></label><button className="primary" onClick={create}>Create draft <Icon name="arrow"/></button>{error&&<div className="form-error">{error}</div>}</article><article className="panel approval-queue"><div className="panel-head"><div><span className="kicker">HUMAN APPROVAL</span><h2>Approval queue</h2></div><button onClick={refresh}>Refresh</button></div>{loading?<div className="empty-state">Loading workspace records…</div>:drafts.length===0?<div className="empty-state">No drafts are waiting. Create one to begin.</div>:<div className="approval-list">{drafts.map(d=><div className="approval-card" key={d.id}><div><span>{d.content_type||"Post"}</span><time>{d.proposed_at?new Date(d.proposed_at).toLocaleString():"Date not chosen"}</time></div><p>{d.caption}</p><footer><button className="reject" onClick={()=>decide(d.id,"rejected")}>Reject</button><button className="approve" onClick={()=>decide(d.id,"approved")}>Approve draft</button></footer></div>)}</div>}</article></section>
}

type ChatMessage = { role: "assistant" | "user"; content: string; activity?: Array<{ tool?: string; kind?: string }> };

function AssistantPanel({ open, close, currentView, useAnalytics }: { open: boolean; close: () => void; currentView: string; useAnalytics: boolean }) {
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: "assistant", content: "I’m your Riverlight HQ social media manager. I can inspect this workspace’s calendar, campaigns, drafts, media, and analytics—and create drafts that always wait for your approval." }]);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const suggestions = currentView === "Campaigns" ? ["Give me four more posts for this campaign", "Is this campaign on track?"] : currentView === "Overview" ? ["What performed best last month?", "Find gaps in next week’s calendar"] : ["Show me everything waiting for approval", "Create 3 posts for next week"];

  async function send(text = value) {
    const prompt = text.trim(); if (!prompt || busy) return;
    setMessages(old => [...old, { role: "user", content: prompt }]); setValue(""); setBusy(true);
    try {
      const response = await fetch("/api/ai/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message: prompt, workspaceId: "ws_riverlight", currentView, campaignId: currentView === "Campaigns" ? "cmp_fall" : undefined, useAnalytics }) });
      const data = await response.json();
      setMessages(old => [...old, { role: "assistant", content: data.message || data.error || "I couldn’t complete that request.", activity: data.activity }]);
    } catch { setMessages(old => [...old, { role: "assistant", content: "The assistant service is unavailable. No data was changed." }]); }
    finally { setBusy(false); }
  }

  return <><div className={`assistant-scrim ${open ? "show" : ""}`} onClick={close}/><aside className={`assistant-panel ${open ? "open" : ""}`} aria-hidden={!open}>
    <div className="ai-head"><div><span className="ai-orb">✦</span><div><strong>Social Cockpit AI</strong><small>Riverlight HQ · {currentView}</small></div></div><button onClick={close} aria-label="Close assistant">×</button></div>
    <div className="scope-note"><i/> Working only in <strong>Riverlight HQ</strong><span>Draft actions require human approval</span></div>
    <div className="chat-stream">{messages.map((message, index) => <div className={`message ${message.role}`} key={index}><span>{message.role === "assistant" ? "✦" : "YOU"}</span><div><p>{message.content}</p>{message.activity?.length ? <div className="tool-trace">{message.activity.map((a,i) => <small key={i}><b>{a.kind === "draft_write" ? "Draft action" : "Checked"}</b> {String(a.tool).replaceAll("_", " ")}</small>)}</div> : null}</div></div>)}{busy && <div className="message assistant"><span>✦</span><div><p className="thinking">Inspecting workspace data…</p></div></div>}</div>
    <div className="quick-prompts">{suggestions.map(s => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>
    <div className="composer"><textarea value={value} onChange={e => setValue(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} placeholder="Ask about your calendar, campaigns, or performance…"/><button onClick={() => send()} disabled={busy || !value.trim()} aria-label="Send">↑</button><footer><span>{useAnalytics ? "Analytics-aware generation on" : "Analytics-aware generation off"}</span><span>Enter to send</span></footer></div>
  </aside></>;
}

function Overview({ range }: { range: string }) {
  return <>
    <section className="context-row"><div><span className="live-dot"/>Data current through Aug 10, 2026</div><div>Compared with previous period</div></section>
    <section className="metrics">
      <Metric label="TOTAL REACH" value="84,290" change="+18.4%" note="13,102 more people" />
      <Metric label="IMPRESSIONS" value="126.8K" change="+12.7%" note="1.50× frequency" />
      <Metric label="ENGAGEMENT" value="6,482" change="+24.1%" note="7.7% rate" />
      <Metric label="LINK CLICKS" value="1,204" change="+8.6%" note="1.43% of reach" />
    </section>
    <section className="grid-main">
      <article className="panel performance"><div className="panel-head"><div><span className="kicker">PERFORMANCE OVER TIME</span><h2>Reach & engagement</h2></div><div className="legend"><i/> Reach <i className="purple"/> Engagement</div></div><div className="chart-labels"><span>12K</span><span>8K</span><span>4K</span><span>0</span></div><div className="big-chart"><Sparkline values={[14,21,18,32,29,45,42,58,51,74,68,88]} /><div className="purple-line"/></div><div className="x-axis"><span>Jul 12</span><span>Jul 18</span><span>Jul 24</span><span>Jul 30</span><span>Aug 5</span><span>Aug 10</span></div></article>
      <article className="panel pulse"><span className="kicker">ACCOUNT PULSE</span><h2>Audience growth</h2><div className="audience"><strong>+386</strong><span>net new followers</span></div><Sparkline values={[18,22,29,27,39,44,42,57,62,70,74,88]} /><div className="account-row"><span className="insta">◎</span><div><strong>Instagram</strong><span>8,426 followers</span></div><b>+4.2%</b></div><div className="account-row"><span className="fb">f</span><div><strong>Facebook</strong><span>12,180 followers</span></div><b>+1.8%</b></div></article>
    </section>
    <section className="panel posts"><div className="panel-head"><div><span className="kicker">CONTENT PERFORMANCE</span><h2>What landed — and what didn’t</h2></div><button>View all posts <Icon name="arrow" /></button></div><div className="table"><div className="tr th"><span>POST</span><span>TYPE</span><span>REACH</span><span>ENG. RATE</span><span>VS. BASELINE</span></div>{posts.map((p,i) => <div className="tr" key={p.title}><span className="post-title"><b>{i+1}</b><span><strong>{p.title}</strong><small>{p.platform} · {p.date} · {p.media}</small></span></span><span><mark>{p.type}</mark></span><span>{p.reach.toLocaleString()}</span><span>{p.engagement}%</span><span className={p.delta > 0 ? "positive" : "negative"}>{p.delta > 0 ? "+" : ""}{p.delta}%</span></div>)}</div></section>
  </>;
}

function Metric({label,value,change,note}:{label:string,value:string,change:string,note:string}) { return <article className="metric"><div><span>{label}</span><b>{value}</b></div><Sparkline values={[20,18,30,26,42,38,53,50,66,61,78,86]} /><footer><strong>{change}</strong><span>{note}</span></footer></article> }

function Campaigns() { return <section className="campaign-layout"><article className="hero-card"><span className="status-pill">ACTIVE CAMPAIGN</span><h2>Riverlight Summer Festival</h2><p>July 18 – August 17 · 14 published posts · 3 scheduled</p><div className="campaign-stats"><div><span>TOTAL REACH</span><strong>48,320</strong><small>+42% vs campaign baseline</small></div><div><span>ENGAGEMENT</span><strong>4,108</strong><small>8.5% average rate</small></div><div><span>LINK CLICKS</span><strong>842</strong><small>1.74% click rate</small></div></div></article><article className="panel breakdown"><span className="kicker">CAMPAIGN SIGNALS</span><h2>What is working</h2>{[["Best day","Tuesday","+63% reach"],["Best time","6–8 PM","9.4% engagement"],["Best format","Event photos","1.7× median"],["Best CTA","Comment","12.1% engagement"]].map(x=><div className="signal" key={x[0]}><span>{x[0]}</span><strong>{x[1]}</strong><b>{x[2]}</b></div>)}</article><article className="panel wide"><span className="kicker">CAMPAIGN TIMELINE</span><h2>Momentum by phase</h2><div className="phase-bars"><div><span>Awareness</span><i style={{width:"43%"}}/><b>21.2K</b></div><div><span>Consideration</span><i style={{width:"71%"}}/><b>35.4K</b></div><div><span>Final 72 hours</span><i style={{width:"96%"}}/><b>48.3K</b></div></div></article></section> }

function Recommendations({optimize,setOptimize}:{optimize:boolean,setOptimize:(x:boolean)=>void}) { const recs=[{title:"Lead with real event photos on Instagram",body:"Photo posts reached 1.7× the account median while designed flyers reached 0.8×.",sample:"34 posts",confidence:"High confidence"},{title:"Schedule Tuesday and Thursday evenings",body:"Posts published from 6–8 PM produced 41% more engagement than the account’s other weekday posts.",sample:"52 posts · last 90 days",confidence:"High confidence"},{title:"Use countdowns inside the final 72 hours",body:"Countdown content produced an 8.9% engagement rate near the event, compared with 5.1% earlier.",sample:"18 posts",confidence:"Medium confidence"},{title:"Keep Instagram captions between 80–150 words",body:"This range outperformed longer captions by 29% on engagement rate after normalizing for audience size.",sample:"67 posts",confidence:"High confidence"}]; return <><section className="optimization"><div><span className="kicker">CAMPAIGN GENERATION</span><h2>Optimize using historical performance</h2><p>Use proven patterns as recommendations when choosing timing, format, caption length, and CTA.</p></div><button className={`toggle ${optimize?"on":""}`} onClick={()=>setOptimize(!optimize)} aria-label="Toggle historical optimization"><i/></button></section><section className="recommend-grid">{recs.map((r,i)=><article className="recommend" key={r.title}><div className="rec-num">0{i+1}</div><span className="confidence">{r.confidence}</span><h2>{r.title}</h2><p>{r.body}</p><footer><span>Evidence</span><strong>{r.sample}</strong><button>View analysis <Icon name="arrow"/></button></footer></article>)}</section></> }

function Imports({file,headers,rows,detected,input,loadFile,importReady}:{file:string,headers:string[],rows:string[][],detected:{source:string,target:string}[],input:React.RefObject<HTMLInputElement|null>,loadFile:(f?:File)=>void,importReady:boolean}) { return <section className="import-layout"><article className="panel upload"><span className="kicker">HISTORICAL DATA IMPORT</span><h2>Bring your performance history with you</h2><p>Upload a Buffer, Meta Business Suite, Facebook, Instagram, CSV, or Excel export. We’ll detect its shape before anything is saved.</p><div className={`dropzone ${file?"loaded":""}`} onClick={()=>input.current?.click()} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();loadFile(e.dataTransfer.files[0])}}><input ref={input} type="file" accept=".csv,.xlsx,.xls" onChange={e=>loadFile(e.target.files?.[0])}/><div className="upload-icon">↓</div><strong>{file || "Drop an export here"}</strong><span>{file ? `${rows.length} preview rows detected` : "or choose a CSV / XLSX file"}</span></div><div className="privacy"><b>Local source of truth</b><span>Imported records and raw source files remain owned by your workspace.</span></div></article><article className="panel mapping"><div className="panel-head"><div><span className="kicker">FORMAT DETECTION</span><h2>{file ? "Review field mapping" : "Waiting for a file"}</h2></div>{file && <span className="status-pill">CSV DETECTED</span>}</div>{!file ? <div className="empty-state">Column mappings and matching confidence will appear here before import.</div> : <>{detected.slice(0,6).map(d=><div className="map-row" key={d.source}><code>{d.source}</code><span>→</span><strong>{d.target}</strong></div>)}<button className="primary full">Continue to matching <Icon name="arrow"/></button></>}</article>{importReady && <article className="panel preview wide"><div className="panel-head"><div><span className="kicker">PREVIEW · NOTHING IMPORTED YET</span><h2>First {rows.length} records</h2></div><div className="match-summary"><span><i className="match"/> {Math.max(0,rows.length-1)} matched</span><span><i className="review"/> 1 needs review</span><span><i className="dupe"/> 0 duplicates</span></div></div><div className="preview-scroll"><table><thead><tr>{headers.slice(0,6).map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{r.slice(0,6).map((v,j)=><td key={j}>{v || "—"}</td>)}</tr>)}</tbody></table></div></article>}</section> }

function detectField(value:string) { const v=value.toLowerCase().replace(/[^a-z0-9]/g,""); if(v.includes("caption")||v.includes("description")||v==="text")return "Post caption"; if(v.includes("date")||v.includes("published"))return "Published at"; if(v.includes("platform")||v.includes("network"))return "Platform"; if(v.includes("reach"))return "Reach"; if(v.includes("impression"))return "Impressions"; if(v.includes("click"))return "Link clicks"; if(v.includes("comment"))return "Comments"; if(v.includes("share"))return "Shares"; if(v.includes("like")||v.includes("reaction"))return "Reactions"; return "Custom metric"; }
