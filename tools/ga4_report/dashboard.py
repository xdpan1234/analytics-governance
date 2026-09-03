from __future__ import annotations

import json
from html import escape
from typing import Any

from .contracts import ReportError


class DashboardRenderer:
    def __init__(self, view: str = "daily", sample: bool = False) -> None:
        if view not in {"daily", "investigate"}:
            raise ReportError("HTML view must be daily or investigate")
        self.view = view
        self.sample = sample

    def render(self, report: dict[str, Any]) -> str:
        period = report["period"]
        comparison = report.get("comparison_period")
        title = "GA4 决策型日报" if self.view == "daily" else "GA4 排障工作台"
        comparison_text = (
            f"对比 {comparison['start_date']}～{comparison['end_date']}"
            if comparison
            else "未设置对比周期"
        )
        payload = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
        return (
            _TEMPLATE.replace("__VIEW__", self.view)
            .replace("__TITLE__", escape(title))
            .replace("__START__", escape(period["start_date"]))
            .replace("__END__", escape(period["end_date"]))
            .replace("__COMPARISON__", escape(comparison_text))
            .replace("__SOURCE__", " · 固定样例数据" if self.sample else "")
            .replace("__REPORT_JSON__", payload)
        )


_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>__TITLE__</title>
  <style>
    :root{--ink:#172033;--muted:#667085;--line:#e4e8ef;--surface:#fff;--canvas:#f4f6fa;--blue:#315ee8;--blue-soft:#edf2ff;--red:#c8343d;--red-soft:#fff0f1;--amber:#b56809;--green:#137a48;--shadow:0 8px 28px rgba(24,35,60,.06)}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}button,select,a{font:inherit}button:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #9db7ff;outline-offset:2px}.skip{position:absolute;left:-9999px}.skip:focus{left:16px;top:12px;z-index:10;background:#fff;padding:8px 12px;border-radius:8px}.shell{max-width:1240px;margin:auto;padding:28px 24px 56px}.topbar{align-items:flex-start;display:flex;justify-content:space-between;gap:20px;margin-bottom:22px}.eyebrow{color:var(--blue);font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}h1,h2,h3,p{margin-top:0}h1{font-size:32px;letter-spacing:-.035em;margin:3px 0 5px}h2{font-size:19px;letter-spacing:-.02em;margin-bottom:3px}h3{font-size:14px;margin-bottom:3px}.subtle,.helper{color:var(--muted)}.subtle{margin:0}.nav{background:#e9edf5;border-radius:10px;display:flex;padding:4px}.nav a{border-radius:7px;color:var(--muted);font-weight:700;padding:8px 12px;text-decoration:none}.nav a.active{background:#fff;color:var(--ink);box-shadow:0 1px 3px rgba(20,30,50,.12)}
    .panel,.metric{background:var(--surface);border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow)}.filters{align-items:end;display:flex;flex-wrap:wrap;gap:12px;padding:14px 16px}.field{display:grid;gap:5px;min-width:158px}.field label{color:var(--muted);font-size:12px;font-weight:700}.field select{appearance:none;background:#fff;border:1px solid #ccd3df;border-radius:8px;color:var(--ink);height:40px;padding:0 34px 0 10px}.date-chip{background:#f7f9fc;border:1px solid var(--line);border-radius:8px;color:var(--muted);padding:9px 11px}.filter-note{color:var(--muted);font-size:12px;margin:0 0 10px auto}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:16px}.metric{padding:16px 18px}.metric span{color:var(--muted);display:block}.metric strong{display:block;font-size:28px;letter-spacing:-.03em;margin:2px 0}.metric small{color:var(--muted)}.metric .bad{color:var(--red)}.metric .good{color:var(--green)}
    .decision{align-items:center;display:flex;gap:13px;margin-top:16px;padding:15px 18px}.decision .signal{border-radius:50%;height:11px;width:11px}.decision.bad{background:var(--red-soft);border-color:#f5cbd0}.decision.bad .signal{background:var(--red)}.decision.good{background:#edf8f2;border-color:#caead8}.decision.good .signal{background:var(--green)}.decision.neutral .signal{background:#98a2b3}.decision strong{display:block}.decision p{margin:1px 0 0}.section{margin-top:24px}.section-head{align-items:end;display:flex;justify-content:space-between;gap:16px;margin-bottom:11px}.section-head p{margin:0}.grid-2{display:grid;grid-template-columns:minmax(0,1.22fr) minmax(330px,.78fr);gap:13px}.chart{min-height:330px;padding:18px}.chart-head{align-items:start;display:flex;justify-content:space-between;gap:12px;margin-bottom:17px}.chart-head strong{font-size:20px;font-variant-numeric:tabular-nums}.ranking{display:grid;gap:9px}.rank-row{align-items:center;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px}.rank{appearance:none;background:transparent;border:0;color:inherit;cursor:pointer;display:grid;gap:5px;padding:3px 0;text-align:left;width:100%}.rank-label{display:flex;justify-content:space-between;gap:12px}.rank-label code{overflow:hidden;text-overflow:ellipsis}.rank-label span{color:var(--muted);font-variant-numeric:tabular-nums}.track{background:#edf0f5;border-radius:4px;height:10px;overflow:hidden}.track>span{background:var(--blue);border-radius:inherit;display:block;height:100%;min-width:2px}.rank[aria-pressed=true] .track>span{background:var(--red)}.drill{color:var(--blue);font-size:12px;font-weight:700;text-decoration:none;white-space:nowrap}
    .donut-layout{align-items:center;display:grid;gap:18px;grid-template-columns:170px minmax(0,1fr);min-height:240px}.donut{align-items:center;background:#e9edf3;border-radius:50%;display:flex;height:164px;justify-content:center;margin:auto;position:relative;width:164px}.donut:after{background:#fff;border-radius:50%;content:"";height:98px;position:absolute;width:98px}.donut-center{font-size:11px;position:relative;text-align:center;z-index:1}.donut-center strong{display:block;font-size:23px}.legend{display:grid;gap:8px;list-style:none;margin:0;padding:0}.legend li{align-items:center;display:grid;gap:7px;grid-template-columns:10px minmax(0,1fr) auto}.swatch{border-radius:2px;height:10px;width:10px}.legend span:last-child{color:var(--muted);font-variant-numeric:tabular-nums}.hours{align-items:end;display:grid;grid-template-columns:repeat(24,minmax(8px,1fr));gap:5px;height:190px;padding-top:18px}.hour{align-items:center;display:flex;flex-direction:column;height:100%;justify-content:end}.hour-bar{background:#a9bdf7;border-radius:4px 4px 2px 2px;min-height:2px;width:100%}.hour.hot .hour-bar{background:var(--red)}.hour span{color:var(--muted);font-size:10px;height:16px;margin-top:6px}.heatmap{display:grid;grid-template-columns:repeat(12,minmax(42px,1fr));gap:7px}.heat{align-items:center;background:var(--blue-soft);border-radius:7px;display:flex;flex-direction:column;justify-content:center;min-height:55px}.heat strong{font-size:16px}.heat span{color:var(--muted);font-size:10px}.empty{color:var(--muted);padding:42px 12px;text-align:center}
    .flow{padding:18px}.flow-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0}.mini{background:#f7f9fc;border:1px solid var(--line);border-radius:9px;padding:12px}.mini span{color:var(--muted);display:block;font-size:12px}.mini strong{display:block;font-size:18px;margin-top:2px}.compare{display:grid;gap:10px}.compare-row{align-items:center;display:grid;gap:10px;grid-template-columns:46px minmax(0,1fr) 82px}.compare-row span:last-child{text-align:right}.table-wrap{overflow:auto}.table-wrap table{border-collapse:collapse;min-width:650px;width:100%}th,td{border-bottom:1px solid var(--line);padding:12px 15px;text-align:left}thead th{background:#f8fafc;color:var(--muted);font-size:12px}tbody tr:last-child th,tbody tr:last-child td{border-bottom:0}.numeric{font-variant-numeric:tabular-nums;white-space:nowrap}code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}.badge{background:var(--blue-soft);border-radius:999px;color:var(--blue);display:inline-block;font-size:11px;padding:2px 7px}.quality{padding:16px 18px}.quality ul{margin:0;padding-left:19px}.quality li{margin:4px 0}.quality .ok{color:var(--green)}footer{color:var(--muted);font-size:11px;margin-top:26px}
    body[data-view="daily"] .investigate-only,body[data-view="investigate"] .daily-only{display:none!important}
    @media(max-width:900px){.metrics{grid-template-columns:repeat(2,1fr)}.grid-2{grid-template-columns:1fr}.heatmap{grid-template-columns:repeat(8,1fr)}}
    @media(max-width:620px){.shell{padding:20px 13px 40px}.topbar{display:grid}h1{font-size:26px}.nav{width:max-content}.field{min-width:calc(50% - 6px);flex:1}.date-chip{width:100%}.filter-note{margin:0}.metrics,.flow-summary{grid-template-columns:1fr 1fr}.donut-layout{grid-template-columns:1fr}.chart{padding:15px;min-height:0}.hours{gap:2px}.hour span{font-size:8px}.heatmap{grid-template-columns:repeat(4,1fr)}}
    @media(max-width:380px){.metrics,.flow-summary{grid-template-columns:1fr}.field{min-width:100%}}
  </style>
</head>
<body data-view="__VIEW__">
  <a class="skip" href="#content">跳到主要内容</a>
  <div class="shell">
    <header class="topbar">
      <div><div class="eyebrow">GA4 reliability</div><h1>__TITLE__</h1><p class="subtle">统计周期 __START__～__END__ · __COMPARISON____SOURCE__</p></div>
      <nav class="nav" aria-label="报告视图"><a id="daily-nav" href="daily.html">决策型日报</a><a id="investigate-nav" href="investigate.html">排障工作台</a></nav>
    </header>
    <main id="content">
      <section class="panel filters" aria-label="报告筛选">
        <span class="date-chip">__START__～__END__</span>
        <div class="field daily-only"><label for="domain-filter">业务域</label><select id="domain-filter"><option value="all">全部业务域</option></select></div>
        <div class="field daily-only"><label for="outcome-filter">异常类型</label><select id="outcome-filter"><option value="all">全部类型</option></select></div>
        <div class="field investigate-only"><label for="investigate-event">异常事件</label><select id="investigate-event"></select></div>
        <div class="field"><label for="platform-filter">平台</label><select id="platform-filter"><option value="all">全部平台</option></select></div>
        <div class="field"><label for="version-filter">版本</label><select id="version-filter"><option value="all">全部版本</option></select></div>
        <p class="filter-note">筛选会写入网址；日期由生成命令决定。</p>
      </section>

      <section class="daily-only metrics" id="daily-metrics" aria-label="日报总体指标" aria-live="polite"></section>
      <section class="daily-only panel decision" id="decision" aria-live="polite"><span class="signal"></span><div><strong id="decision-title">正在判断</strong><p class="helper" id="decision-copy"></p></div></section>

      <section class="daily-only section">
        <div class="section-head"><div><h2>需要关注的异常</h2><p class="helper">优先展示新出现和较上期恶化的事件；点击事件联动原因与趋势。</p></div></div>
        <div class="grid-2">
          <article class="panel chart"><div class="chart-head"><div><h3>异常事件排行</h3><p class="helper">异常次数与较上期变化</p></div><strong id="ranking-total">—</strong></div><div class="ranking" id="event-ranking"></div></article>
          <article class="panel chart" aria-live="polite"><div class="chart-head"><div><h3>当前事件原因占比</h3><p class="helper" id="daily-event-name">—</p></div><strong id="daily-coverage">—</strong></div><div class="donut-layout"><div class="donut" id="daily-donut"><div class="donut-center"><strong id="daily-donut-total">—</strong><span>异常次数</span></div></div><ul class="legend" id="daily-legend"></ul></div></article>
        </div>
      </section>
      <section class="daily-only section"><div class="section-head"><div><h2>小时趋势</h2><p class="helper">当前事件按小时分布，帮助判断是否集中爆发。</p></div><a class="drill" id="daily-drill" href="investigate.html">进入排障工作台 →</a></div><article class="panel chart"><div class="hours" id="daily-hours"></div></article></section>

      <section class="investigate-only metrics" id="investigate-metrics" aria-label="事件指标" aria-live="polite"></section>
      <section class="investigate-only section">
        <div class="section-head"><div><h2 id="workbench-event">事件排障</h2><p class="helper">从时间、原因、流程分母和版本分布逐层定位。</p></div></div>
        <div class="grid-2">
          <article class="panel chart"><div class="chart-head"><div><h3>时间热区</h3><p class="helper">颜色越深表示该小时异常越集中</p></div><strong id="peak-hour">—</strong></div><div class="heatmap" id="heatmap"></div></article>
          <article class="panel chart"><div class="chart-head"><div><h3>原因占比</h3><p class="helper" id="reason-dimension">—</p></div><strong id="investigate-coverage">—</strong></div><div class="donut-layout"><div class="donut" id="investigate-donut"><div class="donut-center"><strong id="investigate-donut-total">—</strong><span>异常次数</span></div></div><ul class="legend" id="investigate-legend"></ul></div></article>
        </div>
      </section>
      <section class="investigate-only section"><div class="section-head"><div><h2>业务流程可靠性</h2><p class="helper">有明确成功或评估分母时才展示结果率。</p></div></div><article class="panel flow" id="flow"></article></section>
      <section class="investigate-only section"><div class="section-head"><div><h2>平台与版本定位</h2><p class="helper">按异常次数排序；用户数为 GA4 各上下文口径。</p></div></div><div class="panel table-wrap"><table><thead><tr><th scope="col">平台</th><th scope="col">应用版本</th><th scope="col">异常次数</th><th scope="col">影响用户</th><th scope="col">占比</th></tr></thead><tbody id="context-table"></tbody></table></div></section>
      <section class="investigate-only section"><div class="section-head"><div><h2>原因明细</h2><p class="helper">仅展示 Schema 已批准的低基数原因值。</p></div></div><div class="panel table-wrap"><table><thead><tr><th scope="col">原因</th><th scope="col">异常次数</th><th scope="col">占比</th><th scope="col">主要平台 / 版本</th></tr></thead><tbody id="reason-table"></tbody></table></div></section>

      <section class="daily-only section"><details class="panel"><summary style="cursor:pointer;font-weight:700;padding:15px 18px">数据质量</summary><div class="quality"><ul id="quality"></ul></div></details></section>
    </main>
    <footer id="footer"></footer>
  </div>
  <script type="application/json" id="report-data">__REPORT_JSON__</script>
  <script>
  (()=>{
    const report=JSON.parse(document.getElementById("report-data").textContent),events=report.events||[],view=document.body.dataset.view;
    const $=id=>document.getElementById(id),fmt=n=>new Intl.NumberFormat("zh-CN").format(n??0),pct=n=>n==null?"不可用":`${(n*100).toFixed(1)}%`;
    const labels={failed:"失败",blocked:"阻断",degraded:"降级",invalidated:"失效"},colors=["#315ee8","#c8343d","#b56809","#137a48","#7656c8","#5796a3"];
    const make=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!=null)node.textContent=text;return node};
    const params=new URLSearchParams(location.search),platform=$("platform-filter"),version=$("version-filter"),domain=$("domain-filter"),outcome=$("outcome-filter"),eventSelect=$("investigate-event");
    const domainOf=e=>e.event_name.split("_")[0],allContexts=events.flatMap(e=>e.contexts||[]),unique=values=>[...new Set(values.filter(Boolean))].sort();
    const option=(select,value,label=value)=>{const item=make("option","",label);item.value=value;select.append(item)};
    unique(allContexts.map(x=>x.platform)).forEach(x=>option(platform,x));unique(allContexts.map(x=>x.app_version)).forEach(x=>option(version,x));
    unique(events.map(domainOf)).forEach(x=>option(domain,x));unique(events.map(x=>x.outcome_type)).forEach(x=>option(outcome,x,labels[x]||x));events.forEach(x=>option(eventSelect,x.event_name));
    const setInitial=(select,name)=>{const requested=params.get(name);if([...select.options].some(x=>x.value===requested))select.value=requested};
    setInitial(platform,"platform");setInitial(version,"version");setInitial(domain,"domain");setInitial(outcome,"outcome");setInitial(eventSelect,"event");
    const matches=x=>(platform.value==="all"||x.platform===platform.value)&&(version.value==="all"||x.app_version===version.value),contextFiltered=()=>platform.value!=="all"||version.value!=="all";
    const countFor=(event,previous=false)=>{if(!contextFiltered())return previous?(event.event_count.previous??0):(event.event_count.value??0);return (previous?(event.previous_contexts||[]):(event.contexts||[])).filter(matches).reduce((sum,x)=>sum+x.event_count,0)};
    const usersFor=event=>contextFiltered()?(event.contexts||[]).filter(matches).reduce((sum,x)=>sum+x.affected_users,0):(event.affected_users.value??0);
    const reasonCount=reason=>contextFiltered()?(reason.contexts||[]).filter(matches).reduce((sum,x)=>sum+x.event_count,0):reason.event_count;
    const reasonsFor=event=>(event.reasons.items||[]).map(x=>({...x,filtered_count:reasonCount(x)})).filter(x=>x.filtered_count>0).sort((a,b)=>b.filtered_count-a.filtered_count);
    const hoursFor=event=>{const result=Array(24).fill(0);(event.timeline||[]).filter(matches).forEach(x=>result[Number(x.date_hour.slice(-2))]+=x.event_count);return result};
    const deltaFor=event=>{const previous=countFor(event,true),current=countFor(event);return previous?((current-previous)/previous):(current?null:0)};
    const sync=eventName=>{const url=new URL(location.href);[["platform",platform.value],["version",version.value],["event",eventName]].forEach(([key,value])=>value&&value!=="all"?url.searchParams.set(key,value):url.searchParams.delete(key));if(view==="daily")[["domain",domain.value],["outcome",outcome.value]].forEach(([key,value])=>value!=="all"?url.searchParams.set(key,value):url.searchParams.delete(key));history.replaceState(null,"",url)};
    const deepLink=eventName=>{const url=new URL("investigate.html",location.href);url.searchParams.set("event",eventName);if(platform.value!=="all")url.searchParams.set("platform",platform.value);if(version.value!=="all")url.searchParams.set("version",version.value);return url.href};
    const metric=(label,value,note,tone="")=>{const card=make("article","metric"),strong=make("strong",tone,value);card.append(make("span","",label),strong,make("small","",note));return card};
    const renderDonut=(prefix,total,reasons,status)=>{const donut=$(`${prefix}-donut`),legend=$(`${prefix}-legend`),segments=reasons.map(x=>({name:x.reason,count:x.filtered_count})),covered=segments.reduce((s,x)=>s+x.count,0);if(status==="available"&&total>covered)segments.push({name:"未上报或未批准",count:total-covered,missing:true});legend.replaceChildren();let offset=0;const stops=[];segments.forEach((segment,index)=>{const start=total?offset/total*100:0;offset+=segment.count;const end=total?offset/total*100:0,color=segment.missing?"#d2d7e0":colors[index%colors.length];stops.push(`${color} ${start}% ${end}%`);const row=make("li"),swatch=make("span","swatch");swatch.style.background=color;row.append(swatch,make("span","",segment.name),make("span","",`${fmt(segment.count)} · ${total?(segment.count/total*100).toFixed(1):"0.0"}%`));legend.append(row)});if(!segments.length){stops.push("#e9edf3 0 100%");legend.append(make("li","helper",status==="available"?"暂无已批准原因":"原因维度不可用"))}donut.style.background=`conic-gradient(${stops.join(",")})`;$(`${prefix}-donut-total`).textContent=fmt(total);return total?covered/total:null};
    const renderHours=(root,event,heat=false)=>{const hours=hoursFor(event),max=Math.max(...hours,1),peak=hours.indexOf(Math.max(...hours));root.replaceChildren();hours.forEach((value,hour)=>{if(heat){const cell=make("div","heat");cell.style.background=`color-mix(in srgb, var(--red) ${Math.round(value/max*72)}%, var(--blue-soft))`;cell.setAttribute("aria-label",`${hour} 时，${fmt(value)} 次`);cell.append(make("strong","",fmt(value)),make("span","",`${String(hour).padStart(2,"0")}:00`));root.append(cell)}else{const cell=make("div",`hour ${hour===peak&&value?"hot":""}`),bar=make("div","hour-bar");bar.style.height=`${Math.max(2,value/max*100)}%`;cell.setAttribute("aria-label",`${hour} 时，${fmt(value)} 次`);cell.title=`${String(hour).padStart(2,"0")}:00 · ${fmt(value)} 次`;cell.append(bar,make("span","",hour%3===0?String(hour):""));root.append(cell)}});return {peak,value:hours[peak]||0}};
    function renderDaily(){
      const visible=events.filter(e=>(domain.value==="all"||domainOf(e)===domain.value)&&(outcome.value==="all"||e.outcome_type===outcome.value)&&countFor(e)>0).sort((a,b)=>{const ad=deltaFor(a),bd=deltaFor(b);return (bd===null?1:bd>0?2:0)-(ad===null?1:ad>0?2:0)||countFor(b)-countFor(a)}),total=visible.reduce((s,e)=>s+countFor(e),0),previous=visible.reduce((s,e)=>s+countFor(e,true),0),affected=(domain.value==="all"&&outcome.value==="all"&&!contextFiltered())?report.summary.affected_users.value:visible.reduce((s,e)=>s+usersFor(e),0),worse=visible.filter(e=>deltaFor(e)===null||deltaFor(e)>0).length,covered=visible.reduce((s,e)=>s+reasonsFor(e).reduce((n,r)=>n+r.filtered_count,0),0),delta=previous?(total-previous)/previous:(total?null:0);
      const metrics=$("daily-metrics");metrics.replaceChildren(metric("异常次数",fmt(total),previous?`上期 ${fmt(previous)} · ${delta>=0?"+":""}${(delta*100).toFixed(1)}%`:total?"上期为 0 · 新出现":"与上期持平",delta===null||delta>0?"bad":"good"),metric(domain.value==="all"&&outcome.value==="all"&&!contextFiltered()?"影响用户":"影响用户*",fmt(affected),domain.value==="all"&&outcome.value==="all"&&!contextFiltered()?"跨事件去重":"筛选后按事件口径汇总"),metric("恶化事件",fmt(worse),`共 ${visible.length} 个异常事件`,worse?"bad":"good"),metric("原因覆盖率",pct(total?covered/total:null),`${fmt(covered)} / ${fmt(total)}`));
      const decision=$("decision");decision.className=`daily-only panel decision ${delta===null||delta>0?"bad":delta<0?"good":"neutral"}`;$("decision-title").textContent=delta===null?"需要关注：出现新的异常量":delta>0?`需要关注：异常较上期上升 ${(delta*100).toFixed(1)}%`:delta<0?`整体改善：异常较上期下降 ${Math.abs(delta*100).toFixed(1)}%`:"整体稳定：异常量与上期持平";$("decision-copy").textContent=worse?`${worse} 个事件出现恶化或新发，建议先看排行首位。`:"当前筛选范围内未发现恶化事件。";
      const ranking=$("event-ranking");ranking.replaceChildren();$("ranking-total").textContent=`${fmt(total)} 次`;const selected=visible.find(e=>e.event_name===params.get("event"))||visible[0];if(!selected){ranking.append(make("p","empty","当前筛选范围没有异常事件"));renderDonut("daily",0,[],"available");$("daily-event-name").textContent="暂无事件";$("daily-coverage").textContent="—";$("daily-hours").replaceChildren(make("p","empty","暂无小时趋势"));sync("");return}const max=Math.max(...visible.map(countFor),1);visible.slice(0,12).forEach(event=>{const row=make("div","rank-row"),button=make("button","rank"),label=make("div","rank-label"),track=make("div","track"),fill=make("span"),change=deltaFor(event);button.type="button";button.dataset.event=event.event_name;button.setAttribute("aria-pressed",String(event.event_name===selected.event_name));label.append(make("code","",event.event_name),make("span",change===null?`${fmt(countFor(event))} · 新出现`:`${fmt(countFor(event))} · ${change>=0?"+":""}${(change*100).toFixed(1)}%`));fill.style.width=`${countFor(event)/max*100}%`;track.append(fill);button.append(label,track);const link=make("a","drill","排障 →");link.href=deepLink(event.event_name);row.append(button,link);ranking.append(row)});
      const reasons=reasonsFor(selected),coverage=renderDonut("daily",countFor(selected),reasons,selected.reasons.status);$("daily-event-name").textContent=selected.event_name;$("daily-coverage").textContent=`覆盖率 ${pct(coverage)}`;renderHours($("daily-hours"),selected);$("daily-drill").href=deepLink(selected.event_name);sync(selected.event_name);ranking.onclick=event=>{const button=event.target.closest("button[data-event]");if(button){params.set("event",button.dataset.event);renderDaily()}};
    }
    function renderInvestigation(){
      const selected=events.find(e=>e.event_name===eventSelect.value)||events[0];if(!selected){$("workbench-event").textContent="本期没有异常事件";$("investigate-metrics").replaceChildren(metric("异常次数","0","本期无异常"),metric("影响用户","0","本期无异常"),metric("结果率","—","没有可计算事件"),metric("原因覆盖率","—","没有可计算事件"));$("heatmap").replaceChildren(make("p","empty","暂无小时数据"));$("peak-hour").textContent="暂无峰值";renderDonut("investigate",0,[],"available");$("investigate-coverage").textContent="覆盖率 —";$("flow").replaceChildren(make("p","empty","暂无可计算的业务流程"));[["context-table",5,"暂无平台 / 版本数据"],["reason-table",4,"暂无原因数据"]].forEach(([id,columns,text])=>{const row=document.createElement("tr"),cell=make("td","empty",text);cell.colSpan=columns;row.append(cell);$(id).replaceChildren(row)});sync("");return}eventSelect.value=selected.event_name;const count=countFor(selected),previous=countFor(selected,true),reasons=reasonsFor(selected),covered=reasons.reduce((s,r)=>s+r.filtered_count,0),coverage=count?covered/count:null,rate=!contextFiltered()?selected.rate:null,rateText=rate?.value!=null?pct(rate.value):"无可靠分母";
      const metrics=$("investigate-metrics");metrics.replaceChildren(metric("异常次数",fmt(count),`上期 ${fmt(previous)}`,count>previous?"bad":"good"),metric("影响用户",fmt(usersFor(selected)),contextFiltered()?"当前平台 / 版本口径":"当前事件去重"),metric(labels[selected.outcome_type]?`${labels[selected.outcome_type]}率`:"结果率",rateText,contextFiltered()?"筛选后没有成功分母":rate?.value!=null?`${fmt(rate.numerator)} / ${fmt(rate.denominator)}`:"仅展示异常量"),metric("原因覆盖率",pct(coverage),`${fmt(covered)} / ${fmt(count)}`));
      $("workbench-event").textContent=selected.event_name;const peak=renderHours($("heatmap"),selected,true);$("peak-hour").textContent=peak.value?`峰值 ${String(peak.peak).padStart(2,"0")}:00 · ${fmt(peak.value)} 次`:"暂无峰值";$("reason-dimension").textContent=selected.reasons.dimension.replace("customEvent:","");$("investigate-coverage").textContent=`覆盖率 ${pct(renderDonut("investigate",count,reasons,selected.reasons.status))}`;
      const flow=$("flow");flow.replaceChildren();const title=make("div");title.append(make("h3","",selected.event_name),make("p","helper",rate?.value!=null?"结果率使用规则中明确配置的成功 / 评估事件作为分母。":contextFiltered()?"平台或版本筛选后没有对应成功事件分母，因此不计算结果率。":"该事件没有可靠分母，因此不计算结果率。"));flow.append(title);const summary=make("div","flow-summary");summary.append(metric("本期异常",fmt(count),"分子"),metric("规则分母",rate?.denominator!=null?fmt(rate.denominator):"—",rate?.denominator!=null?"异常 + 成功 / 评估":"未配置"),metric("结果率",rateText,rate?.previous!=null?`上期 ${pct(rate.previous)}`:"上期不可用"));flow.append(summary);const compare=make("div","compare"),max=Math.max(count,previous,1);[["本期",count],["上期",previous]].forEach(([label,value])=>{const row=make("div","compare-row"),track=make("div","track"),fill=make("span");fill.style.width=`${value/max*100}%`;track.append(fill);row.append(make("span","",label),track,make("span","",`${fmt(value)} 次`));compare.append(row)});flow.append(compare);
      const contexts=(selected.contexts||[]).filter(matches),contextTable=$("context-table");contextTable.replaceChildren();contexts.forEach(item=>{const row=document.createElement("tr");[item.platform,item.app_version,fmt(item.event_count),fmt(item.affected_users),pct(count?item.event_count/count:null)].forEach((value,index)=>{const cell=document.createElement(index===0?"th":"td");if(index===0)cell.scope="row";if(index>1)cell.className="numeric";cell.textContent=value;row.append(cell)});contextTable.append(row)});if(!contexts.length){const row=document.createElement("tr"),cell=make("td","empty","当前筛选没有平台 / 版本数据");cell.colSpan=5;row.append(cell);contextTable.append(row)}
      const reasonTable=$("reason-table");reasonTable.replaceChildren();reasons.forEach(reason=>{const filteredContexts=(reason.contexts||[]).filter(matches).sort((a,b)=>b.event_count-a.event_count),top=filteredContexts[0],row=document.createElement("tr");[reason.reason,fmt(reason.filtered_count),pct(count?reason.filtered_count/count:null),top?`${top.platform} / ${top.app_version}`:"—"].forEach((value,index)=>{const cell=document.createElement(index===0?"th":"td");if(index===0)cell.scope="row";cell.textContent=value;row.append(cell)});reasonTable.append(row)});if(!reasons.length){const row=document.createElement("tr"),cell=make("td","empty",selected.reasons.status==="available"?"暂无已批准原因值":"原因维度不可用");cell.colSpan=4;row.append(cell);reasonTable.append(row)}sync(selected.event_name);
    }
    const quality=$("quality"),warnings=[...(report.quality.missing_dimensions||[]).map(x=>`未注册原因维度：${x}`),...(report.quality.warnings||[])];if(quality){if(warnings.length)warnings.forEach(x=>quality.append(make("li","",x)));else quality.append(make("li","ok","自定义原因维度均可查询，未发现质量告警"))}
    $("daily-nav").classList.toggle("active",view==="daily");$("investigate-nav").classList.toggle("active",view==="investigate");$("footer").textContent=`report_schema_version ${report.report_schema_version} · rules_version ${report.rules_version}`;
    const render=view==="daily"?renderDaily:renderInvestigation;[platform,version].forEach(select=>select.onchange=render);domain.onchange=render;outcome.onchange=render;eventSelect.onchange=render;render();
  })();
  </script>
</body>
</html>
"""
