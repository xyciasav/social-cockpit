import json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file
import requests

VERSION="1.7.0"; ROOT=Path(__file__).parent; DATA=Path(os.getenv("DATA_DIR",ROOT/"data")); UPLOADS=DATA/"uploads"; DB=DATA/"social-cockpit.db"
DATA.mkdir(exist_ok=True);UPLOADS.mkdir(exist_ok=True)
app=Flask(__name__);app.config["MAX_CONTENT_LENGTH"]=25*1024*1024
def db(): c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def init():
 c=db();c.executescript("""
 CREATE TABLE IF NOT EXISTS library(id TEXT PRIMARY KEY,category TEXT NOT NULL,title TEXT NOT NULL,details TEXT,url TEXT,filename TEXT,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS tones(id TEXT PRIMARY KEY,name TEXT NOT NULL,prompt TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),lm_url TEXT NOT NULL,lm_model TEXT NOT NULL,temperature REAL NOT NULL,max_tokens INTEGER NOT NULL,buffer_token TEXT,buffer_channel TEXT,lm_token TEXT DEFAULT '');
 CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,caption TEXT NOT NULL,scheduled_at TEXT NOT NULL,status TEXT NOT NULL,tone TEXT,subject TEXT,buffer_id TEXT,created_at TEXT NOT NULL);
 """)
 if "lm_token" not in [x[1] for x in c.execute("PRAGMA table_info(settings)").fetchall()]:c.execute("ALTER TABLE settings ADD COLUMN lm_token TEXT DEFAULT ''")
 settings_cols=[x[1] for x in c.execute("PRAGMA table_info(settings)").fetchall()]
 for column in ("facebook_channel","instagram_channel","public_url"):
  if column not in settings_cols:c.execute(f"ALTER TABLE settings ADD COLUMN {column} TEXT DEFAULT ''")
 draft_cols=[x[1] for x in c.execute("PRAGMA table_info(drafts)").fetchall()]
 if "platforms" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN platforms TEXT DEFAULT 'facebook'")
 if "media_id" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN media_id TEXT DEFAULT ''")
 if "instagram_type" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN instagram_type TEXT DEFAULT 'post'")
 if "facebook_type" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN facebook_type TEXT DEFAULT 'post'")
 if "schedule_mode" not in draft_cols:c.execute("ALTER TABLE drafts ADD COLUMN schedule_mode TEXT DEFAULT 'custom'")
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
 return jsonify(version=VERSION,library=rows("SELECT * FROM library ORDER BY created_at DESC"),tones=rows("SELECT * FROM tones ORDER BY name"),drafts=rows("SELECT * FROM drafts WHERE status='pending' ORDER BY scheduled_at"),settings=s)
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
 c.execute("UPDATE settings SET lm_url=?,lm_model=?,temperature=?,max_tokens=?,buffer_token=?,buffer_channel=?,lm_token=?,facebook_channel=?,instagram_channel=?,public_url=? WHERE id=1",(x["lm_url"].rstrip("/").removesuffix("/v1"),x["lm_model"],float(x["temperature"]),int(x["max_tokens"]),token,x.get("buffer_channel",""),lm_token,x.get("facebook_channel",""),x.get("instagram_channel",""),x.get("public_url","").rstrip("/")));c.commit();c.close();return jsonify(ok=True)
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
   when=start.timestamp()+(0 if total==1 else span*i/(total-1));scheduled=datetime.fromtimestamp(when,timezone.utc).isoformat();ident=str(uuid.uuid4());c.execute("INSERT INTO drafts(id,caption,scheduled_at,status,tone,subject,buffer_id,created_at,platforms,media_id,instagram_type,facebook_type,schedule_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(ident,caption,scheduled,"pending",tone,topic["subject"],None,datetime.now(timezone.utc).isoformat(),json.dumps(platforms),topic["media_id"],instagram_type,facebook_type,schedule_mode));created.append(ident)
  c.commit();c.close();return jsonify(created=len(created))
 except requests.RequestException as e:return jsonify(error=f"Cannot reach LM Studio: {e}"),502
 except (KeyError,ValueError,json.JSONDecodeError) as e:return jsonify(error=f"Qwen response could not be parsed: {e}"),422
@app.put("/api/drafts/<ident>")
def edit_draft(ident): x=request.get_json(force=True);c=db();c.execute("UPDATE drafts SET caption=?,scheduled_at=? WHERE id=? AND status='pending'",(x["caption"],x["scheduled_at"],ident));c.commit();c.close();return jsonify(ok=True)
@app.post("/api/drafts/<ident>/reject")
def reject(ident): c=db();c.execute("UPDATE drafts SET status='rejected' WHERE id=?",(ident,));c.commit();c.close();return jsonify(ok=True)
@app.post("/api/drafts/<ident>/regenerate")
def regenerate(ident):
 c=db();d=c.execute("SELECT * FROM drafts WHERE id=?",(ident,)).fetchone();s=c.execute("SELECT * FROM settings WHERE id=1").fetchone();c.close()
 if not d:return jsonify(error="Draft not found"),404
 try:
  headers={"Authorization":"Bearer "+s["lm_token"]} if s["lm_token"] else {};r=requests.post(s["lm_url"]+"/v1/chat/completions",headers=headers,json={"model":s["lm_model"],"temperature":s["temperature"],"max_tokens":s["max_tokens"],"messages":[{"role":"system","content":"Rewrite this social post with short paragraphs separated by blank lines, the call to action on its own line, and hashtags on a final separate line. Return only the revised caption."},{"role":"user","content":d["caption"]+"\nInstructions: "+(request.json.get("instructions","") if request.is_json else "")} ]},timeout=300);r.raise_for_status();caption=r.json()["choices"][0]["message"]["content"].strip();c=db();c.execute("UPDATE drafts SET caption=? WHERE id=?",(caption,ident));c.commit();c.close();return jsonify(ok=True)
 except Exception as e:return jsonify(error=str(e)),502
@app.post("/api/drafts/<ident>/approve")
def approve(ident):
 c=db();d=c.execute("SELECT * FROM drafts WHERE id=? AND status='pending'",(ident,)).fetchone();s=c.execute("SELECT * FROM settings WHERE id=1").fetchone()
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
@app.errorhandler(Exception)
def unexpected_error(error):
 app.logger.exception("Unhandled application error")
 return jsonify(error=f"Server error: {error}"),500
if __name__=="__main__":app.run(host="0.0.0.0",port=3000)
