#!/usr/bin/env python3
"""Loopback-only, read-only operator UI for the configured analytics scope."""
from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import psycopg
from db import SCOPE, connect

LABELS = {
    "WAITING_EXPORT":"等待导出", "AVAILABLE":"可用", "DEGRADED":"存在质量缺口", "NO_DATA":"无数据",
    "SUCCEEDED":"归档成功", "SELECTED_PREVIEW":"预览选中", "MERGED_INTO_SELECTED_ACCOUNT":"合并到已选账号",
    "TOTAL_ACCOUNT_LIMIT":"本次账号总额限制", "GROUP_LIMIT":"本次分组上限", "UNRESOLVED":"实例目标未解析",
    "KEY_SIGNAL":"关键异常信号", "SDK_OR_UNKNOWN":"SDK 或未知错误", "NETWORK_OR_TIMEOUT":"网络或超时",
    "TOP10_IMPACT":"日报 Top10 影响", "EXPECTED_BEHAVIOR":"预期行为排除", "BELOW_THRESHOLD":"低于阈值",
    "INVALID_REASON":"原因值不符合契约", "MISSING_ACCOUNT":"缺少合法账号", "NON_CRASH_EXIT":"非已支持崩溃退出",
    "AMBIGUOUS_PARAMETERS":"参数歧义", "APPROVED_UNKNOWN":"合法 unknown", "HYPOTHESIS":"待验证假设",
    "UNVERIFIED":"尚未由日志验证", "VALID":"有效", "MEDIAN":"中位数", "NO_REFERENCE":"没有参考值",
    "SINGLE_ACCOUNT_NOISE":"单账号集中异常", "UNAVAILABLE_NO_DENOMINATOR":"无分母，结果率不可计算",
}


def h(value):
    return escape(str(value if value is not None else "未知"), quote=True)


def label(value):
    return h(LABELS.get(value, value))


def badge(value):
    return f'<span class="badge">{label(value)}</span>'


def url(path, **params):
    return h(path + ("?" + urlencode({k:v for k,v in params.items() if v is not None}) if params else ""))


def link(path, text, **params):
    return f'<a href="{url(path, **params)}">{h(text)}</a>'


def raw_details(title, value):
    return f'<details><summary>{h(title)}</summary><pre>{h(json.dumps(value,ensure_ascii=False,indent=2))}</pre></details>'


def table(heads, rows, caption=""):
    if not rows:
        return '<p class="empty" role="status">没有符合条件的记录。</p>'
    return '<div class="table-wrap"><table>' + (f'<caption>{h(caption)}</caption>' if caption else '') + \
        '<thead><tr>' + ''.join(f'<th scope="col">{h(x)}</th>' for x in heads) + '</tr></thead><tbody>' + \
        ''.join('<tr>'+''.join(f'<td>{cell}</td>' for cell in row)+'</tr>' for row in rows) + '</tbody></table></div>'


def page(title, body):
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{h(title)} · 埋点分析管理</title>
<link rel="stylesheet" href="/style.css"></head><body>
<a class="skip" href="#main">跳到内容</a><header><nav aria-label="主导航"><a class="brand" href="/">埋点分析管理</a>
<span>第一阶段 · 冻结回放 · 本机只读</span><a href="/users">按用户查询</a></nav></header>
<main id="main"><div class="scope">{h(SCOPE)}</div><h1>{h(title)}</h1>
<p class="notice">当前为账号级候选预览，实例目标尚未解析；问题推断等待日志验证。采集任务 0 · 推送 0。</p>{body}</main>
<footer>仅本机操作者访问指定 scope。日期与聚合窗口为 UTC；不构造逐事件时间线。</footer></body></html>'''


def search_form(action, account="", hidden=None):
    fields = ''.join(f'<input type="hidden" name="{h(k)}" value="{h(v)}">' for k,v in (hidden or {}).items())
    return f'''<form method="get" action="{h(action)}">{fields}<label for="account">账号 ID（精确查询）</label>
