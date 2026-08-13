import json, os, random, sqlite3, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file
import requests
from urllib.parse import urlsplit, urlunsplit
from comfyui_client import ComfyUIClient, ComfyUIError
from asset_processing import isolate_background, vectorize_png

VERSION="1.11.1"; ROOT=Path(__file__).parent; DATA=Path(os.getenv("DATA_DIR",ROOT/"data")); UPLOADS=DATA/"uploads"; ASSETS=DATA/"generated-assets"; DB=DATA/"social-cockpit.db"
DATA.mkdir(exist_ok=True);UPLOADS.mkdir(exist_ok=True);ASSETS.mkdir(exist_ok=True)
app=Flask(__name__);app.config["MAX_CONTENT_LENGTH"]=25*1024*1024
def db(): c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def init():
 c=db();c.executescript("""
 CREATE TABLE IF NOT EXISTS library(id TEXT PRIMARY KEY,category TEXT NOT NULL,title TEXT NOT NULL,details TEXT,url TEXT,filename TEXT,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS tones(id TEXT PRIMARY KEY,name TEXT NOT NULL,prompt TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),lm_url TEXT NOT NULL,lm_model TEXT NOT NULL,temperature REAL NOT NULL,max_tokens INTEGER NOT NULL,buffer_token TEXT,buffer_channel TEXT,lm_token TEXT DEFAULT '');
 CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,caption TEXT NOT NULL,scheduled_at TEXT NOT NULL,status TEXT NOT NULL,tone TEXT,subject TEXT,buffer_id TEXT,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS asset_batches(id TEXT PRIMARY KEY,user_prompt TEXT NOT NULL,asset_type TEXT NOT NULL,visual_style TEXT NOT NULL,color_mode TEXT NOT NULL,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL,user_prompt TEXT NOT NULL,enhanced_prompt TEXT NOT NULL,sub_prompt TEXT NOT NULL,asset_type TEXT NOT NULL,visual_style TEXT NOT NULL,color_mode TEXT NOT NULL,seed INTEGER NOT NULL,workflow_id TEXT NOT NULL,created_at TEXT NOT NULL,status TEXT NOT NULL,original_path TEXT,transparent_path TEXT,svg_path TEXT,transparency_status TEXT,vector_status TEXT,favorite INTEGER DEFAULT 0,error TEXT DEFAULT '');
 """)
 if "lm_token" not in [x[1] for x in c.execute("PRAGMA table_info(settings)").fetchall()]:c.execute("ALTER TABLE settings ADD COLUMN lm_token TEXT DEFAULT ''")
 settings_cols=[x[1] for x in c.execute("PRAGMA table_info(settings)").fetchall()]
 for column in ("facebook_channel","instagram_channel","public_url"):
  if column not in settings_cols:c.execute(f"ALTER TABLE settings ADD COLUMN {column} TEXT DEFAULT ''")
 if "comfyui_url" not in settings_cols:c.execute("ALTER TABLE settings ADD COLUMN comfyui_url TEXT DEFAULT 'http://host.docker.internal:8188'")
 c.execute("UPDATE settings SET comfyui_url='http://host.docker.internal:8188' WHERE comfyui_url IS NULL OR comfyui_url='' ")
 draft_cols=[x[1] for x in c.execute("PRAGMA table_info(drafts)").fetchall()]
 if "platforms" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN platforms TEXT DEFAULT 'facebook'")
 if "media_id" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN media_id TEXT DEFAULT ''")
 if "instagram_type" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN instagram_type TEXT DEFAULT 'post'")
 if "facebook_type" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN facebook_type TEXT DEFAULT 'post'")
 if "schedule_mode" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN schedule_mode TEXT DEFAULT 'custom'")
 if "information_json" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN information_json TEXT DEFAULT '[]'")
 if "instructions" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN instructions TEXT DEFAULT ''")
 library_cols=[x[1] for x in c.execute("PRAGMA table_info(library)").fetchall()]
 if "image_url" not in library_cols:c.execute("ALTER TABLE library ADD COLUMN image_url TEXT DEFAULT ''")
 for column in ("event_date","start_time","end_time","location"):
  if column not in library_cols:c.execute(f"ALTER TABLE library ADD COLUMN {column} TEXT DEFAULT ''")
 for column in ("recurrence","recurrence_days","recurrence_end"):
  if column not in library_cols:c.execute(f"ALTER TABLE library ADD COLUMN {column} TEXT DEFAULT ''")
 tone_cols=[x[1] for x in c.execute("PRAGMA table_info(tones)").fetchall()]
 if "is_default" not in tone_cols:c.execute("ALTER TABLE tones ADD COLUMN is_default INTEGER DEFAULT 0")
 c.execute("INSERT OR IGNORE INTO settings(id,lm_url,lm_model,temperature,max_tokens,buffer_token,buffer_channel,lm_token) VALUES(1,?,?,?,?,?,?,?)",("http://host.docker.internal:1234","qwen",0.4,2400,"","",""));
 c.execute("UPDATE settings SET facebook_channel=buffer_channel WHERE (facebook_channel IS NULL OR facebook_channel='') AND buffer_channel IS NOT NULL AND buffer_channel!=''")
 c.execute("INSERT OR IGNORE INTO tones(id,name,prompt,is_default) VALUES(?,?,?,?)",("tone_conversational","Conversational","Natural, warm, direct, and human. Avoid corporate language.",1));c.execute("UPDATE tones SET is_default=1 WHERE id=(SELECT id FROM tones ORDER BY name LIMIT 1) AND NOT EXISTS(SELECT 1 FROM tones WHERE is_default=1)");c.commit();c.close()
