import json, os, random, sqlite3, threading, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file
import requests
from urllib.parse import urlsplit, urlunsplit
from comfyui_client import ComfyUIClient, ComfyUIError
from asset_processing import isolate_background, vectorize_png

VERSION="1.15.0"; ROOT=Path(__file__).parent; DATA=Path(os.getenv("DATA_DIR",ROOT/"data")); UPLOADS=DATA/"uploads"; ASSETS=DATA/"generated-assets"; DB=DATA/"social-cockpit.db"
DATA.mkdir(exist_ok=True);UPLOADS.mkdir(exist_ok=True);ASSETS.mkdir(exist_ok=True)
app=Flask(__name__);app.config["MAX_CONTENT_LENGTH"]=25*1024*1024
def db(): c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def init():
 c=db();c.executescript("""
 CREATE TABLE IF NOT EXISTS library(id TEXT PRIMARY KEY,category TEXT NOT NULL,title TEXT NOT NULL,details TEXT,url TEXT,filename TEXT,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS tones(id TEXT PRIMARY KEY,name TEXT NOT NULL,prompt TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),lm_url TEXT NOT NULL,lm_model TEXT NOT NULL,temperature REAL NOT NULL,max_tokens INTEGER NOT NULL,buffer_token TEXT,buffer_channel TEXT,lm_token TEXT DEFAULT '');
 CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,caption TEXT NOT NULL,scheduled_at TEXT NOT NULL,status TEXT NOT NULL,tone TEXT,subject TEXT,buffer_id TEXT,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS library_media(id TEXT PRIMARY KEY,library_id TEXT NOT NULL,kind TEXT NOT NULL,value TEXT NOT NULL,filename TEXT,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS asset_batches(id TEXT PRIMARY KEY,user_prompt TEXT NOT NULL,asset_type TEXT NOT NULL,visual_style TEXT NOT NULL,color_mode TEXT NOT NULL,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL,user_prompt TEXT NOT NULL,enhanced_prompt TEXT NOT NULL,sub_prompt TEXT NOT NULL,asset_type TEXT NOT NULL,visual_style TEXT NOT NULL,color_mode TEXT NOT NULL,seed INTEGER NOT NULL,workflow_id TEXT NOT NULL,created_at TEXT NOT NULL,status TEXT NOT NULL,original_path TEXT,transparent_path TEXT,svg_path TEXT,transparency_status TEXT,vector_status TEXT,favorite INTEGER DEFAULT 0,error TEXT DEFAULT '');
 """)
 if "lm_token" not in [x[1] for x in c.execute("PRAGMA table_info(settings)").fetchall()]:c.execute("ALTER TABLE settings ADD COLUMN lm_token TEXT DEFAULT ''")
 settings_cols=[x[1] for x in c.execute("PRAGMA table_info(settings)").fetchall()]
 for column in ("facebook_channel","instagram_channel","public_url"):
  if column not in settings_cols:c.execute(f"ALTER TABLE settings ADD COLUMN {column} TEXT DEFAULT ''")
 if "comfyui_url" not in settings_cols:c.execute("ALTER TABLE settings ADD COLUMN comfyui_url TEXT DEFAULT 'http://host.docker.internal:8188'")
 if "insights_targets" not in settings_cols:c.execute("ALTER TABLE settings ADD COLUMN insights_targets TEXT DEFAULT '{}'")
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
def add_media(c,library_id,files,urls):
 now=datetime.now(timezone.utc).isoformat()
 for value in urls:
  value=web_url(value)
  if value:c.execute("INSERT INTO library_media VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),library_id,"url",value,None,now))
 for f in files:
  if not f or not f.filename:continue
  media_id=str(uuid.uuid4());name=Path(f.filename).name;f.save(UPLOADS/f"{media_id}-{name}");c.execute("INSERT INTO library_media VALUES(?,?,?,?,?,?)",(media_id,library_id,"upload","",name,now))
def media_for(library_id,c=None):
 owned=c is None;c=c or db();items=[dict(x) for x in c.execute("SELECT * FROM library_media WHERE library_id=? ORDER BY created_at,id",(library_id,)).fetchall()]
 old=c.execute("SELECT filename,image_url FROM library WHERE id=?",(library_id,)).fetchone()
 if old:
  if old["image_url"]:items.insert(0,{"id":"legacy-url","library_id":library_id,"kind":"url","value":old["image_url"],"filename":None})
  if old["filename"]:items.insert(0,{"id":"legacy-upload","library_id":library_id,"kind":"legacy","value":"","filename":old["filename"]})
 if owned:c.close()
 return items
def enrich_library(items):
 for item in items:item["media"]=media_for(item["id"])
 return items
def buffer_call(token,query,variables=None):
 r=requests.post("https://api.buffer.com",headers={"Authorization":"Bearer "+token},json={"query":query,"variables":variables or {}},timeout=60)
 try:result=r.json()
 except ValueError:raise ValueError(f"Buffer returned {r.status_code}: {r.text[:300]}")
 if not r.ok:raise ValueError((result.get("errors") or [{}])[0].get("message",f"Buffer returned HTTP {r.status_code}"))
 if result.get("errors"):raise ValueError(result["errors"][0].get("message","Buffer query failed"))
 return result.get("data") or {}
def metric_key(value): return "".join(ch.lower() for ch in (value or "") if ch.isalnum())
def summarize_insights(posts,start,end):
 selected=[];totals={};metric_meta={}
 for post in posts:
  try:published=datetime.fromisoformat((post.get("dueAt") or "").replace("Z","+00:00"))
  except ValueError:continue
  if not start <= published < end:continue
  item={**post,"metricValues":{}}
  for metric in post.get("metrics") or []:
   key=metric_key(metric.get("type") or metric.get("name"));value=float(metric.get("value") or 0)
   item["metricValues"][key]=value;totals[key]=totals.get(key,0)+value
   metric_meta[key]={"type":metric.get("type") or key,"name":metric.get("name") or metric.get("type") or key,"unit":metric.get("unit") or "count"}
  selected.append(item)
 count=len(selected);engagement_keys=("reactions","likes","comments","shares","saves","clicks","linkclicks")
 def first_metric(values,names):
  for name in names:
   if name in values:return values[name]
  return 0
 for item in selected:
  values=item["metricValues"];item["derivedEngagements"]=first_metric(values,("reactions","likes"))+sum(values.get(k,0) for k in engagement_keys[2:])
  denominator=first_metric(values,("reach","impressions"));item["derivedEngagementRate"]=(item["derivedEngagements"]/denominator*100) if denominator else None
 selected.sort(key=lambda x:(x["derivedEngagementRate"] if x["derivedEngagementRate"] is not None else -1,x["derivedEngagements"]),reverse=True)
 for key,meta in metric_meta.items():
  if meta["unit"]=="percentage" and count:totals[key]=totals[key]/count
 engagements=sum(x["derivedEngagements"] for x in selected);reach=first_metric(totals,("reach","impressions"))
 return {"postCount":count,"totals":totals,"metricMeta":metric_meta,"derived":{"engagements":engagements,"engagementRate":engagements/reach*100 if reach else None,"averageEngagements":engagements/count if count else 0,"postsPerWeek":count/max((end-start).total_seconds()/604800,1/7)},"posts":selected}
def fetch_buffer_metric_posts(token,organization_id,channel_ids,start_date,max_pages=10):
 query="""query Insights($organization:OrganizationId!,$channels:[ChannelId!]!,$start:DateTime!,$after:String){posts(first:100,after:$after,input:{organizationId:$organization,sort:[{field:dueAt,direction:desc}],filter:{status:[sent],channelIds:$channels,startDate:$start}}){edges{node{id text dueAt channelId externalLink metrics{type name value unit} metricsUpdatedAt}}pageInfo{endCursor hasNextPage}}}"""
 posts=[];cursor=None
 for _ in range(max_pages):
  data=buffer_call(token,query,{"organization":organization_id,"channels":channel_ids,"start":start_date.isoformat(),"after":cursor});connection=data.get("posts") or {}
  posts.extend(edge["node"] for edge in connection.get("edges") or []);page=connection.get("pageInfo") or {}
  if not page.get("hasNextPage"):break
  cursor=page.get("endCursor")
 return posts
def fetch_buffer_aggregate(token,organization_id,channel_ids,start,end):
 query="""query Aggregate($organization:OrganizationId!,$channels:[ChannelId!]!,$start:DateTime!,$end:DateTime!){aggregatedPostMetrics(input:{organizationId:$organization,channelIds:$channels,startDateTime:$start,endDateTime:$end}){metrics{type name value unit}metricsUpdatedAt}}"""
 return buffer_call(token,query,{"organization":organization_id,"channels":channel_ids,"start":start.isoformat(),"end":end.isoformat()}).get("aggregatedPostMetrics") or {}
def summarize_aggregates(groups,start,end):
 totals={};metric_meta={};percentage_values={};post_count=0
 for group in groups:
  metrics=group.get("metrics") or [];group_count=next((float(m.get("value") or 0) for m in metrics if metric_key(m.get("type"))=="postcount"),0)
  post_count+=group_count
  for metric in metrics:
   key=metric_key(metric.get("type") or metric.get("name"));value=float(metric.get("value") or 0);unit=metric.get("unit") or "count"
   metric_meta[key]={"type":metric.get("type") or key,"name":metric.get("name") or metric.get("type") or key,"unit":unit}
   if unit=="percentage":percentage_values.setdefault(key,[]).append((value,group_count))
   else:totals[key]=totals.get(key,0)+value
 for key,values in percentage_values.items():
  weight=sum(weight for _,weight in values);totals[key]=sum(value*weight for value,weight in values)/weight if weight else 0
 engagement_keys=("comments","shares","saves","clicks","linkclicks");engagements=(totals.get("reactions",totals.get("likes",0))+sum(totals.get(key,0) for key in engagement_keys))
 denominator=totals.get("reach") or totals.get("impressions") or 0
 return {"postCount":int(post_count),"totals":totals,"metricMeta":metric_meta,"derived":{"engagements":engagements,"engagementRate":engagements/denominator*100 if denominator else None,"averageEngagements":engagements/post_count if post_count else 0,"postsPerWeek":post_count/max((end-start).total_seconds()/604800,1/7)},"posts":[]}
@app.get("/")
def home(): return render_template("index.html",version=VERSION)
@app.get("/media/<ident>")
def media(ident):
 item=rows("SELECT filename FROM library WHERE id=?",(ident,))
 if not item or not item[0]["filename"]:return jsonify(error="Media not found"),404
 return send_file(UPLOADS/f"{ident}-{item[0]['filename']}")
@app.get("/media-file/<ident>")
def media_file(ident):
 item=rows("SELECT filename FROM library_media WHERE id=? AND kind='upload'",(ident,))
 if not item:return jsonify(error="Media not found"),404
 return send_file(UPLOADS/f"{ident}-{item[0]['filename']}")
@app.get("/api/state")
def state():
 s=rows("SELECT * FROM settings WHERE id=1")[0];s["buffer_token"]="" if not s["buffer_token"] else "configured";s["lm_token"]="" if not s["lm_token"] else "configured"
 return jsonify(version=VERSION,library=enrich_library(rows("SELECT * FROM library ORDER BY created_at DESC")),tones=rows("SELECT * FROM tones ORDER BY name"),drafts=rows("SELECT * FROM drafts WHERE status IN ('pending','ready') ORDER BY scheduled_at"),assets=rows("SELECT * FROM assets ORDER BY created_at DESC"),settings=s)
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
@app.get("/api/buffer-insights")
def buffer_insights():
 s=rows("SELECT * FROM settings WHERE id=1")[0]
 if not s["buffer_token"]:return jsonify(error="Configure the Buffer API key in Settings"),400
 try:days=max(1,min(365,int(request.args.get("days",30))))
 except ValueError:return jsonify(error="Days must be a number from 1 to 365"),400
 platform_filter=request.args.get("platform","all").lower()
 if platform_filter not in ("all","facebook","instagram"):return jsonify(error="Platform must be all, facebook, or instagram"),400
 end=datetime.now(timezone.utc);start=end.replace(microsecond=0)-timedelta(days=days);previous_start=start-timedelta(days=days)
 try:
  account=buffer_call(s["buffer_token"],"query { account { organizations { id name } } }");organizations=(account.get("account") or {}).get("organizations") or []
  if not organizations:return jsonify(error="Buffer returned no organizations for this API key"),502
  all_posts=[];channels={};query_errors=[];current_aggregates={"Facebook":[],"Instagram":[]};previous_aggregates={"Facebook":[],"Instagram":[]};aggregate_successes=0
  for organization in organizations:
   try:
    channel_data=buffer_call(s["buffer_token"],"query Channels($organization:OrganizationId!){channels(input:{organizationId:$organization}){id name displayName service}}",{"organization":organization["id"]})
    owned={"Facebook":[],"Instagram":[]}
    for channel in channel_data.get("channels") or []:
     service=str(channel.get("service") or "").lower()
     if service not in ("facebook","instagram") or (platform_filter!="all" and service!=platform_filter):continue
     platform="Facebook" if service=="facebook" else "Instagram";owned[platform].append(channel["id"]);channels[channel["id"]]=platform
    for platform,ids in owned.items():
     if not ids:continue
     try:
      current_aggregates[platform].append(fetch_buffer_aggregate(s["buffer_token"],organization["id"],ids,start,end));previous_aggregates[platform].append(fetch_buffer_aggregate(s["buffer_token"],organization["id"],ids,previous_start,start));aggregate_successes+=1
     except ValueError as e:query_errors.append(f"{organization.get('name') or organization['id']} {platform} metrics: {e}")
    channel_ids=[ident for ids in owned.values() for ident in ids]
    if channel_ids:
     try:all_posts.extend(fetch_buffer_metric_posts(s["buffer_token"],organization["id"],channel_ids,previous_start))
     except ValueError as e:query_errors.append(f"{organization.get('name') or organization['id']} top posts: {e}")
   except ValueError as e:query_errors.append(f"{organization.get('name') or organization['id']}: {e}")
  if not channels:
   detail="; ".join(query_errors) if query_errors else "No connected Facebook or Instagram channels were found"
   return jsonify(error=detail),502
  if query_errors and not aggregate_successes:return jsonify(error="Buffer could not load post metrics: "+"; ".join(query_errors)),502
  all_posts=list({post["id"]:post for post in all_posts}.values())
  for post in all_posts:post["platform"]=channels.get(post.get("channelId"),"Buffer")
  platforms={name:summarize_aggregates(current_aggregates[name],start,end) for name in sorted(set(channels.values()))}
  current=summarize_aggregates([group for values in current_aggregates.values() for group in values],start,end);previous=summarize_aggregates([group for values in previous_aggregates.values() for group in values],previous_start,start)
  current["posts"]=summarize_insights(all_posts,start,end)["posts"][:50]
  aggregate_groups=[group for values in current_aggregates.values() for group in values]
  updated_at=max([p.get("metricsUpdatedAt") or "" for p in all_posts]+[group.get("metricsUpdatedAt") or "" for group in aggregate_groups],default="") or None
  return jsonify(days=days,platform=platform_filter,start=start.isoformat(),end=end.isoformat(),updatedAt=updated_at,current=current,previous=previous,platforms=platforms,channels=len(channels),warnings=query_errors,experimental=True)
 except (requests.RequestException,ValueError,KeyError) as e:return jsonify(error=f"Could not load Buffer insights: {e}"),502
@app.route("/api/insights-targets",methods=["GET","PUT"])
def insights_targets():
 c=db();row=c.execute("SELECT insights_targets FROM settings WHERE id=1").fetchone()
 if request.method=="GET":
  c.close()
  try:return jsonify(targets=json.loads((row["insights_targets"] if row else "") or "{}"))
  except json.JSONDecodeError:return jsonify(targets={})
 values=request.get_json(force=True) or {};allowed=("engagements","reach","follows","clicks","posts");targets={}
 for key in allowed:
  try:value=float(values.get(key) or 0)
  except (TypeError,ValueError):c.close();return jsonify(error=f"{key.title()} target must be a number"),400
  if value<0:c.close();return jsonify(error="Targets cannot be negative"),400
  targets[key]=value
 c.execute("UPDATE settings SET insights_targets=? WHERE id=1",(json.dumps(targets),));c.commit();c.close();return jsonify(ok=True,targets=targets)
@app.post("/api/library")
def add_library():
 if request.content_type and "multipart" in request.content_type:
  ident=str(uuid.uuid4());record=(ident,request.form.get("category","Information"),request.form.get("title","").strip(),request.form.get("details",""),web_url(request.form.get("url")),None,datetime.now(timezone.utc).isoformat(),"",request.form.get("event_date",""),request.form.get("start_time",""),request.form.get("end_time",""),request.form.get("location",""),request.form.get("recurrence","one_time"),json.dumps(request.form.getlist("recurrence_day")),request.form.get("recurrence_end",""))
  if not record[2]:return jsonify(error="Title is required"),400
 else:
  x=request.get_json(force=True);record=(str(uuid.uuid4()),x.get("category","Information"),x.get("title","" ).strip(),x.get("details",""),x.get("url",""),None,datetime.now(timezone.utc).isoformat(),x.get("image_url",""),x.get("event_date",""),x.get("start_time",""),x.get("end_time",""),x.get("location",""),x.get("recurrence","one_time"),json.dumps(x.get("recurrence_days",[])),x.get("recurrence_end",""))
  if not record[2]:return jsonify(error="Title is required"),400
 c=db();c.execute("INSERT INTO library(id,category,title,details,url,filename,created_at,image_url,event_date,start_time,end_time,location,recurrence,recurrence_days,recurrence_end) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",record)
 if request.content_type and "multipart" in request.content_type:add_media(c,record[0],request.files.getlist("files") or request.files.getlist("file"),request.form.get("image_urls",request.form.get("image_url","")).splitlines())
 c.commit();c.close();return jsonify(ok=True)
@app.put("/api/library/<ident>")
def edit_library(ident):
 x=request.form;c=db();old=c.execute("SELECT * FROM library WHERE id=?",(ident,)).fetchone()
 if not old:return jsonify(error="Information not found"),404
 name=old["filename"]
 title=x.get("title","").strip()
 if not title:return jsonify(error="Title is required"),400
 c.execute("UPDATE library SET category=?,title=?,details=?,url=?,filename=?,image_url=?,event_date=?,start_time=?,end_time=?,location=?,recurrence=?,recurrence_days=?,recurrence_end=? WHERE id=?",(x.get("category","Information"),title,x.get("details",""),web_url(x.get("url")),name,old["image_url"],x.get("event_date",""),x.get("start_time",""),x.get("end_time",""),x.get("location",""),x.get("recurrence","one_time"),json.dumps(x.getlist("recurrence_day")),x.get("recurrence_end",""),ident));add_media(c,ident,request.files.getlist("files") or request.files.getlist("file"),x.get("image_urls","").splitlines());c.commit();c.close();return jsonify(ok=True)
@app.delete("/api/library/<library_id>/media/<media_id>")
def del_library_media(library_id,media_id):
 c=db();item=c.execute("SELECT * FROM library_media WHERE id=? AND library_id=?",(media_id,library_id)).fetchone()
 if not item and media_id in ("legacy-url","legacy-upload"):
  old=c.execute("SELECT filename FROM library WHERE id=?",(library_id,)).fetchone()
  if not old:c.close();return jsonify(error="Image not found"),404
  if media_id=="legacy-upload" and old["filename"]:(UPLOADS/f"{library_id}-{old['filename']}").unlink(missing_ok=True)
  c.execute("UPDATE library SET image_url='' WHERE id=?",(library_id,)) if media_id=="legacy-url" else c.execute("UPDATE library SET filename=NULL WHERE id=?",(library_id,));c.commit();c.close();return jsonify(ok=True)
 if not item:c.close();return jsonify(error="Image not found"),404
 c.execute("DELETE FROM library_media WHERE id=?",(media_id,));c.commit();c.close()
 if item["kind"]=="upload":(UPLOADS/f"{media_id}-{item['filename']}").unlink(missing_ok=True)
 return jsonify(ok=True)
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
 lib=enrich_library(rows(f"SELECT id,category,title,details,url,filename,image_url,event_date,start_time,end_time,location,recurrence,recurrence_days,recurrence_end FROM library WHERE id IN ({','.join('?'*len(selected))})",selected)) if selected else []
 order={ident:i for i,ident in enumerate(selected)};lib.sort(key=lambda item:order.get(item["id"],9999));custom=(x.get("subject") or "").strip();topics=[{"subject":item["title"],"information":[item],"media_id":item["id"] if item.get("media") else ""} for item in lib]
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
 media_urls=[]
 if d["media_id"]:
  for item in media_for(d["media_id"],c):
   if item["kind"]=="url":media_urls.append(item["value"])
   elif item["kind"]=="legacy":
    if not s["public_url"]:return jsonify(error="This post uses uploaded images. Set the Public HTTPS address in Settings so Buffer can retrieve them."),400
    media_urls.append(s["public_url"].rstrip("/")+"/media/"+d["media_id"])
   else:
    if not s["public_url"]:return jsonify(error="This post uses uploaded images. Set the Public HTTPS address in Settings so Buffer can retrieve them."),400
    media_urls.append(s["public_url"].rstrip("/")+"/media-file/"+item["id"])
 if "instagram" in platforms and not media_urls:return jsonify(error="Instagram requires an image"),400
 query="""mutation CreatePost($text:String!,$channel:ChannelId!,$due:DateTime,$mode:ShareMode!,$assets:[AssetInput!]!,$metadata:PostInputMetaData){createPost(input:{text:$text,channelId:$channel,schedulingType:automatic,mode:$mode,dueAt:$due,assets:$assets,metadata:$metadata}){... on PostActionSuccess{post{id text dueAt}} ... on MutationError{message}}}"""
 post_ids=[]
 for platform in platforms:
  metadata={"instagram":{"type":d["instagram_type"] or "post","shouldShareToFeed":True}} if platform=="instagram" else {"facebook":{"type":d["facebook_type"] or "post"}}
  variables={"text":d["caption"],"channel":channels[platform],"due":d["scheduled_at"] if d["schedule_mode"]=="custom" else None,"mode":"customScheduled" if d["schedule_mode"]=="custom" else "addToQueue","assets":[{"image":{"url":url}} for url in media_urls],"metadata":metadata}
  try:
   data=buffer_call(s["buffer_token"],query,variables);post=data.get("createPost") or {};error=post.get("message")
  except (requests.RequestException,ValueError,AttributeError,IndexError) as e:return jsonify(error=f"Could not reach Buffer: {e}"),502
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
NEGATIVE_ASSET_PROMPT="typography, text, readable text, gibberish text, letters, words, captions, labels, title, logo, complete flyer, complete poster, poster layout, advertisement, card, mockup, scene, room, landscape, backdrop, crowd, band lineup, multiple characters, group portrait, ground line, stage, rectangular illustration, full-canvas background, frame, border, photograph of printed art, white box, black box, checkerboard pattern"

def comfy_url():
 configured=rows("SELECT comfyui_url FROM settings WHERE id=1")[0].get("comfyui_url","").strip()
 if configured:return configured.rstrip("/")
 configured=os.getenv("COMFYUI_URL","").strip()
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
 isolation="full-canvas background is allowed" if exception else "ONE isolated subject only on a plain removable background, no environment, no scene, no floor or ground line, no canvas or rectangular background"
 return f"Create this exact standalone decorative asset: {concept}. Overall direction: {user_prompt}. Asset type: {asset_type}. Visual style: {style}. Color mode: {color}. {isolation}. No typography of any kind: no text, letters, words, title, logo, label, or fake writing. Do not make a flyer or poster. Do not add a crowd, band, extra characters, scenery, stage, frame, or surrounding composition. The requested subject must be the only focal object, centered with generous empty space around it. Preserve handmade character through distressed ink, rough photocopy texture, uneven screen-print edges, or expressive linework when appropriate. Strong silhouette, recognizable internal detail, clean negative space, limited shading, vector-friendly shapes, high contrast, screen-print ready. Artwork only, designed to be placed into another layout."

def concepts_for(prompt,asset_type):
 words=[word.strip(".,!?()[]").lower() for word in prompt.split() if len(word.strip(".,!?()[]"))>2]
 theme=" ".join(words[:5]) or "the requested theme"
 prompt_lower=prompt.lower()
 if "halloween" in prompt_lower:
  forms=["one skeleton guitarist in an energetic wide-legged pose","one bat with safety-pin wings","one skeletal hand gripping a wired microphone","one jack-o'-lantern with a liberty-spike mohawk","one upright coffin wrapped in a single broken chain","one dripping lightning bolt decorated with two tiny skull accents"]
 elif "protest" in prompt_lower or "civic" in prompt_lower or "politic" in prompt_lower:
  forms=["one raised fist gripping a torn ballot","one cracked megaphone with radiating ink lines","one distressed star wrapped in a chain","one hand holding a lightning-bolt placard with no writing","one flying dove carrying a safety pin","one bold voting-box symbol with a rough check mark"]
 elif asset_type=="Borders / frames":forms=["one torn circular border","one distressed corner frame","one chain border","one rough ink oval","one pair of ornamental side rails","one broken-star frame"]
 elif asset_type=="Textures":forms=["ink splatter overlay","torn paper distress","scratch marks","halftone dots","dry brush streaks","photocopy noise cluster"]
 elif asset_type=="Icons / symbols":forms=["one bold emblematic symbol","one simple hand-drawn icon","one radiating symbolic object","one pair of crossed thematic objects","one distressed badge-shaped symbol with no text","one stencil-style pictogram"]
 else:forms=["one expressive mascot holding a thematic object","one bold emblematic object","one hand gripping a thematic object","one distinctive creature or mascot","one decorative thematic motif","one compact symbolic object"]
 return [f"{form}, clearly expressing {theme}" for form in forms]

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
