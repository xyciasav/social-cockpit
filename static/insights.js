(()=>{
const $=selector=>document.querySelector(selector);
const escapeHtml=value=>String(value||'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const format=(value,unit)=>value==null?'—':unit==='percentage'?`${Number(value).toFixed(2)}%`:Intl.NumberFormat(undefined,{notation:Math.abs(value)>=10000?'compact':'standard',maximumFractionDigits:1}).format(value);
const trend=(current,prior)=>{if(!prior)return{label:current?'New this period':'No change',className:'neutral',percent:null};let change=(current-prior)/Math.abs(prior)*100;return{label:`${change>=0?'↑':'↓'} ${Math.abs(change).toFixed(1)}%`,className:change>0?'up':change<0?'down':'neutral',percent:change}};
const metricValue=(summary,key)=>summary.totals[key]??null;

async function loadInsights(){
 const status=$('#insights-status'),button=$('#refresh-insights');button.disabled=true;status.textContent='Loading Buffer metrics…';
 try{
  const response=await fetch(`/api/buffer-insights?days=${$('#insights-days').value}&platform=${$('#insights-platform').value}`),data=await response.json();
  if(!response.ok)throw Error(data.error||`Server ${response.status}`);
  render(data);
  const freshness=data.updatedAt?`Updated ${new Date(data.updatedAt).toLocaleString()}`:`${data.channels} connected channel${data.channels===1?'':'s'} · No metrics in this period`;
  status.textContent=data.warnings?.length?`${freshness} · Some details unavailable`:freshness;
 }catch(error){
  status.textContent=error.message;
  ['#insights-story','#insights-summary','#insights-chart','#insights-platforms','#insights-metrics','#insights-posts'].forEach(selector=>$(selector).innerHTML='');
 }finally{button.disabled=false}
}

function render(data){
 const current=data.current,prior=data.previous,reach=metricValue(current,'reach')??metricValue(current,'impressions'),priorReach=metricValue(prior,'reach')??metricValue(prior,'impressions');
 const cards=[
  {label:'Total engagements',value:current.derived.engagements,prior:prior.derived.engagements,source:'Social Cockpit calculation',primary:true},
  {label:'People reached',value:reach,prior:priorReach,source:'Buffer metric'},
  {label:'Engagement rate',value:current.derived.engagementRate,prior:prior.derived.engagementRate,unit:'percentage',source:'Social Cockpit calculation'},
  {label:'Posts published',value:current.postCount,prior:prior.postCount,source:'Buffer metric'},
  {label:'Avg. engagements / post',value:current.derived.averageEngagements,prior:prior.derived.averageEngagements,source:'Social Cockpit calculation'}
 ];
 $('#insights-summary').innerHTML=cards.map(card=>{const change=trend(card.value||0,card.prior||0);return`<article class="metric-card${card.primary?' primary':''}"><span class="metric-label">${card.label}</span><b class="metric-value">${format(card.value,card.unit)}</b><span class="metric-change ${change.className}">${change.label} vs prior</span><small class="metric-source">${card.source}</small></article>`}).join('');
 renderStories(data);renderChart(current,prior);renderPlatforms(data.platforms,current);renderMetrics(current,prior);renderPosts(current.posts);
}

function renderStories(data){
 const current=data.current,prior=data.previous,meta={...prior.metricMeta,...current.metricMeta};
 const growth=Object.keys(meta).map(key=>({key,change:trend(current.totals[key]||0,prior.totals[key]||0).percent})).filter(item=>item.change!=null&&item.change>0&&item.key!=='postcount').sort((a,b)=>b.change-a.change)[0];
 const platforms=Object.entries(data.platforms).sort((a,b)=>b[1].derived.engagements-a[1].derived.engagements),leader=platforms[0],total=current.derived.engagements||0;
 const stories=[];
 if(growth)stories.push(`<div class="story-card"><span class="story-icon">↑</span><span><b>${escapeHtml(meta[growth.key].name)} is gaining momentum</b><small>Up ${growth.change.toFixed(1)}% compared with the previous period.</small></span></div>`);
 if(platforms.length>1&&leader&&total)stories.push(`<div class="story-card secondary"><span class="story-icon">◎</span><span><b>${escapeHtml(leader[0])} drove the most engagement</b><small>${(leader[1].derived.engagements/total*100).toFixed(0)}% of total calculated engagements came from this channel.</small></span></div>`);
 $('#insights-story').innerHTML=stories.join('');
}

function renderChart(current,prior){
 const candidates=[['reach','Reach'],['impressions','Impressions'],['reactions','Reactions'],['shares','Shares'],['comments','Comments'],['clicks','Clicks'],['saves','Saves'],['views','Views']];
 const rows=candidates.filter(([key])=>current.totals[key]!=null||prior.totals[key]!=null).slice(0,6);
 if(!rows.length){$('#insights-chart').innerHTML='<div class="empty-insights">No comparison data is available yet.</div>';return}
 $('#insights-chart').innerHTML=rows.map(([key,label])=>{const now=current.totals[key]||0,old=prior.totals[key]||0,max=Math.max(now,old,1),change=trend(now,old);return`<div class="chart-row"><span class="chart-label"><b>${label}</b><small>${format(now)} now</small></span><span class="chart-bars"><span class="chart-track"><i class="chart-bar" style="width:${now/max*100}%"></i></span><span class="chart-track prior"><i class="chart-bar" style="width:${old/max*100}%"></i></span></span><span class="chart-change ${change.className}">${change.label}</span></div>`}).join('')+'<div class="chart-legend"><span><i></i>Current</span><span><i></i>Previous</span></div>';
}

function renderPlatforms(platforms,current){
 const total=current.derived.engagements||0;
 $('#insights-platforms').innerHTML=Object.entries(platforms).map(([name,summary])=>{const share=total?summary.derived.engagements/total*100:0;return`<article class="platform-panel ${name.toLowerCase()}"><div class="platform-heading"><h3>${escapeHtml(name)}</h3><b>${share.toFixed(0)}% of engagement</b></div><div class="share-track"><div class="share-fill" style="width:${share}%"></div></div><div class="platform-stats"><span><small>Posts</small><b>${format(summary.postCount)}</b></span><span><small>Engagements</small><b>${format(summary.derived.engagements)}</b></span><span><small>Eng. rate</small><b>${format(summary.derived.engagementRate,'percentage')}</b></span></div></article>`}).join('');
}

function renderMetrics(current,prior){
 const meta={...prior.metricMeta,...current.metricMeta},keys=Object.keys(meta).sort((a,b)=>(meta[a].name||a).localeCompare(meta[b].name||b));
 $('#insights-metrics').innerHTML=['Metric','Current','Previous','Change'].map(label=>`<div class="head">${label}</div>`).join('')+keys.map(key=>{const item=meta[key],now=current.totals[key]||0,old=prior.totals[key]||0,change=trend(now,old);return`<div class="metric-name"><b>${escapeHtml(item.name)}</b><small>${item.unit==='percentage'?'Rate':'Buffer metric'}</small></div><div>${format(now,item.unit)}</div><div>${format(old,item.unit)}</div><div class="table-change ${change.className}">${change.label}</div>`}).join('');
}

function renderPosts(posts){
 const card=$('#insights-post-card');card.hidden=!posts.length;
 $('#insights-posts').innerHTML=posts.map((post,index)=>`<article class="insight-post"><div class="rank">${String(index+1).padStart(2,'0')}</div><div><b>${escapeHtml(post.platform)}</b><p>${escapeHtml((post.text||'(No caption)').slice(0,260))}</p><small>${post.dueAt?new Date(post.dueAt).toLocaleString():''}${post.externalLink?` · <a href="${escapeHtml(post.externalLink)}" target="_blank" rel="noopener">View post</a>`:''}</small></div><div class="post-score"><b>${format(post.derivedEngagements)} engagements</b><small>${post.derivedEngagementRate==null?'Rate unavailable':`${format(post.derivedEngagementRate,'percentage')} calculated rate`}</small></div></article>`).join('');
}

$('#refresh-insights').onclick=loadInsights;$('#insights-days').onchange=loadInsights;$('#insights-platform').onchange=loadInsights;$('button[data-tab="insights"]').addEventListener('click',loadInsights);
})();