init()
def rows(sql,args=()): c=db();r=[dict(x) for x in c.execute(sql,args).fetchall()];c.close();return r
def web_url(value):
 value=(value or "").strip()
 return value if not value or value.startswith(("http://","https://")) else "https://"+value
def buffer_call(token,query,variables=None):
 r=requests.post("https://api.buffer.com",headers={"Authorization":"Bearer "+token},json={"query":query,"variables":variables or {}},timeout=60)
 try:result=r.json()
 except ValueError:raise ValueError(f"Buffer returned {r.status_code}: {r.text[:300]}")
 if not r.ok:raise ValueError((result.get("errors") or [{}])[0].get("message",f"Buffer returned HTTP {r.status_code}"))
 if result.get("errors"):raise ValueError(result["errors"][0].get("message","Buffer query failed"))
 return result.get("data") or {}
@app.get("/")
def home(): return render_template("index.html",version=VERSION)
@app.get("/media/<ident>")
def media(ident):
 item=rows("SELECT filename FROM library WHERE id=?",(ident,))
 if not item or not item[0]["filename"]:return jsonify(error="Media not found"),404
 return send_file(UPLOADS/f"{ident}-{item[0]['filename']}")
@app.get("/api/state")
def state():
 s=rows("SELECT * FROM settings WHERE id=1")[0];s["buffer_token"]="" if not s["buffer_token"] else "configured";s["lm_token"]="" if not s["lm_token"] else "configured"
 return jsonify(version=VERSION,library=rows("SELECT * FROM library ORDER BY created_at DESC"),tones=rows("SELECT * FROM tones ORDER BY name"),drafts=rows("SELECT * FROM drafts WHERE status IN ('pending','ready') ORDER BY scheduled_at"),assets=rows("SELECT * FROM assets ORDER BY created_at DESC"),settings=s)
@app.get("/api/buffer-queue")
def buffer_queue():
 s=rows("SELECT * FROM settings WHERE id=1")[0]
 if not s["buffer_token"]:return jsonify(error="Configure the Buffer API key in Settings"),400
 channel_ids=list(dict.fromkeys(filter(None,[s["facebook_channel"] or s["buffer_channel"],s["instagram_channel"]])))
 if not channel_ids:return jsonify(error="Configure at least one Buffer channel ID in Settings"),400
 try:
  account=buffer_call(s["buffer_token"],"query { account { organizations { id name } } }");organizations=(account.get("account") or {}).get("organizations") or [];posts=[]
  query="""query Queue($organization:OrganizationId!,$channels:[ChannelId!]!){posts(first:100,input:{organizationId:$organization,sort:[{field:dueAt,direction:asc}],filter:{status:[scheduled],channelIds:$channels}}){edges{node{id text dueAt channelId}}}}"""
  for organization in organizations:
   try:
    data=buffer_call(s["buffer_token"],query,{"organization":organization["id"],"channels":channel_ids});posts.extend(edge["node"] for edge in (data.get("posts") or {}).get("edges",[]))
   except ValueError:continue
  labels={s["facebook_channel"] or s["buffer_channel"]:"Facebook",s["instagram_channel"]:"Instagram"};seen={}
  for post in posts:seen[post["id"]]={**post,"platform":labels.get(post.get("channelId"),"Buffer")}
  return jsonify(posts=sorted(seen.values(),key=lambda post:post.get("dueAt") or ""))
 except (requests.RequestException,ValueError,KeyError) as e:return jsonify(error=f"Could not load Buffer queue: {e}"),502
