"use client";
import { useEffect, useRef, useState } from "react";

type Draft={id:string;caption:string;proposed_at:number|null;content_type:string;tone:string;cta:string;approval_status:string};
type Message={role:"user"|"assistant";content:string;activity?:Array<{tool:string;kind:string}>};
const headers={"content-type":"application/json","x-workspace-id":"ws_riverlight"};

export default function Home(){
  const [version,setVersion]=useState("0.2.0");
  const [messages,setMessages]=useState<Message[]>([{role:"assistant",content:"Tell me what you need to post about. Give me an event, link, rough notes, or just an idea—I’ll write the posts and save them as drafts for you."}]);
  const [input,setInput]=useState("");const [busy,setBusy]=useState(false);const [drafts,setDrafts]=useState<Draft[]>([]);const [error,setError]=useState("");const end=useRef<HTMLDivElement>(null);
  async function load(){try{await fetch("/api/bootstrap",{method:"POST",headers});const r=await fetch("/api/approvals",{headers});const d=await r.json();if(!r.ok)throw new Error(d.error);setDrafts(d.approvals||[])}catch(e){setError(e instanceof Error?e.message:"Could not load drafts")}}
  useEffect(()=>{load();fetch("/api/version").then(r=>r.json()).then(d=>setVersion(d.version)).catch(()=>{})},[]);useEffect(()=>{end.current?.scrollIntoView({behavior:"smooth"})},[messages,busy]);
  async function send(text=input){const prompt=text.trim();if(!prompt||busy)return;setInput("");setError("");setMessages(m=>[...m,{role:"user",content:prompt}]);setBusy(true);try{const r=await fetch("/api/ai/chat",{method:"POST",headers,body:JSON.stringify({message:prompt,workspaceId:"ws_riverlight",currentView:"Post generator",useAnalytics:false})});const d=await r.json();if(!r.ok)throw new Error(d.error);setMessages(m=>[...m,{role:"assistant",content:d.message||"Done.",activity:d.activity}]);await load()}catch(e){const msg=e instanceof Error?e.message:"LM Studio could not be reached";setError(msg);setMessages(m=>[...m,{role:"assistant",content:`I couldn’t reach Qwen. ${msg}`}])}finally{setBusy(false)}}
  async function decide(id:string,decision:"approved"|"rejected"){const r=await fetch("/api/approvals",{method:"PATCH",headers,body:JSON.stringify({postId:id,decision})});const d=await r.json();if(!r.ok){setError(d.error);return}await load()}
  return <main className="cockpit">
    <header className="top"><div className="logo">SC</div><div><h1>Social Cockpit</h1><p>Qwen-powered post assistant <b className="version">v{version}</b></p></div><span className="connection"><i/> LM Studio</span></header>
    <section className="workspace">
      <div className="chat">
        <div className="intro"><span>RIVERLIGHT HQ</span><h2>What are we posting?</h2><p>Talk naturally. Qwen can write, revise, and save drafts—but never publish without you.</p></div>
        <div className="messages">{messages.map((m,i)=><article className={m.role} key={i}><b>{m.role==="assistant"?"Q":"YOU"}</b><div><p>{m.content}</p>{m.activity?.map((a,j)=><small key={j}>{a.kind==="draft_write"?"Saved drafts":"Checked workspace"} · {a.tool.replaceAll("_"," ")}</small>)}</div></article>)}{busy&&<article className="assistant"><b>Q</b><div><p className="thinking">Qwen is working…</p></div></article>}<div ref={end}/></div>
        <div className="suggestions">{["Write 3 posts for an event next Saturday","Rewrite my latest draft to sound warmer","Give me five volunteer recruitment ideas"].map(x=><button key={x} onClick={()=>send(x)}>{x}</button>)}</div>
        <div className="composer"><textarea value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}}} placeholder="Example: Create three Facebook posts for our food drive on October 18…"/><button disabled={busy||!input.trim()} onClick={()=>send()}>Send</button></div>
        {error&&<div className="error">{error}<small>Check that LM Studio’s server is running on port 1234 and the model name in your .env matches the loaded Qwen model.</small></div>}
      </div>
      <aside className="drafts"><div className="draft-head"><div><span>DRAFTS</span><h2>Waiting for you</h2></div><button onClick={load}>↻</button></div>{drafts.length===0?<div className="empty"><b>No drafts yet</b><p>Ask Qwen to create posts and they’ll appear here.</p></div>:<div className="draft-list">{drafts.map(d=><article key={d.id}><header><span>{d.content_type||"Post"}</span><time>{d.proposed_at?new Date(d.proposed_at).toLocaleString():"No date yet"}</time></header><p>{d.caption}</p><div className="tags"><span>{d.tone}</span><span>{d.cta}</span></div><footer><button onClick={()=>decide(d.id,"rejected")}>Reject</button><button className="approve" onClick={()=>decide(d.id,"approved")}>Approve</button></footer></article>)}</div>}</aside>
    </section>
  </main>
}