<div class="form-line"><input id="account" name="account" value="{h(account)}" inputmode="numeric" pattern="[1-9][0-9]*" maxlength="64" placeholder="输入业务账号 ID">
<button type="submit">查询</button></div></form>'''


def summary_cards(items):
    return '<dl class="stats">'+''.join(f'<div><dt>{h(k)}</dt><dd>{h(v)}</dd></div>' for k,v in items)+'</dl>'


def get_run(conn, run_id):
    return conn.execute("SELECT * FROM analytics.telemetry_runs WHERE scope_key=%s AND run_id=%s", (SCOPE,run_id)).fetchone()


def batch_index(conn, params):
    account = params.get("account", "")
    rows = conn.execute("""SELECT r.run_id,r.target_day,r.data_status,r.process_status,r.created_at,
        (SELECT count(*) FROM analytics.daily_reports d WHERE d.run_id=r.run_id) AS reports,
        (SELECT count(*) FROM analytics.diagnostic_contexts c WHERE c.run_id=r.run_id) AS accounts,
        (SELECT count(*) FROM analytics.telemetry_findings f WHERE f.run_id=r.run_id) AS findings
        FROM analytics.telemetry_runs r WHERE r.scope_key=%s
        AND (%s='' OR EXISTS(SELECT 1 FROM analytics.diagnostic_contexts c WHERE c.run_id=r.run_id AND c.account_id=%s))
        ORDER BY r.created_at DESC,r.run_id LIMIT 100""", (SCOPE,account,account)).fetchall()
    body = search_form("/", account) + '<h2>分析批次</h2>'
    body += table(["请求统计日 / 批次","数据状态","计算状态","日报","候选账号","关联线索","入库时间 UTC"], [
        [link('/runs/'+r['run_id'],str(r['target_day']))+f'<small class="mono">{h(r["run_id"][:16])}…</small>',
         badge(r['data_status']),badge(r['process_status']),h(r['reports']),h(r['accounts']),h(r['findings']),h(r['created_at'].strftime('%Y-%m-%d %H:%M:%S'))]
        for r in rows], "最近 100 个批次；同一冻结输入与归档重复导入只保留一条批次")
    if account:
        body += '<p>'+link('/users/'+account,'查看该用户的归档批次')+'</p>'
    return page("分析批次",body)


def metric(value, percent=False):
    if value is None:
        return '不可计算'
    return f'{value*100:.2f}%' if percent else f'{value:,.2f}'.rstrip('0').rstrip('.')


def comparison_detail(comparison):
    return table(["指标","本期","参考","差值","相对变化","参考天数 / 状态"], [
        [h({"records":"记录数","identified_accounts":"去重账号","result_rate":"结果率"}.get(k,k)),
         h(metric(v.get('current'),k=='result_rate')),h(metric(v.get('reference'),k=='result_rate')),
         h(f'{v["delta_percentage_points"]:+.2f} 个百分点' if k=='result_rate' and v.get('delta_percentage_points') is not None else metric(v.get('delta'))),
         h(metric(v.get('relative_change'),True)),h(f'{v.get("reference_days",0)}/{v.get("expected_reference_days",0)}')+' '+badge(v.get('status'))]
        for k,v in comparison.items()]) + raw_details("比较状态及不可计算原因",comparison)


def report_view(report):
    rows = []
    for rank, event in enumerate(report['top10'],1):
        comparison = event['previous_day_comparison']['records']
        baseline = event['baseline_comparison']['records']
        details = '<details><summary>查看原因、分母与比较口径</summary>'
        details += '<h3>较前一 UTC 日</h3>'+comparison_detail(event['previous_day_comparison'])
        details += '<h3>前 7 日基线</h3>'+comparison_detail(event['baseline_comparison'])
        details += raw_details('事件完整指标、平台与版本分布',event)+'</details>'
        rows.append([h(rank),f'<code>{h(event["event_name"])}</code>'+details,h(event['records']),h(event['identified_accounts']),
                     h(metric(event.get('result_rate'),True))+'<small>'+label(event.get('result_rate_status'))+'</small>',
                     h(metric(comparison.get('relative_change'),True)),h(metric(baseline.get('reference'))),
                     h(metric(baseline.get('relative_change'),True))])
    body = '<h2>日报 Top10</h2><p>统计日 '+h(report['statistical_day'])+' · UTC；结果率沿用原指标定义，分母见每行详情。环比与基线为全筛选人群，不能当成单用户基线。</p>'
    body += summary_cards([('基线方法',LABELS.get(report['baseline_summary']['method'],report['baseline_summary']['method'])),
                           ('基线可用天数',f'{report["baseline_summary"]["available_days"]}/7'),
                           ('数据质量',LABELS.get(report['quality']['status'],report['quality']['status']))])
    body += table(['排名','事件 / 解释','记录数','去重账号','结果率','记录数环比','基线记录数','较基线变化'],rows)
    body += raw_details('数据质量、窗口与表覆盖', {k:report[k] for k in ['quality','table_coverage','window','baseline_summary']})
    body += raw_details('全部事件及比较指标（原样归档）',report['events'])
    return body


def batch_view(conn, run_id, params):
    run = get_run(conn,run_id)
    if not run:
        return None
    analysis = run['analysis']
    reports = conn.execute("SELECT statistical_day,content FROM analytics.daily_reports WHERE run_id=%s ORDER BY statistical_day DESC",(run_id,)).fetchall()
    day = params.get('day') or (str(reports[0]['statistical_day']) if reports else '')
    selected = next((r['content'] for r in reports if str(r['statistical_day'])==day),None)
    if params.get('day') and not selected:
        return None
    account = params.get('account','')
    contexts = conn.execute("""SELECT c.account_id,c.selection_order,c.context_id,c.proposal,
        jsonb_array_length(c.content->'findings') AS findings,
        jsonb_array_length(c.content->'observations') AS facts
        FROM analytics.diagnostic_contexts c WHERE c.run_id=%s AND (%s='' OR c.account_id=%s)
        ORDER BY c.selection_order""",(run_id,account,account)).fetchall()
    funnel = analysis['candidate_summary']['funnel']
    body = '<p>'+link('/','全部批次')+'</p>'+summary_cards([('请求统计日',run['target_day']),('数据状态',LABELS.get(run['data_status'],run['data_status'])),
            ('观察账号',funnel['observed_accounts']),('合格账号',funnel['eligible_accounts']),('命中账号',funnel['matched_accounts']),('候选预览',funnel['proposed_accounts'])])
    body += '<p>漏斗统计日：'+h('、'.join(analysis['candidate_summary']['statistical_days']))+'。计算与归档已完成；请求日缺表时保留等待导出状态。</p>'
    body += '<nav class="tabs" aria-label="日报日期">'+''.join(link('/runs/'+run_id,str(r['statistical_day']),day=str(r['statistical_day'])) for r in reports)+'</nav>'
    if selected:
        body += report_view(selected)
    body += '<h2>候选用户</h2>'+search_form('/runs/'+run_id,account,{'day':day})
    body += table(['顺序','账号','主线索 / 原因','平台 / 版本','命中规则','关联线索 / 埋点聚合'],[
        [h(c['selection_order']),link('/users/'+c['account_id'],c['account_id'],run=run_id),
         '<code>'+h(c['proposal']['evidence']['event_name'])+'</code><small>'+h(c['proposal']['evidence']['failure_reason'])+'</small>',
         h(c['proposal']['platform'])+'<small>'+h(' / '.join(c['proposal']['app_versions']))+'</small>',
         '<br>'.join(label(x) for x in c['proposal']['matched_rules']),h(f'{c["findings"]} / {c["facts"]}')]
        for c in contexts], '点击账号查看筛选原因、所有关联线索、事实引用与诊断上下文')
    body += '<h2>筛选与排除</h2>'+raw_details('各阶段原因统计与固定策略',{'candidate_summary':analysis['candidate_summary'],'policy':analysis['policy']})
    body += raw_details('完整候选池（含未选中原因）',analysis['candidate_pool'])
    body += raw_details('全部排除记录（保留原始排除码）',analysis['candidate_exclusions'])
    executions = conn.execute("SELECT * FROM analytics.run_executions WHERE run_id=%s",(run_id,)).fetchall()
    body += '<h2>来源与版本</h2><dl class="metadata">'+''.join(f'<dt>{h(k)}</dt><dd class="mono">{h(v)}</dd>' for k,v in
             [('run_id',run_id),('source_sha256',run['source_sha256']),('rules_version',run['rules_version']),('implementation_sha256',run['implementation_sha256'])])+'</dl>'
    for execution in executions:
        path = 'http://127.0.0.1:8080/ui/main/executions/'+quote(execution['namespace'],safe='')+'/'+quote(execution['flow_id'],safe='')+'/'+quote(execution['execution_id'],safe='')+'/outputs'
        body += '<p>'+link(path,'查看 Kestra 执行 '+execution['execution_id'])+'</p>'
    body += raw_details('源快照清单、归档摘要与数据覆盖',{'provenance':run['provenance'],'archive_manifest':run['archive_manifest'],
                        'source_manifest':run['source_manifest'],'day_coverage':analysis['day_coverage']})
    return page('批次 '+run_id[:16],body)


def account_view(conn, account, params):
    contexts = conn.execute("""SELECT c.*,r.target_day,r.created_at AS imported_at FROM analytics.diagnostic_contexts c
        JOIN analytics.telemetry_runs r USING (run_id) WHERE r.scope_key=%s AND c.account_id=%s
        ORDER BY r.created_at DESC,r.run_id LIMIT 100""",(SCOPE,account)).fetchall()
    body = search_form('/users',account)
    if not contexts:
        return page('用户 '+account,body+'<p class="empty" role="status">该账号没有已归档候选上下文。当前仅为预览选中的账号保存独立上下文；这不代表该账号没有异常。</p>')
    run_id = params.get('run') or contexts[0]['run_id']
    selected = next((c for c in contexts if c['run_id']==run_id),None)
    if selected is None:
        return None
    content, proposal = selected['content'], selected['proposal']
    body += '<h2>已归档批次（最近 100 个）</h2>'+table(['请求统计日','批次','上下文'],[[h(c['target_day']),
        link('/users/'+account,c['run_id'][:16],run=c['run_id']),h(c['context_id'][:16])+'…'] for c in contexts])
    body += '<p>'+link('/runs/'+run_id,'返回本批次日报与候选用户')+'</p>'
    body += summary_cards([('关联线索',len(content['findings'])),('埋点聚合行',len(content['observations'])),
                           ('目标状态',LABELS['UNRESOLVED']),('采集任务',0)])
    body += ('<h2>为什么选中该账号</h2><p>'+badge(selected['selection_outcome'])+' 顺序 '+h(selected['selection_order'])+
        '；主线索统计日 '+h(proposal['statistical_day'])+'，'+h(proposal['platform'])+'，'+h(proposal['records'])+' 条记录。</p>')
    body += '<p>命中规则：'+ '、'.join(label(x) for x in proposal['matched_rules'])+'。优先级依据：'+label(proposal['priority_reason'])+'。</p>'
    body += raw_details('完整选样依据、组占比及合并线索',proposal)
    body += '<h2>关联线索与问题推断</h2><p>以下检查方向由规则生成，状态均为待验证；语义搜索词不能直接当作精确日志标签。</p>'
    for finding in content['findings']:
        investigation = finding['investigation']
        body += '<article class="finding"><h3><code>'+h(finding['event_name'])+'</code> · '+h(finding['reason'])+'</h3>'
        body += '<p>'+h(finding['statistical_day'])+' · '+h(finding['platform'])+' · '+h(finding['account_records'])+' 条 · 组内 '+h(finding['group_accounts'])+' 个账号 · '+badge(finding['selection']['reason'])+'</p>'
        body += '<p>规则：'+ '、'.join(label(x) for x in finding['matched_rules'])+'。排查方向：'+h(investigation['suspected_area'])+'。</p>'
        body += '<ul>'+''.join('<li>'+h(x)+'</li>' for x in investigation['checks'])+'</ul>'
        body += '<p>语义搜索词：'+h(' / '.join(investigation['search_terms']))+'</p><p>支持本线索的事实：'+ ' '.join(
            f'<a href="#fact-{h(ref)}"><code>{h(ref[:12])}</code></a>' for ref in finding['evidence_fact_ids'])+'</p>'
        body += raw_details('线索身份、全人群比较与证据引用',finding)+'</article>'
    body += '<h2>该账号的排除记录</h2>'+table(['统计日','事件','平台','记录数','排除原因','末次事件 UTC'],[
        [h(x['statistical_day']),'<code>'+h(x['event_name'])+'</code>',h(x['platform']),h(x['records']),label(x['reason']),h(x['last_event_at'])]
        for x in content['exclusions']])
    body += '<h2>埋点证据</h2><p>这里是该账号在冻结查询范围内的 UTC 日聚合；首末时间为聚合界限。点击线索中的事实引用可定位对应行。</p>'
    facts = []
    for fact in sorted(content['observations'],key=lambda x:(x['statistical_day'],x['event_name']),reverse=True):
        facts.append([f'<span id="fact-{h(fact["fact_id"])}" class="anchor"><code>{h(fact["fact_id"][:12])}</code></span>'+raw_details('事实摘要',fact),
            h(fact['statistical_day']),'<code>'+h(fact['event_name'])+'</code>',h(fact['platform'])+'<small>'+h(fact['app_version'])+'</small>',
            h(fact['records']),h(fact['reason'] if fact['reason'] is not None else '未提供 / 不适用'),h(fact['first_event_at'])+'<small>'+h(fact['last_event_at'])+'</small>',
            label(fact['parameter_status'])+'<small>'+(label(fact['reason_status']) if fact['reason_status'] else '未标记原因问题')+'</small>'])
    body += table(['事实 ID','UTC 日','事件','平台 / 版本','次数','原因','首末时间 UTC','质量'],facts)
    body += '<h2>诊断上下文</h2><p class="mono">context_id: '+h(selected['context_id'])+'</p>'
    body += '<ul>'+''.join('<li>'+h(x)+'</li>' for x in content['limitations'])+'</ul>'
    body += raw_details('完整单账号诊断上下文（PostgreSQL 原样存储）',content)
    return page('用户 '+account,body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Request paths can contain private account identifiers.

    def send(self, status, body, content_type='text/html; charset=utf-8'):
        payload = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def do_GET(self):
        if self.headers.get('Host') not in {'127.0.0.1:8090','localhost:8090'} or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return self.send(403,page('无法访问','<p>仅允许本机同站点访问。</p>'))
        try:
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query,keep_blank_values=True,max_num_fields=8)
            if len(self.path)>2048 or any(len(v)!=1 for v in params.values()) or set(params)-{'account','run','day'}:
                raise ValueError('Invalid query')
            params = {k:v[0] for k,v in params.items()}
            if params.get('account') and not re.fullmatch(r'[1-9][0-9]{0,63}',params['account']):
                raise ValueError('Invalid account')
            if params.get('run') and not re.fullmatch(r'[0-9a-f]{64}',params['run']):
                raise ValueError('Invalid run')
            if params.get('day'):
                date.fromisoformat(params['day'])
            if parsed.path=='/style.css':
                return self.send(200,Path(__file__).with_name('style.css').read_text(),'text/css; charset=utf-8')
            if parsed.path=='/favicon.ico':
                return self.send(204,'')
            with connect(read_only=True) as conn:
                if parsed.path=='/healthz':
                    conn.execute('SELECT 1').fetchone()
                    return self.send(200,'{"status":"ok","read_only":true}','application/json')
                if parsed.path=='/':
                    result = batch_index(conn,params)
                elif parsed.path=='/users':
                    result = account_view(conn,params['account'],params) if params.get('account') else page('按用户查询',search_form('/users'))
                elif re.fullmatch(r'/runs/[0-9a-f]{64}',parsed.path):
                    result = batch_view(conn,parsed.path.split('/')[-1],params)
                elif re.fullmatch(r'/users/[1-9][0-9]{0,63}',parsed.path):
                    result = account_view(conn,parsed.path.split('/')[-1],params)
                else:
                    result = None
            self.send(200,result) if result else self.send(404,page('未找到记录','<p>批次、日期或用户关联不存在于当前 scope。</p>'))
        except ValueError:
            self.send(400,page('查询参数无效','<p>请使用合法账号 ID、批次 ID 和 ISO 日期。</p>'))
        except psycopg.Error:
            self.send(503,page('数据库暂时不可用','<p role="alert">请稍后重试；当前请求未修改数据。</p>'))

    def do_HEAD(self):
        self.do_GET()


if __name__=='__main__':
    print('Analytics management ready on container port 8090; publish on loopback only.',flush=True)
    ThreadingHTTPServer(('0.0.0.0',8090),Handler).serve_forever()