@app.post("/api/library")
def add_library():
 if request.content_type and "multipart" in request.content_type:
  f=request.files.get("file");ident=str(uuid.uuid4());name=None
  if f and f.filename:name=Path(f.filename).name;f.save(UPLOADS/f"{ident}-{name}")
  record=(ident,request.form.get("category","Information"),request.form.get("title","").strip(),request.form.get("details",""),web_url(request.form.get("url")),name,datetime.now(timezone.utc).isoformat(),web_url(request.form.get("image_url")),request.form.get("event_date",""),request.form.get("start_time",""),request.form.get("end_time",""),request.form.get("location",""),request.form.get("recurrence","one_time"),json.dumps(request.form.getlist("recurrence_day")),request.form.get("recurrence_end",""))
  if not record[2]:return jsonify(error="Title is required"),400
 else:
  x=request.get_json(force=True);record=(str(uuid.uuid4()),x.get("category","Information"),x.get("title","" ).strip(),x.get("details",""),x.get("url",""),None,datetime.now(timezone.utc).isoformat(),x.get("image_url",""),x.get("event_date",""),x.get("start_time",""),x.get("end_time",""),x.get("location",""),x.get("recurrence","one_time"),json.dumps(x.get("recurrence_days",[])),x.get("recurrence_end",""))
  if not record[2]:return jsonify(error="Title is required"),400
 c=db();c.execute("INSERT INTO library(id,category,title,details,url,filename,created_at,image_url,event_date,start_time,end_time,location,recurrence,recurrence_days,recurrence_end) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",record);c.commit();c.close();return jsonify(ok=True)
@app.put("/api/library/<ident>")
def edit_library(ident):
 x=request.form;f=request.files.get("file");c=db();old=c.execute("SELECT * FROM library WHERE id=?",(ident,)).fetchone()
 if not old:return jsonify(error="Information not found"),404
 name=old["filename"]
 if f and f.filename:name=Path(f.filename).name;f.save(UPLOADS/f"{ident}-{name}")
 title=x.get("title","").strip()
 if not title:return jsonify(error="Title is required"),400
 c.execute("UPDATE library SET category=?,title=?,details=?,url=?,filename=?,image_url=?,event_date=?,start_time=?,end_time=?,location=?,recurrence=?,recurrence_days=?,recurrence_end=? WHERE id=?",(x.get("category","Information"),title,x.get("details",""),web_url(x.get("url")),name,web_url(x.get("image_url")),x.get("event_date",""),x.get("start_time",""),x.get("end_time",""),x.get("location",""),x.get("recurrence","one_time"),json.dumps(x.getlist("recurrence_day")),x.get("recurrence_end",""),ident));c.commit();c.close();return jsonify(ok=True)
@app.delete("/api/library/<ident>")
def del_library(ident): c=db();r=c.execute("SELECT filename FROM library WHERE id=?",(ident,)).fetchone();c.execute("DELETE FROM library WHERE id=?",(ident,));c.commit();c.close();return jsonify(ok=True)
@app.post("/api/tones")
def save_tone():
 x=request.get_json(force=True);ident=x.get("id") or str(uuid.uuid4());
 if not x.get("name") or not x.get("prompt"):return jsonify(error="Tone name and prompt are required"),400
 c=db();is_default=1 if x.get("is_default") else 0
 if is_default:c.execute("UPDATE tones SET is_default=0")
 c.execute("INSERT INTO tones(id,name,prompt,is_default) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,prompt=excluded.prompt,is_default=excluded.is_default",(ident,x["name"],x["prompt"],is_default));c.commit();c.close();return jsonify(ok=True)
@app.delete("/api/tones/<ident>")
def del_tone(ident): c=db();c.execute("DELETE FROM tones WHERE id=?",(ident,));c.execute("UPDATE tones SET is_default=1 WHERE id=(SELECT id FROM tones ORDER BY name LIMIT 1) AND NOT EXISTS(SELECT 1 FROM tones WHERE is_default=1)");c.commit();c.close();return jsonify(ok=True)
@app.put("/api/settings")
def settings():
 x=request.get_json(force=True);c=db();old=c.execute("SELECT * FROM settings WHERE id=1").fetchone();token=x.get("buffer_token","");token=old["buffer_token"] if token=="configured" else token;lm_token=x.get("lm_token","");lm_token=old["lm_token"] if lm_token=="configured" else lm_token
 comfy=(x.get("comfyui_url") or "http://host.docker.internal:8188").rstrip("/")
 if not comfy.startswith(("http://","https://")):return jsonify(error="ComfyUI URL must start with http:// or https://"),400
 c.execute("UPDATE settings SET lm_url=?,lm_model=?,temperature=?,max_tokens=?,buffer_token=?,buffer_channel=?,lm_token=?,facebook_channel=?,instagram_channel=?,public_url=?,comfyui_url=? WHERE id=1",(x["lm_url"].rstrip("/").removesuffix("/v1"),x["lm_model"],float(x["temperature"]),int(x["max_tokens"]),token,x.get("buffer_channel",""),lm_token,x.get("facebook_channel",""),x.get("instagram_channel",""),x.get("public_url","").rstrip("/"),comfy));c.commit();c.close();return jsonify(ok=True)
def extract_json(text):
 text=text.strip();text=text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
 try:return json.loads(text)
 except json.JSONDecodeError:
  a=text.find("{");b=text.rfind("}")
  if a>=0 and b>a:return json.loads(text[a:b+1])
  raise
@app.post("/api/generate")
def generate():
 x=request.get_json(force=True);count=max(1,min(10,int(x.get("count",1))));selected=x.get("coverage_ids",[]);tone_id=x.get("tone_id");platforms=x.get("platforms",[]);instagram_type=x.get("instagram_type","post");facebook_type=x.get("facebook_type","post");schedule_mode=x.get("schedule_mode","queue")
 if instagram_type not in ("post","story"):return jsonify(error="Instagram type must be Post or Story"),400
 if facebook_type not in ("post","story"):return jsonify(error="Facebook type must be Post or Story"),400
 if not platforms:return jsonify(error="Choose Facebook, Instagram, or both"),400
 if schedule_mode not in ("queue","custom"):return jsonify(error="Invalid scheduling choice"),400
 lib=rows(f"SELECT id,category,title,details,url,filename,image_url,event_date,start_time,end_time,location,recurrence,recurrence_days,recurrence_end FROM library WHERE id IN ({','.join('?'*len(selected))})",selected) if selected else []
 order={ident:i for i,ident in enumerate(selected)};lib.sort(key=lambda item:order.get(item["id"],9999));custom=(x.get("subject") or "").strip();topics=[{"subject":item["title"],"information":[item],"media_id":item["id"] if item.get("filename") or item.get("image_url") else ""} for item in lib]
 fallback=x.get("media_id","")
 if custom:topics.append({"subject":custom,"information":[],"media_id":fallback})
 if not topics:return jsonify(error="Add at least one saved item or custom topic to the queue"),400
 if count*len(topics)>30:return jsonify(error="This queue is limited to 30 drafts at a time"),400
 if "instagram" in platforms:
  missing=[topic["subject"] for topic in topics if not topic["media_id"]]
  if missing:return jsonify(error="Instagram requires an image for: "+", ".join(missing)),400
 tone=rows("SELECT prompt FROM tones WHERE id=?",(tone_id,));tone=tone[0]["prompt"] if tone else "Clear and conversational"
 s=rows("SELECT * FROM settings WHERE id=1")[0];start=datetime.fromisoformat(x["start"]) if schedule_mode=="custom" else datetime.now(timezone.utc);end=datetime.fromisoformat(x.get("end") or x["start"]) if schedule_mode=="custom" else start;span=(end-start).total_seconds()
 schema={"name":"social_posts","strict":True,"schema":{"type":"object","properties":{"posts":{"type":"array","items":{"type":"object","properties":{"caption":{"type":"string"}},"required":["caption"],"additionalProperties":False}}},"required":["posts"],"additionalProperties":False}}
 try:
  headers={"Authorization":"Bearer "+s["lm_token"]} if s["lm_token"] else {};queued=[]
  for topic in topics:
   prompt={"posts":count,"subject":topic["subject"],"tone":tone,"platforms":platforms,"additional_instructions":x.get("instructions",""),"selected_information":topic["information"]};payload={"model":s["lm_model"],"temperature":s["temperature"],"max_tokens":s["max_tokens"],"response_format":{"type":"json_schema","json_schema":schema},"messages":[{"role":"system","content":"Write exactly the requested count of distinct, finished social posts about this single subject. Use only its supplied facts. Do not mix in other events or programs. Use short paragraphs separated by blank lines, a separate call to action, and hashtags on a final line."},{"role":"user","content":json.dumps(prompt)}]};generated=None;last_error=""
   for attempt in range(2):
    r=requests.post(s["lm_url"]+"/v1/chat/completions",headers=headers,json=payload,timeout=300);raw=r.text
    if not r.ok:return jsonify(error=f"LM Studio {r.status_code}: {raw[:500]}"),502
    try:
     candidate=extract_json(r.json()["choices"][0]["message"]["content"])["posts"]
     if len(candidate)==count:generated=candidate;break
     last_error=f"Qwen returned {len(candidate)} posts; expected {count}"
    except (KeyError,ValueError,json.JSONDecodeError) as e:last_error=str(e)
   if generated is None:return jsonify(error=f"Qwen could not create posts for {topic['subject']}: {last_error}"),422
   queued.extend((str(p.get("caption","")).strip(),topic) for p in generated if str(p.get("caption","")).strip())
  c=db();created=[];total=len(queued)
  for i,(caption,topic) in enumerate(queued):
   when=start.timestamp()+(0 if total==1 else span*i/(total-1));scheduled=datetime.fromtimestamp(when,timezone.utc).isoformat();ident=str(uuid.uuid4());c.execute("INSERT INTO drafts(id,caption,scheduled_at,status,tone,subject,buffer_id,created_at,platforms,media_id,instagram_type,facebook_type,schedule_mode,information_json,instructions) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ident,caption,scheduled,"pending",tone,topic["subject"],None,datetime.now(timezone.utc).isoformat(),json.dumps(platforms),topic["media_id"],instagram_type,facebook_type,schedule_mode,json.dumps(topic["information"]),x.get("instructions","")));created.append(ident)
  c.commit();c.close();return jsonify(created=len(created))
 except requests.RequestException as e:return jsonify(error=f"Cannot reach LM Studio: {e}"),502
 except (KeyError,ValueError,json.JSONDecodeError) as e:return jsonify(error=f"Qwen response could not be parsed: {e}"),422
@app.put("/api/drafts/<ident>")
def edit_draft(ident): x=request.get_json(force=True);c=db();c.execute("UPDATE drafts SET caption=?,scheduled_at=? WHERE id=? AND status IN ('pending','ready')",(x["caption"],x["scheduled_at"],ident));c.commit();c.close();return jsonify(ok=True)
@app.post("/api/drafts/<ident>/reject")
def reject(ident): c=db();c.execute("UPDATE drafts SET status='rejected' WHERE id=?",(ident,));c.commit();c.close();return jsonify(ok=True)
@app.post("/api/drafts/<ident>/ready")
def ready(ident):
 c=db();changed=c.execute("UPDATE drafts SET status='ready' WHERE id=? AND status='pending'",(ident,)).rowcount;c.commit();c.close()
 return jsonify(ok=True) if changed else (jsonify(error="Draft not found or already approved"),404)
@app.post("/api/drafts/<ident>/unready")
def unready(ident):
 c=db();changed=c.execute("UPDATE drafts SET status='pending' WHERE id=? AND status='ready'",(ident,)).rowcount;c.commit();c.close()
 return jsonify(ok=True) if changed else (jsonify(error="Approved draft not found"),404)
@app.post("/api/drafts/<ident>/regenerate")
def regenerate(ident):
 c=db();d=c.execute("SELECT * FROM drafts WHERE id=?",(ident,)).fetchone();s=c.execute("SELECT * FROM settings WHERE id=1").fetchone();fallback_information=[dict(x) for x in c.execute("SELECT * FROM library WHERE title=?",(d["subject"],)).fetchall()] if d else [];c.close()
 if not d:return jsonify(error="Draft not found"),404
 try:
  saved_information=json.loads(d["information_json"] or "[]") or fallback_information;extra=(request.json.get("instructions","") if request.is_json else "").strip();prompt={"posts":1,"subject":d["subject"],"tone":d["tone"],"platforms":json.loads(d["platforms"] or '["facebook"]'),"additional_instructions":"\n".join(filter(None,[d["instructions"] or "",extra])),"selected_information":saved_information,"previous_caption":d["caption"]};schema={"name":"social_post","strict":True,"schema":{"type":"object","properties":{"caption":{"type":"string"}},"required":["caption"],"additionalProperties":False}}
  headers={"Authorization":"Bearer "+s["lm_token"]} if s["lm_token"] else {};r=requests.post(s["lm_url"]+"/v1/chat/completions",headers=headers,json={"model":s["lm_model"],"temperature":s["temperature"],"max_tokens":s["max_tokens"],"response_format":{"type":"json_schema","json_schema":schema},"messages":[{"role":"system","content":"Create one fresh, finished social post about the supplied subject. Use only the supplied facts, preserve important dates, times, locations, links, and calls to action, but do not merely paraphrase the previous caption. Use short paragraphs separated by blank lines, a separate call to action, and hashtags on a final line."},{"role":"user","content":json.dumps(prompt)}]},timeout=300);r.raise_for_status();caption=extract_json(r.json()["choices"][0]["message"]["content"])["caption"].strip();c=db();c.execute("UPDATE drafts SET caption=? WHERE id=?",(caption,ident));c.commit();c.close();return jsonify(ok=True)
 except Exception as e:return jsonify(error=str(e)),502
@app.post("/api/drafts/<ident>/approve")
def approve(ident):
 c=db();d=c.execute("SELECT * FROM drafts WHERE id=? AND status IN ('pending','ready')",(ident,)).fetchone();s=c.execute("SELECT * FROM settings WHERE id=1").fetchone()
 if not d:return jsonify(error="Draft not found"),404
 if not s["buffer_token"]:return jsonify(error="Configure the Buffer API key in Settings"),400
 platforms=json.loads(d["platforms"] or '["facebook"]');channels={"facebook":s["facebook_channel"] or s["buffer_channel"],"instagram":s["instagram_channel"]}
 missing=[p for p in platforms if not channels.get(p)]
 if missing:return jsonify(error="Configure Buffer channel ID for "+", ".join(missing)+" in Settings"),400
 media_url=""
 if d["media_id"]:
  item=c.execute("SELECT filename,image_url FROM library WHERE id=?",(d["media_id"],)).fetchone()
  if item and item["image_url"]:media_url=item["image_url"]
  elif item and item["filename"]:
   if not s["public_url"]:return jsonify(error="This post uses an uploaded image. Set the Public HTTPS address in Settings so Buffer can retrieve it, or save a direct public image URL with the Information item."),400
   media_url=s["public_url"].rstrip("/")+"/media/"+d["media_id"]
 if "instagram" in platforms and not media_url:return jsonify(error="Instagram requires an image"),400
 query="""mutation CreatePost($text:String!,$channel:ChannelId!,$due:DateTime,$mode:ShareMode!,$assets:[AssetInput!]!,$metadata:PostInputMetaData){createPost(input:{text:$text,channelId:$channel,schedulingType:automatic,mode:$mode,dueAt:$due,assets:$assets,metadata:$metadata}){... on PostActionSuccess{post{id text dueAt}} ... on MutationError{message}}}"""
 post_ids=[]
 for platform in platforms:
  metadata={"instagram":{"type":d["instagram_type"] or "post","shouldShareToFeed":True}} if platform=="instagram" else {"facebook":{"type":d["facebook_type"] or "post"}}
  variables={"text":d["caption"],"channel":channels[platform],"due":d["scheduled_at"] if d["schedule_mode"]=="custom" else None,"mode":"customScheduled" if d["schedule_mode"]=="custom" else "addToQueue","assets":[{"image":{"url":media_url}}] if media_url else [],"metadata":metadata}
  try:r=requests.post("https://api.buffer.com",headers={"Authorization":"Bearer "+s["buffer_token"]},json={"query":query,"variables":variables},timeout=60)
  except requests.RequestException as e:return jsonify(error=f"Could not reach Buffer: {e}"),502
  try:
   result=r.json();data=result.get("data") or {};post=data.get("createPost") or {};errors=result.get("errors") or [];error=post.get("message") or (errors[0].get("message") if errors else None)
  except (ValueError,AttributeError,IndexError):return jsonify(error=f"Buffer returned {r.status_code}: {r.text[:300]}"),502
  if not r.ok and not error:error=f"Buffer returned HTTP {r.status_code}"
  if error:return jsonify(error=f"{platform.title()}: {error}"),502
  post_ids.append(post.get("post",{}).get("id"))
 c.execute("UPDATE drafts SET status='approved',buffer_id=? WHERE id=?",(json.dumps(post_ids),ident));c.commit();c.close();return jsonify(ok=True)
@app.post("/api/drafts/send-ready")
def send_ready():
 ids=[x["id"] for x in rows("SELECT id FROM drafts WHERE status='ready' ORDER BY scheduled_at")];sent=[];failed=[]
 if not ids:return jsonify(error="No approved posts are waiting to be sent"),400
 for ident in ids:
  result=approve(ident);response,status=(result if isinstance(result,tuple) else (result,result.status_code))
  if status<400:sent.append(ident)
 else:failed.append({"id":ident,"error":(response.get_json(silent=True) or {}).get("error","Unknown error")})
 return jsonify(sent=len(sent),failed=failed)

ASSET_TYPES={"Mixed","Illustrations","Icons / symbols","Borders / frames","Background elements","Textures","Decorative shapes"}
VISUAL_STYLES={"Auto","Punk / DIY","Grunge","Horror comic","Retro","Tattoo / flash","Screen print","Woodcut / linocut","Clean vector","Zine / photocopy"}
COLOR_MODES={"Black only","Black + white","Limited color","Full color"}
NEGATIVE_ASSET_PROMPT="complete flyer, complete poster, poster layout, advertisement, card, mockup, scene, room, landscape, backdrop, rectangular illustration, full-canvas background, frame, border, text, letters, words, watermark, logo, photograph of printed art, white box, black box, checkerboard pattern"

def comfy_url():
 configured=os.getenv("COMFYUI_URL","").strip()
 if configured:return configured.rstrip("/")
 configured=rows("SELECT comfyui_url FROM settings WHERE id=1")[0].get("comfyui_url","").strip()
 return configured.rstrip("/") if configured else f"http://host.docker.internal:{os.getenv('COMFYUI_PORT','8188')}"

@app.get("/api/assets/health")
def asset_health():
 url=comfy_url()
 try:
  response=requests.get(url+"/system_stats",timeout=5);response.raise_for_status()
  return jsonify(ok=True,url=url,message="ComfyUI is connected")
 except requests.RequestException as exc:
  return jsonify(error=f"Cannot connect to ComfyUI at {url}. On the ComfyUI server, start it with --listen 0.0.0.0 --port 8188, then try again. ({exc})",url=url),503

def update_asset(ident,**values):
 if not values:return
 c=db();c.execute("UPDATE assets SET "+",".join(f"{key}=?" for key in values)+" WHERE id=?",(*values.values(),ident));c.commit();c.close()

def asset_prompt(user_prompt,asset_type,style,color,concept):
 exception=asset_type=="Background elements"
 isolation="full-canvas background is allowed" if exception else "isolated subject only, real transparent background, no environment, no canvas or rectangular background"
 return f"Standalone decorative graphic asset inspired by: {user_prompt}. Concept: {concept}. Asset type: {asset_type}. Visual style: {style}. Color mode: {color}. {isolation}. Bold readable silhouette, separated foreground, clean negative space, vector-friendly shapes, high contrast, minimal gradients, screen-print ready, individual artwork intended to be placed into another layout."

def concepts_for(prompt,asset_type):
 words=[word.strip(".,!?()[]").lower() for word in prompt.split() if len(word.strip(".,!?()[]"))>2]
 theme=" ".join(words[:5]) or "the requested theme"
 if asset_type=="Borders / frames":forms=["torn circular border","distressed corner frame","chain border","rough ink oval","ornamental side rails","broken star frame"]
 elif asset_type=="Textures":forms=["ink splatter overlay","torn paper distress","scratch marks","halftone dots","dry brush streaks","photocopy noise cluster"]
 elif asset_type=="Icons / symbols":forms=["bold emblem","simple symbolic mark","radiating icon","crossed-object symbol","distressed badge element","stencil pictogram"]
 else:forms=["hero character or object","bold emblematic object","dynamic hand-held object","creature or mascot","decorative motif","supporting symbol cluster"]
 return [f"{form} expressing {theme}" for form in forms]

def run_asset(ident):
 item=rows("SELECT * FROM assets WHERE id=?",(ident,))
 if not item:return
 item=item[0];folder=ASSETS/item["created_at"][:4]/item["created_at"][5:7]/ident;folder.mkdir(parents=True,exist_ok=True)
 original=folder/"original.png";transparent=folder/"transparent.png";svg=folder/"asset.svg"
 try:
  client=ComfyUIClient(comfy_url(),ROOT/"workflows"/"asset-generator.json",ROOT/"workflows"/"asset-generator.mapping.json")
  raw=client.generate(item["enhanced_prompt"],NEGATIVE_ASSET_PROMPT,item["seed"],on_status=lambda status:update_asset(ident,status=status))
  original.write_bytes(raw);update_asset(ident,original_path=str(original.relative_to(DATA)),status="isolating",transparency_status="processing")
  if item["asset_type"]=="Background elements":
   from PIL import Image
   Image.open(original).convert("RGBA").save(transparent,"PNG")
  else:isolate_background(original,transparent)
  update_asset(ident,transparent_path=str(transparent.relative_to(DATA)),transparency_status="complete",status="vectorizing",vector_status="processing")
  try:
   vectorize_png(transparent,svg);update_asset(ident,svg_path=str(svg.relative_to(DATA)),vector_status="complete",status="complete",error="")
  except Exception as exc:update_asset(ident,vector_status="failed",status="complete_png_only",error=f"SVG unavailable: {exc}")
 except Exception as exc:
  status="background_failed" if original.exists() else "failed"
  update_asset(ident,status=status,transparency_status="failed" if original.exists() else "pending",error=str(exc))

def start_asset(ident):threading.Thread(target=run_asset,args=(ident,),daemon=True).start()

def create_asset_records(payload,concepts,batch_id=None):
 now=datetime.now(timezone.utc).isoformat();batch_id=batch_id or str(uuid.uuid4());created=[];c=db()
 if not c.execute("SELECT 1 FROM asset_batches WHERE id=?",(batch_id,)).fetchone():c.execute("INSERT INTO asset_batches VALUES(?,?,?,?,?,?)",(batch_id,payload["prompt"],payload["asset_type"],payload["visual_style"],payload["color_mode"],now))
 for concept in concepts:
  ident=str(uuid.uuid4());seed=random.SystemRandom().randrange(1,2**63-1);enhanced=asset_prompt(payload["prompt"],payload["asset_type"],payload["visual_style"],payload["color_mode"],concept)
  c.execute("INSERT INTO assets(id,batch_id,user_prompt,enhanced_prompt,sub_prompt,asset_type,visual_style,color_mode,seed,workflow_id,created_at,status,transparency_status,vector_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ident,batch_id,payload["prompt"],enhanced,concept,payload["asset_type"],payload["visual_style"],payload["color_mode"],seed,"asset-generator",now,"queued","pending","pending"));created.append(ident)
 c.commit();c.close()
 for ident in created:start_asset(ident)
 return batch_id,created

@app.post("/api/assets/generate")
def generate_assets():
 x=request.get_json(force=True);prompt=str(x.get("prompt","")).strip()
 if not prompt or len(prompt)>2000:return jsonify(error="Describe the vibe or assets you need (maximum 2,000 characters)"),400
 payload={"prompt":prompt,"asset_type":x.get("asset_type","Mixed"),"visual_style":x.get("visual_style","Auto"),"color_mode":x.get("color_mode","Black + white")}
 if payload["asset_type"] not in ASSET_TYPES or payload["visual_style"] not in VISUAL_STYLES or payload["color_mode"] not in COLOR_MODES:return jsonify(error="Invalid asset settings"),400
 batch,created=create_asset_records(payload,concepts_for(prompt,payload["asset_type"]));return jsonify(batch_id=batch,created=created),202

@app.post("/api/assets/more")
def more_assets():
 x=request.get_json(force=True);batch=rows("SELECT * FROM asset_batches WHERE id=?",(x.get("batch_id"),))
 if not batch:return jsonify(error="Asset batch not found"),404
 b=batch[0];payload={"prompt":b["user_prompt"],"asset_type":b["asset_type"],"visual_style":b["visual_style"],"color_mode":b["color_mode"]};_,created=create_asset_records(payload,[c+f" variation {random.randrange(100,999)}" for c in concepts_for(b["user_prompt"],b["asset_type"])],b["id"]);return jsonify(created=created),202

@app.post("/api/assets/<ident>/regenerate")
def regenerate_asset(ident):
 item=rows("SELECT * FROM assets WHERE id=?",(ident,))
 if not item:return jsonify(error="Asset not found"),404
 a=item[0];payload={"prompt":a["user_prompt"],"asset_type":a["asset_type"],"visual_style":a["visual_style"],"color_mode":a["color_mode"]};_,created=create_asset_records(payload,[a["sub_prompt"]+" fresh composition"],a["batch_id"]);return jsonify(id=created[0]),202

@app.post("/api/assets/<ident>/favorite")
def favorite_asset(ident):
 c=db();changed=c.execute("UPDATE assets SET favorite=CASE favorite WHEN 1 THEN 0 ELSE 1 END WHERE id=?",(ident,)).rowcount;c.commit();c.close();return jsonify(ok=True) if changed else (jsonify(error="Asset not found"),404)

@app.delete("/api/assets/<ident>")
def delete_asset(ident):
 c=db();changed=c.execute("DELETE FROM assets WHERE id=?",(ident,)).rowcount;c.commit();c.close();return jsonify(ok=True) if changed else (jsonify(error="Asset not found"),404)

@app.get("/assets/<ident>/<kind>")
def asset_file(ident,kind):
 column={"png":"transparent_path","svg":"svg_path","original":"original_path"}.get(kind)
 if not column:return jsonify(error="Invalid asset file"),404
 item=rows(f"SELECT {column},sub_prompt FROM assets WHERE id=?",(ident,))
 if not item or not item[0][column]:return jsonify(error="Asset file unavailable"),404
 path=(DATA/item[0][column]).resolve()
 if DATA.resolve() not in path.parents:return jsonify(error="Invalid asset path"),403
 return send_file(path,as_attachment=request.args.get("download")=="1",download_name=f"social-copilot-asset-{ident[:8]}.{kind if kind!='original' else 'png'}")
@app.errorhandler(Exception)
def unexpected_error(error):
 app.logger.exception("Unhandled application error")
 return jsonify(error=f"Server error: {error}"),500
if __name__=="__main__":app.run(host="0.0.0.0",port=3000)
