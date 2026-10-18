"""Generate a static reader-facing dashboard from a review export.

This is what Newseye would look like to a Kenyan reader: an overview of the
story clusters currently tracked, and one page per story showing which outlet
carried which fact, how each described the people involved, and what numbers
each published - with the sentence around every number and a link to the
original.

It asserts nothing. No contradiction claims, no stance labels, no accuracy
scores, no per-outlet trust rating. The reader is given the comparison and makes
the judgement, because on this corpus that is the only division of labour that
has held up: adjudicating figure conflicts produced no true positive at either
800 or 2,162 articles, and the stance classifier called a story headlined
"Appoints Kenyan Diplomat to Crucial New Role" critical at 0.796.

The dashboard counts what the system can actually stand behind - stories,
articles, coverage gaps, outlets - and deliberately has no "contradictions"
figure, because across 151 story groups it found none between two outlets.

    python -m backend.scripts.export_review --top 14
    python -m backend.scripts.build_site

search.html searches every article in the database, not only the stories shown
here. The reader's query is embedded in the browser by the same MiniLM model,
fetched from a CDN on first use, and compared with each article's stored
embedding, shipped in search-index.js. Building the index needs the database;
without one the previous index is left in place.
"""
import argparse
import base64
import difflib
import html
import json
import os
import re
from collections import Counter, defaultdict

from backend.analysis.digest import digest_groups, summarise
from backend.config import RSS_FEEDS
from backend.ingestion.dedupe import is_web_url

CSS = """
:root{--bg:#F4F6F8;--panel:#FFFFFF;--rail:#0E1B2A;--rail-2:#16283C;--ink:#16202B;
--muted:#667585;--faint:#93A0AD;--rule:#E4E9EE;--accent:#12B39B;--accent-soft:#E2F7F3;
--gap:#C2571E;--gap-soft:#FDF0E6;--ok:#1F7A55;--ok-soft:#E6F4EC;--violet:#6E56CF;
--serif:"Newsreader",Georgia,serif;--sans:"Source Sans 3",ui-sans-serif,system-ui,sans-serif}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0B1219;
--panel:#131D27;--rail:#0A121B;--rail-2:#16242F;--ink:#E7ECF1;--muted:#93A0AD;
--faint:#6B7885;--rule:#22303C;--accent:#3FD3BA;--accent-soft:#12312C;--gap:#E0954F;
--gap-soft:#33240F;--ok:#57B98A;--ok-soft:#12301F;--violet:#A797F0}}
:root[data-theme=dark]{--bg:#0B1219;--panel:#131D27;--rail:#0A121B;--rail-2:#16242F;
--ink:#E7ECF1;--muted:#93A0AD;--faint:#6B7885;--rule:#22303C;--accent:#3FD3BA;
--accent-soft:#12312C;--gap:#E0954F;--gap-soft:#33240F;--ok:#57B98A;--ok-soft:#12301F;
--violet:#A797F0}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;
line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}

/* ---- shell ---- */
.app{display:grid;grid-template-columns:212px minmax(0,1fr);min-height:100vh}
.rail{background:var(--rail);color:#DCE5ED;padding:18px 14px;display:flex;
flex-direction:column;gap:22px;position:sticky;top:0;height:100vh}
.brand{display:flex;align-items:center;gap:9px;padding:4px 6px 0}
.brand .glyph{width:30px;height:30px;border-radius:8px;background:var(--accent);
display:grid;place-items:center;flex:none}
.brand .glyph svg{width:17px;height:17px;display:block}
.brand b{font-size:16.5px;letter-spacing:-.01em;color:#fff;font-weight:700}
nav{display:flex;flex-direction:column;gap:2px}
nav a{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:7px;
font-size:13.5px;color:#9FB0C0;font-weight:600}
nav a svg{width:15px;height:15px;flex:none;opacity:.85}
nav a:hover{background:var(--rail-2);color:#E8EFF5}
nav a.on{background:var(--rail-2);color:#fff}
nav a.on svg{opacity:1;color:var(--accent)}

.main{min-width:0;display:flex;flex-direction:column}
.topbar{display:flex;gap:12px;align-items:center;padding:13px 22px;background:var(--panel);
border-bottom:1px solid var(--rule);position:sticky;top:0;z-index:5}
.search{flex:1;max-width:400px;display:flex;align-items:center;gap:8px;background:var(--bg);
border:1px solid var(--rule);border-radius:8px;padding:7px 11px}
.search svg{width:14px;height:14px;color:var(--faint);flex:none}
.search input{border:0;background:transparent;color:var(--ink);font:inherit;
font-size:13.5px;width:100%;outline:none}
.stamp{margin-left:auto;font-size:12.5px;color:var(--muted);border:1px solid var(--rule);
border-radius:8px;padding:6px 11px;white-space:nowrap}
.content{padding:20px 22px 64px;max-width:1220px}

/* ---- what this site is for: the first thing on the dashboard ---- */
.intro{background:var(--panel);border:1px solid var(--rule);border-radius:11px;
padding:18px 20px;margin-bottom:20px}
.intro h1{font-family:var(--serif);font-size:clamp(21px,3vw,26px);font-weight:700;
line-height:1.2;letter-spacing:-.015em;margin:0 0 6px}
.intro p{margin:0;max-width:72ch;color:var(--muted)}
ol.steps{display:flex;flex-wrap:wrap;gap:8px 22px;margin:12px 0 0;padding:0;list-style:none;
counter-reset:step;font-size:14px}
ol.steps li{counter-increment:step;display:flex;align-items:center;gap:8px}
ol.steps li::before{content:counter(step);width:22px;height:22px;border-radius:50%;
background:var(--accent-soft);color:var(--accent);font-size:12px;font-weight:700;
display:grid;place-items:center;flex:none}
p.meta{margin-top:12px;font-size:12.5px;color:var(--faint)}

/* ---- two column body ---- */
.cols{display:grid;grid-template-columns:minmax(0,1fr) 288px;gap:18px;align-items:start}
.colhead{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
margin:0 0 11px}
.colhead h2{font-family:var(--serif);font-size:19px;font-weight:700;margin:0;
letter-spacing:-.01em}
.colhead .hint{font-size:12.5px;color:var(--muted)}

/* ---- story cards ---- */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:13px}
.tile{background:var(--panel);border:1px solid var(--rule);border-radius:10px;
padding:13px 14px;display:flex;flex-direction:column;gap:9px}
.tile:hover{border-color:var(--accent)}
.chips{display:flex;flex-wrap:wrap;gap:5px}
.chip{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
background:var(--bg);border:1px solid var(--rule);color:var(--muted);
border-radius:5px;padding:3px 6px}
.tile h3{font-family:var(--serif);font-size:16px;font-weight:600;line-height:1.32;
margin:0;letter-spacing:-.005em}
.srcline{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.srcline svg{width:12px;height:12px;flex:none;opacity:.7}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto;align-content:flex-start;
align-items:flex-start}
.badge{font-size:11px;font-weight:700;border-radius:20px;padding:3px 9px;
display:inline-flex;align-items:center;gap:5px}
.badge.gap{background:var(--gap-soft);color:var(--gap)}
.badge.fig{background:var(--accent-soft);color:var(--accent)}
.badge.ok{background:var(--ok-soft);color:var(--ok)}
.badge.loose{background:var(--gap-soft);color:var(--gap)}
.empty-grid{background:var(--panel);border:1px dashed var(--rule);border-radius:10px;
padding:26px;text-align:center;color:var(--muted);font-size:13.5px}

/* ---- right rail panels ---- */
.panel{background:var(--panel);border:1px solid var(--rule);border-radius:10px;
padding:14px 15px;margin-bottom:13px}
.panel h4{font-size:13.5px;font-weight:700;margin:0 0 10px}
.rank{display:flex;flex-direction:column;gap:9px}
.rank .r{display:flex;gap:9px;align-items:flex-start}
.rank .r b{width:19px;height:19px;border-radius:5px;background:var(--accent-soft);
color:var(--accent);font-size:11px;font-weight:700;display:grid;place-items:center;flex:none;
margin-top:1px}
.rank .r span{font-size:13px;font-weight:600;line-height:1.3;display:block}
.rank .r small{font-size:11.5px;color:var(--faint);display:block}
.panel.quiet{background:var(--bg)}
.panel.quiet p{font-size:12.5px;color:var(--muted);margin:0 0 8px;line-height:1.5}
.panel.quiet p:last-child{margin-bottom:0}
.panel ul.plain{margin:0;padding-left:16px;font-size:12.5px;color:var(--muted)}
.panel ul.plain li{margin-bottom:5px}
details.howto{background:var(--bg);border:1px solid var(--rule);border-radius:10px;
margin-bottom:13px}
details.howto summary{cursor:pointer;padding:12px 15px;font-size:13.5px;font-weight:700}
details.howto .pbody{padding:0 15px 12px}
details.howto p{font-size:12.5px;color:var(--muted);margin:0 0 8px;line-height:1.5}

/* ---- story detail ---- */
.back{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--accent);
font-weight:700;margin-bottom:14px}
.sheet{background:var(--panel);border:1px solid var(--rule);border-radius:11px;
padding:22px 24px;max-width:900px}
.sheet header h1{font-family:var(--serif);font-size:clamp(21px,3.4vw,30px);font-weight:700;
line-height:1.16;letter-spacing:-.015em;margin:0 0 9px;text-wrap:balance}
.sheet header p.lede{font-size:14px;color:var(--muted);margin:0 0 4px}
/* the story in a few sentences, before any table */
.atglance{background:var(--accent-soft);border-radius:10px;padding:13px 16px;margin:16px 0 4px}
.atglance b.t{display:block;font-size:11.5px;text-transform:uppercase;letter-spacing:.09em;
color:var(--accent);margin-bottom:4px}
.atglance ul{margin:0;padding-left:18px;font-size:14.5px;line-height:1.5}
.atglance li{margin:4px 0}
.atglance a{color:var(--accent);font-weight:700;white-space:nowrap}
.pills{display:flex;flex-wrap:wrap;gap:6px}
.pill{font-size:12.5px;border-radius:20px;padding:3px 10px;border:1px solid var(--rule);
background:var(--bg)}
.pill b{font-weight:700}
.trow{display:grid;grid-template-columns:170px minmax(0,1fr);gap:12px;align-items:center;
padding:10px 0 4px;border-top:1px solid var(--rule)}
.trow>div:first-child b{font-size:14px}
.trow small{display:block;font-size:11.5px;color:var(--muted)}
details.ex{margin:0 0 8px 182px;font-size:12.5px}
details.ex summary{cursor:pointer;color:var(--accent);font-weight:700}
p.fgroup{font-size:13.5px;margin:12px 0 7px}
h4.fsub{font-size:13.5px;margin:12px 0 4px}
p.swipe{display:none;font-size:12.5px;font-weight:700;color:var(--accent);margin:4px 0}
@media(max-width:820px){.trow{grid-template-columns:minmax(0,1fr);gap:6px}
details.ex{margin-left:0}p.swipe{display:block}}
h3.sub{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.09em;
color:var(--muted);margin:26px 0 7px;padding-bottom:6px;border-bottom:1px solid var(--rule);
scroll-margin-top:76px}
p.hint{font-size:13.5px;color:var(--muted);margin:8px 0 13px;max-width:70ch}
.loose{border:1px solid var(--gap);background:var(--gap-soft);border-radius:9px;
padding:12px 14px;margin:14px 0;font-size:13.5px}
.loose b{color:var(--gap)}
.heads{margin:0;padding:0;list-style:none}
.heads li{display:grid;grid-template-columns:148px minmax(0,1fr);gap:13px;padding:10px 0;
border-bottom:1px solid var(--rule);align-items:baseline}
.heads li:first-child{border-top:1px solid var(--rule)}
.hsrc{font-size:12.5px;font-weight:700}
.hsrc .unread{display:block;font-size:10px;font-weight:700;text-transform:uppercase;
letter-spacing:.05em;color:var(--gap);margin-top:2px}
.heads a{font-family:var(--serif);font-size:15px;line-height:1.38}
.heads a:hover{text-decoration:underline;text-decoration-color:var(--accent)}
.scroll{overflow-x:auto;margin:6px 0}
table{border-collapse:collapse;width:100%;min-width:520px;font-size:13.5px}
th,td{padding:9px 7px;border-bottom:1px solid var(--rule)}
thead th{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
color:var(--muted);text-align:center;vertical-align:bottom;border-bottom:2px solid var(--ink)}
thead th:first-child{text-align:left;width:48%}
td.f{font-family:var(--serif);font-size:14px;line-height:1.4}
td.m{text-align:center;font-size:15px;font-weight:700}
td.m.y{color:var(--ok)}td.m.n{color:var(--gap);background:var(--gap-soft)}
td.m.r{color:var(--violet)}
.legend i.r{color:var(--violet)}
details.rel{margin-top:6px;font-family:var(--sans);font-size:12.5px;color:var(--muted)}
details.rel summary{cursor:pointer;color:var(--violet);font-weight:700}
details.rel p{margin:5px 0 0;line-height:1.45}
.remark{border:1px solid var(--rule);border-radius:10px;padding:11px 14px 6px;margin-bottom:10px;
background:var(--bg)}
.rhead{display:flex;gap:10px;align-items:baseline;margin-bottom:6px}
.rhead b{font-size:14.5px}.rhead span{font-size:12px;color:var(--muted)}
.ver{display:grid;grid-template-columns:130px minmax(0,1fr);gap:12px;padding:8px 0;
border-top:1px solid var(--rule);align-items:start}
.vsrc{font-size:12.5px;font-weight:700}
.ver blockquote{margin:0;font-family:var(--serif);font-size:14px;line-height:1.45}
.ver mark{background:var(--accent-soft);color:var(--ink);border-radius:3px;padding:0 2px}
.vrel{display:inline-block;margin-top:5px;font-size:10.5px;font-weight:700;text-transform:uppercase;
letter-spacing:.04em;border-radius:4px;padding:2px 6px;border:1px solid var(--rule);color:var(--muted)}
.vrel.q-same{color:var(--ok);border-color:var(--ok)}
.vrel.q-more,.vrel.q-less{color:var(--accent);border-color:var(--accent)}
.vrel.q-diff{color:var(--violet);border-color:var(--violet)}
ul.qlist{margin:0;padding:0 0 4px;list-style:none}
ul.qlist li{padding:8px 0;border-top:1px solid var(--rule);font-size:13px}
ul.qlist li span{display:block;font-family:var(--serif);font-size:14px;margin-top:3px}
@media(max-width:820px){.ver{grid-template-columns:minmax(0,1fr);gap:4px}}
tfoot td{font-size:12px;color:var(--muted);border-bottom:none;padding-top:10px;
text-align:center;font-variant-numeric:tabular-nums}
tfoot td:first-child{text-align:left;font-weight:700;color:var(--ink)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted);padding:2px 0 6px}
.legend i{font-style:normal;font-weight:700}
.legend i.y{color:var(--ok)}.legend i.n{color:var(--gap)}
.quote{display:grid;grid-template-columns:132px minmax(0,1fr);gap:13px;padding:11px 0;
border-bottom:1px solid var(--rule);align-items:start}
.qsrc{display:block;font-size:12.5px;font-weight:700}
.qtone{display:block;font-size:11px;color:var(--muted)}
.quote blockquote{margin:0;font-family:var(--serif);font-size:14px;line-height:1.45;
color:var(--ink)}
.qmark{display:block;font-size:11px;color:var(--faint);margin-top:4px;font-family:var(--sans)}
.fig{border:1px solid var(--rule);border-radius:9px;padding:11px 13px;margin-bottom:9px;
background:var(--bg)}
.fhead{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;margin-bottom:5px}
.fval{font-family:var(--serif);font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}
.fsrc{font-size:12.5px;font-weight:700;color:var(--muted)}
.ftag{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
background:var(--panel);border:1px solid var(--rule);color:var(--muted);
border-radius:4px;padding:2px 5px}
.fctx{font-size:13px;color:var(--muted);margin:0;line-height:1.5}
.fctx strong{color:var(--ink);font-weight:700;background:var(--accent-soft);border-radius:3px;
padding:0 3px}
.fctx a{color:var(--accent);font-weight:700;white-space:nowrap}
.empty{font-size:13.5px;color:var(--muted);font-style:italic}

/* ---- search page ---- */
.bigsearch{display:flex;align-items:center;gap:9px;border:1px solid var(--rule);
background:var(--bg);border-radius:10px;padding:6px 6px 6px 13px;margin:16px 0 8px}
.bigsearch:focus-within{border-color:var(--accent)}
.bigsearch svg{width:16px;height:16px;color:var(--faint);flex:none}
.bigsearch input{flex:1;min-width:0;border:0;background:transparent;color:var(--ink);
font:inherit;font-size:16px;outline:none;padding:6px 0}
.bigsearch button{border:0;border-radius:7px;background:var(--accent);color:#06231E;
font:inherit;font-size:14px;font-weight:700;padding:8px 16px;cursor:pointer}
.hit{padding:15px 0;border-top:1px solid var(--rule)}
.hit h3{font-family:var(--serif);font-size:17px;font-weight:600;line-height:1.3;margin:8px 0 6px}
.hit h3 a:hover{text-decoration:underline;text-decoration-color:var(--accent)}
.hit .heads li{padding:7px 0}
.snip{font-size:13.5px;color:var(--muted);margin:0 0 6px}
.hitlink{display:inline-block;margin-top:8px;font-size:13px;font-weight:700;color:var(--accent)}
footer.end{margin-top:30px;padding-top:14px;border-top:1px solid var(--rule);
font-size:12.5px;color:var(--faint);line-height:1.55}

/* ---- people ---- */
.meter{height:8px;border-radius:4px;background:var(--rule);overflow:hidden}
.meter i{display:block;height:100%;background:var(--accent);border-radius:4px}
p.psum{font-size:14px;margin:2px 0 8px;max-width:72ch}
.role{display:block;font-size:12px;font-weight:600;color:var(--muted)}
.ph li{grid-template-columns:140px minmax(0,1fr)}
.ph small{display:block;font-size:11px;color:var(--faint);margin-top:3px}
.pchips{display:flex;flex-wrap:wrap;gap:7px;margin:6px 0 4px}
.pchip{font-size:13px;font-weight:700;border:1px solid var(--accent);color:var(--accent);
border-radius:20px;padding:4px 11px}
.pchip:hover{background:var(--accent-soft)}
.panel .more{display:block;margin-top:10px;font-size:12.5px;font-weight:700;color:var(--accent)}
.rank .r a:hover span{color:var(--accent)}
ul.facts{margin:6px 0 4px;padding-left:18px;font-size:14.5px;line-height:1.5}
ul.facts li{margin:4px 0}
table.glance{min-width:660px}
table.glance thead th{text-align:left}
table.glance thead th:first-child{width:auto}
table.glance td{vertical-align:middle}
table.glance td.o{font-weight:700;width:170px;line-height:1.25}
table.glance td.o small{display:block;font-weight:400;font-size:11px;color:var(--muted)}
table.glance td.cov{width:190px}
table.glance td.cov small{display:block;font-size:11.5px;color:var(--muted);margin-top:4px}
table.glance td small{color:var(--muted)}
table.glance tr.none td{color:var(--muted)}
table.glance td.few{color:var(--faint);font-style:italic}
details.pdet{border:1px solid var(--rule);border-radius:10px;background:var(--bg);margin-bottom:9px}
details.pdet summary{cursor:pointer;padding:11px 14px;display:flex;gap:10px;align-items:baseline;
list-style:none}
details.pdet summary::-webkit-details-marker{display:none}
details.pdet summary span{font-size:12.5px;color:var(--muted)}
details.pdet summary::after{content:"+";margin-left:auto;font-weight:700;color:var(--accent)}
details.pdet[open] summary::after{content:"–"}
details.pdet summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:9px}
details.pdet .pbody{padding:0 14px 12px}
details.method{margin-top:18px;background:transparent}
details.method .pbody p,details.method .pbody li{font-size:12.5px;color:var(--muted)}
table.glance td small{display:block;font-size:11.5px;color:var(--muted);margin-top:3px}
table.glance td.o a{color:inherit;border-bottom:1px dashed var(--faint)}
table.glance td.o a:hover{color:var(--accent);border-color:var(--accent)}
.vt{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--muted)}
.few{color:var(--faint);font-style:italic}
p.go{font-size:12.5px;color:var(--accent);font-weight:700;margin:6px 0 2px}
@media(max-width:820px){.ph li{grid-template-columns:minmax(0,1fr)}}

@media(max-width:1080px){.cols{grid-template-columns:minmax(0,1fr)}}
@media(max-width:820px){
.app{grid-template-columns:1fr}
.rail{position:static;height:auto;flex-direction:row;align-items:center;gap:12px;
overflow-x:auto;padding:10px 14px}
.rail nav{flex-direction:row;gap:4px}
.rail nav a{white-space:nowrap}
.content{padding:16px 16px 56px}
.topbar{padding:11px 16px}.stamp{display:none}
.sheet{padding:17px 16px;border-radius:9px}
.quote{grid-template-columns:minmax(0,1fr);gap:5px}
.heads li{grid-template-columns:minmax(0,1fr);gap:3px}
}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Newsreader:opsz,wght@6..72,400;6..72,600;6..72,700&'
         'family=Source+Sans+3:wght@400;600;700&display=swap">')

# Inline so the pages work from the filesystem with no network and no build step.
ICON = {
 "eye": '<svg viewBox="0 0 24 24" fill="none" stroke="#052A25" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 12S5 5.5 12 5.5 22.5 12 22.5 12S19 18.5 12 18.5 1.5 12 1.5 12Z"/><circle cx="12" cy="12" r="2.6"/></svg>',
 "grid": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
 "doc": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2.5H7A1.5 1.5 0 0 0 5.5 4v16A1.5 1.5 0 0 0 7 21.5h10A1.5 1.5 0 0 0 18.5 20V7L14 2.5Z"/><path d="M13.5 2.5V7.5h5"/></svg>',
 "info": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="M12 11v6M12 7.5v.01"/></svg>',
 "person": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7.5 8-7.5s8 3.1 8 7.5"/></svg>',
 "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m16.5 16.5 4 4"/></svg>',
 "arrow": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>',
}

# Four places, each a page a reader can name. Readers testing the site found the
# earlier eight links - several of them jumps to panels on the dashboard - more
# to take in than to use.
NAV = (("index.html", "grid", "Stories"),
       ("people.html", "person", "People"),
       ("search.html", "search", "Search"),
       ("index.html#about", "info", "How it works"))


def e(text):
    return html.escape(str(text if text is not None else ""))


def web_link(url):
    """An article URL safe for href, or "". Escaping does not stop a feed's
    "javascript:" link from running when clicked; only http(s) leaves the site."""
    return e(url) if is_web_url(url) else ""


def article_link(url, text):
    """The headline as a link to the original, or as plain text if the URL is unsafe."""
    link = web_link(url)
    if not link:
        return f"<span>{text}</span>"
    return f'<a href="{link}" target="_blank" rel="noopener noreferrer">{text}</a>'


def trim(text, limit):
    """Cut at a word boundary, never mid-word.

    Slicing produced "one of the organization's most" and "from 2015 t". The
    coverage matrix is the most trustworthy thing on the page and ragged
    truncation undercut it.
    """
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # prefer a sentence end, then a word boundary
    for stop in (". ", "? ", "! "):
        at = cut.rfind(stop)
        if at > limit * 0.6:
            return cut[:at + 1]
    at = cut.rfind(" ")
    return (cut[:at] if at > 0 else cut).rstrip(" ,;:") + "…"


def listing(names):
    """'A', 'A and B', 'A, B and C'."""
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def plural(n, word, many=None):
    return f"{n} {word if n == 1 else many or word + 's'}"


def some_of(k, n):
    """'The one fact was', '1 of the 5 facts was', '4 of the 5 facts were'."""
    if n == 1:
        return "The one fact found was"
    return f"{k} of the {n} facts {'was' if k == 1 else 'were'}"


def read_outlets(cluster):
    """(outlets we could read, outlets we could not). An outlet with one readable
    article and one blocked one was read, and is not also listed as unread."""
    read = sorted({a["source"] for a in cluster["articles"] if a["fetched"]})
    unread = sorted({a["source"] for a in cluster["articles"] if not a["fetched"]} - set(read))
    return read, unread


def coverage_table(cluster):
    """Facts down the side, the outlets we could read across the top.

    Outlets that could not be read used to get a column of question marks. Readers
    had to learn that "?" was not "left it out"; now they are named once, above
    the table, and the table holds only what can be compared.
    """
    read, unread = read_outlets(cluster)
    if not cluster["consensus"] or not read:
        return '<p class="empty">No fact was reported by more than one outlet we could open.</p>'

    head = "".join(f'<th scope="col">{e(o)}</th>' for o in read)
    rows, carried = [], dict.fromkeys(read, 0)
    for group in cluster["consensus"]:
        reported = set(group.get("reported_by") or [])
        # analyses saved before NLI checked each match have no "related" key
        related = {r["source"]: r["text"] for r in group.get("related") or []}
        cells = []
        for o in read:
            if o in reported:
                cells.append('<td class="m y" title="reported this">&check;</td>')
                carried[o] += 1
            elif o in related:
                cells.append('<td class="m r" title="reported something similar">&asymp;</td>')
            else:
                cells.append('<td class="m n" title="did not report this">&mdash;</td>')
        fact = e(trim(group["anchor"]["text"], 170))
        if related:
            said = "".join(f'<p><b>{e(o)}:</b> {e(trim(text, 220))}</p>'
                           for o, text in related.items())
            fact += (f'<details class="rel"><summary>&asymp; what '
                     f'{e(listing(related))} said instead</summary>{said}</details>')
        rows.append(f'<tr><td class="f">{fact}</td>{"".join(cells)}</tr>')

    total = len(cluster["consensus"])
    foot = "".join(f'<td>{carried[o]} of {total}</td>' for o in read)
    missing = (f'<p class="hint">Not in the table: {e(listing(unread))}. We could not open '
               f'{"its article" if len(unread) == 1 else "their articles"} (paywall or '
               f'blocked), so we cannot say what {"it" if len(unread) == 1 else "they"} '
               f'reported.</p>' if unread else "")
    return (
        '<div class="legend"><span><i class="y">&check;</i> reported it</span>'
        '<span><i class="r">&asymp;</i> reported something similar</span>'
        '<span><i class="n">&mdash;</i> did not report it</span></div>'
        + missing
        + '<p class="swipe">Swipe the table sideways to see every outlet &rarr;</p>'
        + '<div class="scroll"><table><thead><tr>'
        f'<th scope="col">What was reported</th>{head}</tr></thead><tbody>'
        f'{"".join(rows)}</tbody><tfoot><tr><td>Reported</td>{foot}</tr>'
        '</tfoot></table></div>'
    )


def headline_list(cluster):
    items = []
    for article in cluster["articles"]:
        unread = "" if article["fetched"] else '<span class="unread">could not open</span>'
        items.append(
            f'<li><div><span class="hsrc">{e(article["source"])}{unread}</span></div>'
            f'{article_link(article.get("url"), e(article["title"]))}</li>')
    return f'<ul class="heads">{"".join(items)}</ul>'


def framing_block(cluster):
    """One line per person: each outlet's overall reading. The sentences behind it
    are folded, because each is scored on its own and can read differently from
    the outlet's overall label - shown open, that difference needed explaining."""
    records = [f for f in (cluster.get("framing") or []) if f.get("sources")]
    if not records:
        return ""
    out = []
    for record in records[:3]:
        entries = sorted(record["sources"], key=lambda s: -s["score"])
        pills = "".join(f'<span class="pill">{e(s["source"])}: <b>{e(s["frame"])}</b></span>'
                        for s in entries)
        # NewsMTSC scores people only (TARGETED_ENT_TYPES); a place or body named
        # here was read from its sentences' tone, and says so
        sentence_only = all(s.get("scored_by", "sentence") == "sentence" for s in entries)
        how = '<small>tone of the sentences naming it</small>' if sentence_only else ""
        examples = "".join(
            f'<div class="quote"><div><span class="qsrc">{e(s["source"])}</span>'
            f'<span class="qtone">{plural(s.get("mentions", 1), "mention")}</span></div>'
            f'<blockquote>{e(trim(s.get("example"), 230))}<span class="qmark">this sentence '
            f'on its own reads {e(s.get("example_frame") or s["frame"])}</span></blockquote></div>'
            for s in entries)
        out.append(f'<div class="trow"><div><b>{e(record["entity"])}</b>{how}</div>'
                   f'<div class="pills">{pills}</div></div>'
                   f'<details class="ex"><summary>Example sentences</summary>{examples}</details>')
    targeted = any(entry.get("scored_by") in ("targeted", "mixed")
                   for record in records[:3] for entry in record["sources"])
    how = ('For a person, each outlet’s overall attitude toward them across its sentences, '
           'read by NewsMTSC, a model trained on news; for a place or organisation, the '
           'tone of the sentences naming it.' if targeted else
           'The overall tone of each outlet’s sentences naming them, which follows the '
           'events as much as the name.')
    return ('<h3 class="sub" id="tone">How they were described</h3>'
            f'<p class="hint">{how} A hint, not a verdict: it can be wrong.</p>'
            + "".join(out))


# how a version of a quote relates to the first outlet's, in a reader's words
QUOTE_RELATION = {
    "same": ("Same words", "q-same"),
    "says more": ("Adds to it", "q-more"),
    "says less": ("Shorter version", "q-less"),
    "worded differently": ("Worded differently", "q-diff"),
    "not compared": ("Not compared", "q-none"),
}


def marked(text, other):
    """text with the words that other does not have highlighted."""
    words, theirs = text.split(), [w.lower().strip(".,;:!?“”\"'") for w in other.split()]
    mine = [w.lower().strip(".,;:!?“”\"'") for w in words]
    keep = set()
    for block in difflib.SequenceMatcher(a=mine, b=theirs, autojunk=False).get_matching_blocks():
        keep.update(range(block.a, block.a + block.size))
    return " ".join(e(w) if i in keep else f"<mark>{e(w)}</mark>" for i, w in enumerate(words))


# remarks shown open; the rest are one click away, so the page does not open on a
# wall of quotations
SHOWN_REMARKS = 2


def quotes_block(cluster):
    """Who was quoted, and each outlet's version side by side where they overlap."""
    remarks = cluster.get("quotes") or []
    if not remarks:
        return ""
    shared = [r for r in remarks if r["outlets"] > 1]
    single = [r for r in remarks if r["outlets"] == 1]
    out = []
    for remark in shared:
        if len(out) == SHOWN_REMARKS:
            out.append('<details class="pdet"><summary><b>More remarks</b><span>'
                       f'{plural(len(shared) - SHOWN_REMARKS, "other remark")} quoted by '
                       'several outlets</span></summary><div class="pbody">')
        first = remark["versions"][0]
        rows = []
        for v in remark["versions"]:
            quote = trim(v["quote"], 320)
            # mark what a longer version adds; a shorter one simply reads short
            body = marked(quote, first["quote"]) if v["relation"] == "says more" else e(quote)
            label = "" if v is first else (
                f'<span class="vrel {QUOTE_RELATION[v["relation"]][1]}">'
                f'{QUOTE_RELATION[v["relation"]][0]}</span>')
            rows.append(f'<div class="ver"><span class="vsrc">{e(v["source"])}</span>'
                        f'<div><blockquote>“{body}”</blockquote>{label}</div></div>')
        out.append(f'<div class="remark"><div class="rhead"><b>{e(remark["speaker"] or "Unattributed")}</b>'
                   f'<span>quoted by {remark["outlets"]} outlets</span></div>{"".join(rows)}</div>')
    if len(shared) > SHOWN_REMARKS:
        out.append('</div></details>')
    others = ""
    if single:
        items = "".join(
            f'<li><b>{e(r["speaker"] or "Unattributed")}</b> &middot; {e(r["versions"][0]["source"])}'
            f'<span>“{e(trim(r["versions"][0]["quote"], 220))}”</span></li>'
            for r in single)
        people = len({r["speaker"] for r in single if r["speaker"]})
        others = (f'<details class="pdet"><summary><b>Other quotes</b><span>{len(single)} from '
                  f'{people} people, each in one outlet</span></summary>'
                  f'<ul class="qlist">{items}</ul></details>')
    hint = ('<p class="hint">The same remark as each outlet printed it. Highlighted words '
            'are ones the first outlet left out.</p>' if shared else "")
    return '<h3 class="sub" id="quotes">What was said</h3>' + hint + "".join(out) + others


def _figure_row(row):
    tags = []
    if row.get("credited_to"):
        tags.append(f'according to {e(row["credited_to"])}')
    if row.get("cumulative"):
        tags.append("running total")
    if row.get("currency") and row["currency"] != "unspecified":
        tags.append(e(row["currency"]).upper())
    if row.get("breakdown"):
        tags.append("of which " + ", ".join(e(b) for b in row["breakdown"][:3]))
    tagging = "".join(f'<span class="ftag">{t}</span>' for t in tags)
    link = web_link(row.get("url"))
    more = (f' <a href="{link}" target="_blank" rel="noopener noreferrer">'
            f'read the original</a>') if link else ""
    return (f'<div class="fig"><div class="fhead">'
            f'<span class="fnum">{e(row["figure"])}</span>'
            f'<span class="fsrc">{e(row["source"])}</span>{tagging}</div>'
            f'<p class="fctx">{figure_in_context(row)}{more}</p></div>')


def figure_in_context(row, limit=280):
    """The context with the figure in bold, cut around the figure.

    The excerpt used to be cut from its start, so a figure late in a long
    passage could fall outside it, and the reader had to hunt for the number the
    row is about. The figure's own sentence is searched first, so a number that
    also appears in the sentence before is not the one marked.
    """
    text = " ".join((row.get("context") or row["sentence"] or "").split())
    figure = " ".join((row.get("figure") or "").split())
    sentence = " ".join((row.get("sentence") or "").split())
    base = text.find(sentence) if sentence else -1
    at = text.find(figure, max(base, 0)) if figure else -1
    if at < 0 and figure:
        at = text.find(figure)
    if at < 0:
        return e(trim(text, limit))
    start = max(0, at - limit // 2)
    end = min(len(text), max(start + limit, at + len(figure)))
    if start > 0:
        start = text.find(" ", start, at) + 1 or start
    if end < len(text):
        cut = text.rfind(" ", at + len(figure), end)
        end = cut if cut > 0 else end
    before, after = text[start:at], text[at + len(figure):end]
    return ("…" if start > 0 else "") + e(before) + f"<strong>{e(figure)}</strong>" \
        + e(after) + ("…" if end < len(text) else "")


def figures_block(cluster):
    digest = cluster.get("figure_digest") or []
    groups = digest_groups(digest)
    out = []

    for group in groups:
        out.append(f'<p class="fgroup">{len(group["sources"])} outlets gave a figure in '
                   f'<b>{e(group["unit"])}</b> for the same thing:</p>')
        out.extend(_figure_row(row) for row in group["values"])

    # Figures no other outlet matched. They used to be dropped, which lost the
    # most striking number in the Murkomen story: 121,000 young people
    # incarcerated, reported by one paper alone. Not comparable is not the same
    # as not worth seeing - it just cannot be set beside anything.
    #
    # Two different reasons a figure ends up unpaired, and conflating them told
    # the reader something false. Some really were the only figure of their kind.
    # Others came from several outlets in the same unit but were too far apart to
    # present as one quantity - $5m for an anti-doping programme beside KES 2bn
    # of sponsorship. Filing those under "reported by one outlet only" was a
    # claim about the coverage that was simply untrue. They get their own section
    # with the numbers and the sentences intact, and no assertion either way.
    paired = {id(row) for group in groups for row in group["values"]}
    unpaired = [r for r in digest if r["unit"] and id(r) not in paired]
    units_with_peers = {r["unit"] for r in unpaired if r["peers"]}
    ungrouped = [r for r in unpaired if r["unit"] in units_with_peers]
    solo = [r for r in unpaired if r["unit"] not in units_with_peers]

    #
    # Both kinds are folded: they cannot be compared, and shown open they made the
    # longest section of the page the one with the least to compare.
    extra = []
    if ungrouped:
        extra.append('<h4 class="fsub">Same kind of figure, possibly not the same thing</h4>'
                     '<p class="hint">Too far apart to call one quantity: a national total and '
                     'a county total can both be true. Read the sentences.</p>')
        extra.extend(_figure_row(row) for row in ungrouped)
    if solo:
        extra.append('<h4 class="fsub">Reported by one outlet only</h4>')
        extra.extend(_figure_row(row) for row in solo)
    if extra:
        lead = "More numbers" if out else "Numbers in this story"
        out.append(f'<details class="pdet"><summary><b>{lead}</b><span>'
                   f'{plural(len(ungrouped) + len(solo), "figure")} with nothing to set '
                   f'beside</span></summary><div class="pbody">{"".join(extra)}</div></details>')

    if not out:
        return ('<p class="empty">No outlet published a figure we could classify '
                'for this story.</p>')
    return "".join(out)


def rail(active):
    items = []
    for href, icon, label in NAV:
        on = ' class="on"' if label == active else ""
        items.append(f'<a href="{href}"{on}>{ICON[icon]}<span>{e(label)}</span></a>')
    return (
        '<aside class="rail">'
        f'<div class="brand"><span class="glyph">{ICON["eye"]}</span><b>Newseye</b></div>'
        f'<nav>{"".join(items)}</nav>'
        '</aside>')


def shell(title, active, body, generated, search="link", scripts=""):
    """The page frame. search is how the top bar's box behaves: "filter" narrows
    the dashboard's stories as you type, "link" sends the query to the search
    page, and None leaves the box out (the search page has its own)."""
    box = ""
    if search:
        hint = ("Find a story, or press Enter to search every article"
                if search == "filter" else "Search every article")
        ident = ' id="q"' if search == "filter" else ""
        box = (f'<form class="search" action="search.html" role="search">{ICON["search"]}'
               f'<input type="search" name="q" placeholder="{e(hint)}" '
               f'aria-label="{e(hint)}" autocomplete="off"{ident}></form>')
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{e(title)}</title>\n{FONTS}\n<style>{CSS}</style>\n</head>\n<body>\n'
        f'<div class="app">{rail(active)}<div class="main">'
        f'<div class="topbar">{box}'
        f'<span class="stamp">Updated {e(generated)}</span></div>'
        f'<div class="content">{body}</div></div></div>\n'
        + (SEARCH_JS if search == "filter" else "")
        + scripts
        + "\n</body>\n</html>\n"
    )


# Real, not decorative: the dashboard ships every story's headline and outlet
# list in the markup, so filtering needs no server and no network.
SEARCH_JS = """<script>
(function(){
  var q=document.getElementById('q'); if(!q) return;
  var tiles=[].slice.call(document.querySelectorAll('.tile'));
  var count=document.getElementById('shown');
  var none=document.getElementById('nores');
  q.addEventListener('input',function(){
    var t=q.value.trim().toLowerCase(), n=0;
    tiles.forEach(function(el){
      var hit=!t||(el.dataset.find||'').indexOf(t)>-1;
      el.style.display=hit?'':'none'; if(hit)n++;
    });
    if(count) count.textContent=n+(n===1?' story':' stories');
    if(none) none.style.display=n?'none':'';
  });
})();
</script>"""


def gaps_in(cluster):
    """Facts that not every readable outlet reported word for word."""
    return sum(1 for g in cluster["consensus"] if g.get("omitted_by") or g.get("related"))


def story_tile(cluster):
    """Headline, who covered it, and in a few words what differs.

    The tile used to carry a bar of "0 carried by all / 4 not", which readers had
    to decode, and two outlet chips that looked like the only outlets. It now says
    the same things in words.
    """
    sources = sorted({a["source"] for a in cluster["articles"]})
    gaps = gaps_in(cluster)
    tiers = summarise(cluster.get("figure_digest") or [])
    coherence = cluster.get("coherence") or 0

    badges = []
    if gaps:
        badges.append(f'<span class="badge gap">{plural(gaps, "fact")} only some '
                      f'outlets reported</span>')
    else:
        badges.append('<span class="badge ok">same facts in every outlet we read</span>')
    if tiers["shared"]:
        badges.append(f'<span class="badge fig">{plural(tiers["shared"], "number")} '
                      f'to compare</span>')
    if coherence and coherence < 0.5:
        badges.append('<span class="badge loose">may mix two stories</span>')

    named = ", ".join(sources[:3]) + (f" and {len(sources) - 3} more" if len(sources) > 3 else "")
    find = " ".join([cluster.get("title_summary") or "", cluster.get("subject") or "",
                     cluster.get("topic_label") or ""] + sources).lower()
    return (
        f'<a class="tile" href="story-{cluster["cluster_id"]}.html" '
        f'data-find="{e(find)}">'
        f'<div class="chips"><span class="chip">{e(cluster.get("topic_label") or "General")}'
        '</span></div>'
        f'<h3>{e(trim(cluster.get("title_summary") or "Untitled story", 96))}</h3>'
        f'<div class="srcline">{ICON["doc"]}<span>{len(sources)} outlets: {e(named)}</span></div>'
        f'<div class="badges">{"".join(badges)}</div></a>')


def dashboard(clusters, generated, stats, people=None, selection=None):
    """What Newseye is for, then the stories.

    Readers shown the earlier version asked what they were looking at and what
    they were meant to do. Four counter cards and six side panels came before any
    answer. The page now says what it is and what to do in three steps; the
    explanations it used to show open are folded under "How it works".
    """
    tiles = "".join(story_tile(c) for c in clusters)
    unread = sorted({a["source"] for c in clusters for a in c["articles"]
                     if not a["fetched"]})
    # a demonstration set is chosen for what it shows, and says so: contested
    # stories are not a typical day's mix
    chosen = (' These stories were picked to show every kind of comparison, so they are '
              'more contested than a typical day.' if selection == "showcase" else "")
    body = (
        '<section class="intro"><h1>See how Kenyan outlets cover the same story</h1>'
        f'<p>Newseye reads {stats["outlets"]} Kenyan news sites, groups the articles about '
        'each event, and shows what each outlet reported, who it quoted and which numbers '
        'it gave. It does not say who is right: you compare.</p>'
        '<ol class="steps"><li>Pick a story</li><li>See what each outlet reported, side by '
        'side</li><li>Open the original articles</li></ol>'
        f'<p class="meta">{stats["usable"]:,} stories &middot; {stats["articles"]:,} '
        f'articles &middot; updated {e(generated)}. A demonstration on real data: nothing '
        f'here is made up.{chosen}</p></section>'

        '<div class="cols"><div>'
        '<div class="colhead" id="stories"><h2>Stories</h2>'
        f'<span class="hint"><span id="shown">{plural(len(clusters), "story", "stories")}'
        '</span> &middot; most outlets first</span></div>'
        f'<div class="grid">{tiles}</div>'
        '<div class="empty-grid" id="nores" style="display:none">No story on this page '
        'matches that. Press Enter to search every article.</div>'
        '</div><div>'
        + differ_panel(clusters)
        + people_panel(people)
        + about_panel(unread)
        + '</div></div>'
        + OPEN_TARGET
    )
    return shell("Newseye - Kenyan media coverage", "Stories", body, generated,
                 search="filter")


def about_panel(unread):
    """The caveats a reader needs once, folded until they ask."""
    blocked = (f'<p><b>Some sites could not be opened</b> (paywall or blocked): '
               f'{e(listing(unread))}. They are never counted as leaving something '
               'out.</p>' if unread else "")
    return (
        '<details class="howto" id="about"><summary>How it works</summary><div class="pbody">'
        '<p><b>Not reported is not wrong.</b> An outlet may leave a fact out because it ran '
        'a shorter piece or filed earlier. The gap shows what you would miss by reading only '
        'that outlet.</p>'
        + blocked
        + '<p><b>What it does not do.</b> It does not rate outlets, decide which number is '
        'right, or call anything false. Where two numbers are too far apart to be the same '
        'thing, both are shown with their sentences.</p>'
        '<p><b>Where it comes from.</b> Headlines and opening lines from each outlet’s '
        'public feed, checked every two hours; the article text is read once and not '
        'kept.</p></div></details>')


def story_page(cluster, generated, people_here=()):
    coherence = cluster.get("coherence") or 0
    sources = len({a["source"] for a in cluster["articles"]})
    loose = ""
    if coherence and coherence < 0.5:
        loose = (f'<div class="loose"><b>We are not confident these are one story.</b> '
                 f'These articles score {coherence:.2f} on our similarity check, below the '
                 f'0.50 floor. Asking who left a fact out only means something when every '
                 f'outlet is covering the same event, so read the comparison below with '
                 f'that in mind.</div>')
    body = (
        f'<a class="back" href="index.html">{ICON["arrow"]}All stories</a>'
        '<div class="sheet"><header>'
        f'<h1>{e(trim(cluster.get("title_summary") or "Untitled story", 110))}</h1>'
        f'<p class="lede">How {sources} Kenyan outlets covered this story.</p>'
        '</header>'
        + loose
        + story_glance(cluster)
        + '<h3 class="sub">Headlines</h3>' + headline_list(cluster)
        + people_chips(people_here)
        + '<h3 class="sub" id="facts">What each outlet reported</h3>'
        + '<p class="hint">Each row is a fact from one of the articles. Read across to see '
          'which outlets reported it.</p>'
        + coverage_table(cluster)
        + quotes_block(cluster)
        + framing_block(cluster)
        + '<h3 class="sub" id="numbers">The numbers</h3>'
        + '<p class="hint">Each number with the sentence it came from. Read the sentence: '
          'two numbers can count different things.</p>'
        + figures_block(cluster)
        + '<footer class="end">Newseye compares what each outlet included. It does not '
          'rate outlets or tell you who to trust.</footer></div>'
    )
    return shell(cluster.get("title_summary") or "Story", "Stories", body, generated)


def story_glance(cluster):
    """The story's comparison in three or four sentences, before any table.

    Facts, not findings: each sentence counts something the sections below show,
    and links to it.
    """
    read, unread = read_outlets(cluster)
    sources = len(read) + len(unread)
    if not unread:
        points = [f"We could open all {sources} outlets' articles."]
    else:
        points = [f"We could open {len(read)} of the {sources} outlets' articles. "
                  f"{e(listing(unread))} could not be opened (paywall or blocked)."]

    groups = cluster["consensus"] or []
    if groups:
        alone = Counter(g["reported_by"][0] for g in groups if len(g.get("reported_by") or []) == 1)
        gaps = gaps_in(cluster)
        if not gaps:
            points.append(f"Every outlet we could open reported the same "
                          f"{plural(len(groups), 'fact')}.")
        elif alone:
            only = sum(alone.values())
            who = (f"only by {e(next(iter(alone)))}" if len(alone) == 1 else
                   "by only one outlet: " + e(", ".join(f"{o} {n}" for o, n in alone.most_common())))
            more = (f" {plural(gaps - only, 'other fact')} {'was' if gaps - only == 1 else 'were'} "
                    "left out by at least one outlet." if gaps > only else "")
            points.append(f"{some_of(only, len(groups))} reported {who}.{more} "
                          "<a href=\"#facts\">See which</a>")
        else:
            points.append(f"{some_of(gaps, len(groups))} left out by at least one outlet. "
                          "<a href=\"#facts\">See which</a>")

    shared = [r for r in cluster.get("quotes") or [] if r["outlets"] > 1]
    if shared:
        same = sum(1 for r in shared if all(v["relation"] in ("first", "same") for v in r["versions"]))
        changed = sum(1 for r in shared if any(v["relation"] in ("says more", "says less",
                                                                  "worded differently")
                                               for v in r["versions"]))
        how = [part for part in (f"{same} word for word" if same else "",
                                 f"{changed} in different words" if changed else "") if part]
        points.append(f"{plural(len(shared), 'remark')} {'was' if len(shared) == 1 else 'were'} "
                      f"quoted by more than one outlet{': ' + ' and '.join(how) if how else ''}. "
                      "<a href=\"#quotes\">Compare them</a>")

    numbers = digest_groups(cluster.get("figure_digest") or [])
    if numbers:
        points.append(f"{plural(len(numbers), 'number')} {'was' if len(numbers) == 1 else 'were'} "
                      "given by more than one outlet. <a href=\"#numbers\">See them side by "
                      "side</a>")

    items = "".join(f"<li>{p}</li>" for p in points)
    return f'<div class="atglance"><b class="t">At a glance</b><ul>{items}</ul></div>'


# Five of the feeds put HTML in their summaries, and ingestion cuts summaries at
# 150 characters, so a tag can arrive with no closing ">".
MARKUP = re.compile(r"<[^>]*(?:>|$)")
# WordPress ends every summary with "The post <a ...>Title</a> appeared first on"
FEED_FOOTER = re.compile(r"<p>The post <a.*", re.S)


def plain(text):
    """A feed summary as readable text."""
    return html.unescape(MARKUP.sub(" ", FEED_FOOTER.sub("", text or "")))


def search_index(clusters):
    """Every article in the database, for the search page. None without a database.

    The vectors are the stored MiniLM embeddings, the ones clustering used, cut to
    int8 with one scale per article: a quarter of the size, and no search score
    moves by more than 0.002. Articles
    that share a coherent cluster are marked as one story, so the page can show
    the story rather than each outlet's copy of it; a loose cluster is not one
    story, so its articles stand alone.
    """
    import numpy as np

    try:
        from backend.config import CLUSTER_MIN_COHERENCE
        from backend.db.connection import get_cursor
        with get_cursor() as cur:
            cur.execute("""
                SELECT a.id, a.title, a.source_name, a.published_utc, a.url,
                       a.category, a.snippet, a.embedding, c.id AS story
                FROM articles a
                LEFT JOIN cluster_members cm ON cm.article_id = a.id
                LEFT JOIN clusters c ON c.id = cm.cluster_id AND c.coherence >= %s
                WHERE a.embedding IS NOT NULL
                ORDER BY a.published_utc DESC NULLS LAST, a.id
            """, (CLUSTER_MIN_COHERENCE,))
            rows = cur.fetchall()
            cur.execute("""
                SELECT c.id, c.topic_label, ca.title_summary
                FROM clusters c
                LEFT JOIN cluster_analysis ca ON ca.cluster_id = c.id
                WHERE c.coherence >= %s
            """, (CLUSTER_MIN_COHERENCE,))
            story_rows = {r["id"]: r for r in cur.fetchall()}
    except Exception as exc:
        print(f"  (search index unavailable: {type(exc).__name__})")
        return None

    # link by URL rather than cluster id: ids are reassigned on every clustering
    # run, and the story pages come from an export that may predate the last one
    pages = {a["url"]: f"story-{c['cluster_id']}.html"
             for c in clusters for a in c["articles"]}

    articles, vectors, stories, story_of, seen = [], [], [], {}, set()
    for row in rows:
        # a few URLs were ingested twice; a reader should see each article once
        if row["url"] in seen:
            continue
        seen.add(row["url"])
        story = -1
        if row["story"] is not None:
            if row["story"] not in story_of:
                story_of[row["story"]] = len(stories)
                meta = story_rows[row["story"]]
                stories.append([meta["title_summary"] or row["title"],
                                meta["topic_label"] or "General"])
            story = story_of[row["story"]]
        published = row["published_utc"]
        articles.append([
            row["title"],
            # "| Daily Nation" is a malformed name from an earlier feed config
            (row["source_name"] or "").strip(" |"),
            published.date().isoformat() if published else "",
            # the page script puts this in href; an unsafe scheme goes no further
            row["url"] if is_web_url(row["url"]) else "",
            row["category"] or "General",
            trim(plain(row["snippet"]), 140),
            story,
            pages.get(row["url"], ""),
        ])
        value = row["embedding"]
        vectors.append(value.strip("[]").split(",") if isinstance(value, str) else value)

    # a summary several articles share describes the feed, not the article: The
    # Kenya Times sends its site tagline as every summary
    repeats = Counter(a[5] for a in articles if a[5])
    for article in articles:
        if repeats[article[5]] >= 3:
            article[5] = ""

    matrix = np.asarray(vectors, dtype=np.float32)
    scales = np.abs(matrix).max(axis=1) / 127
    codes = np.round(matrix / scales[:, None]).astype(np.int8)
    dates = sorted(a[2] for a in articles if a[2])
    return {
        "count": len(articles),
        "first": dates[0] if dates else "",
        "last": dates[-1] if dates else "",
        "dim": matrix.shape[1],
        "articles": articles,
        "stories": stories,
        "codes": base64.b64encode(codes.tobytes()).decode("ascii"),
        "scales": base64.b64encode(scales.astype("<f4").tobytes()).decode("ascii"),
    }


# Runs in the reader's browser. The query is embedded by the same MiniLM model
# that embedded the articles, so a query and an article are compared exactly as
# backend/nlp/search.py compares them - and nothing typed leaves the machine.
SEARCH_PAGE_JS = r"""<script src="search-index.js"></script>
<script type="module">
const LIBRARY = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.0";
const MODEL = "Xenova/all-MiniLM-L6-v2";
// search.py's cut-off: cosine distance 0.75, so similarity 0.25
const MIN_SIMILARITY = 0.25;
// offline fallback: at least half the query's words must appear
const MIN_WORD_SHARE = 0.5;
const CANDIDATES = 120, SHOWN = 20, MEMBERS_SHOWN = 6;
const [TITLE, SOURCE, DATE, URL_, TOPIC, SNIPPET, STORY, PAGE] = [0, 1, 2, 3, 4, 5, 6, 7];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const form = document.getElementById("sform");
const input = document.getElementById("sq");
const status = document.getElementById("sstatus");
const out = document.getElementById("sresults");
const INDEX = window.NEWSEYE_INDEX;

const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]);
const day = d => d ? `${+d.slice(8, 10)} ${MONTHS[+d.slice(5, 7) - 1]}` : "";
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const buffer = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer;
const compare = page => page
  ? `<a class="hitlink" href="${esc(page)}">Compare what each outlet reported &rarr;</a>` : "";
// the index carries "" for any URL that is not http(s): plain text, never a link
const outLink = (url, text) => url
  ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`
  : `<span>${esc(text)}</span>`;

if (!INDEX) {
  status.textContent = "Search is not available in this build: the site was generated " +
                       "without the article database.";
  input.disabled = true;
} else {
  const articles = INDEX.articles;
  const codes = new Int8Array(buffer(INDEX.codes));
  const scales = new Float32Array(buffer(INDEX.scales));
  const members = INDEX.stories.map(() => []);
  articles.forEach((a, i) => { if (a[STORY] >= 0) members[a[STORY]].push(i); });
  const idle = `${INDEX.count.toLocaleString("en")} articles, ${day(INDEX.first)} to ` +
               `${day(INDEX.last)} ${INDEX.last.slice(0, 4)}. Matches meaning, not ` +
               `just words.`;
  status.textContent = idle;

  // start downloading the model at once, so it is usually ready by the first search
  let extractor = null;
  const ready = import(LIBRARY)
    .then(({ pipeline }) => pipeline("feature-extraction", MODEL, { dtype: "q8" }))
    .then(model => { extractor = model; });
  ready.catch(() => {});

  const semanticScores = query => {
    const scores = new Float32Array(articles.length);
    for (let i = 0, k = 0; i < articles.length; i++) {
      let dot = 0;
      for (let j = 0; j < INDEX.dim; j++, k++) dot += query[j] * codes[k];
      scores[i] = dot * scales[i];
    }
    return scores;
  };

  const wordScores = text => {
    const words = text.toLowerCase().match(/[a-z0-9']{3,}/g) || [];
    return Float32Array.from(articles, a => {
      const hay = `${a[TITLE]} ${a[SNIPPET]}`.toLowerCase();
      return words.length ? words.filter(w => hay.includes(w)).length / words.length : 0;
    });
  };

  // best match first; an article in a story brings the story, once
  const rank = (scores, floor) => {
    const hits = [];
    for (let i = 0; i < scores.length; i++) if (scores[i] >= floor) hits.push(i);
    hits.sort((a, b) => scores[b] - scores[a]);
    const seen = new Map();
    for (const i of hits.slice(0, CANDIDATES)) {
      const key = articles[i][STORY] >= 0 ? `s${articles[i][STORY]}` : `a${i}`;
      if (!seen.has(key)) seen.set(key, i);
    }
    return [...seen.values()].slice(0, SHOWN);
  };

  const storyCard = (story, scores) => {
    const list = members[story].slice().sort((a, b) => scores[b] - scores[a]);
    const outlets = new Set(list.map(i => articles[i][SOURCE]));
    const dates = list.map(i => articles[i][DATE]).filter(Boolean).sort();
    const span = dates.length && day(dates[0]) !== day(dates.at(-1))
      ? `${day(dates[0])} &ndash; ${day(dates.at(-1))}` : day(dates[0]);
    const [title, topic] = INDEX.stories[story];
    const rows = list.slice(0, MEMBERS_SHOWN).map(i => {
      const a = articles[i];
      return `<li><span class="hsrc">${esc(a[SOURCE])}</span>` +
             `${outLink(a[URL_], a[TITLE])}</li>`;
    }).join("");
    const more = list.length > MEMBERS_SHOWN
      ? `<p class="snip">and ${plural(list.length - MEMBERS_SHOWN, "more article")}</p>` : "";
    return `<article class="hit"><div class="chips"><span class="chip">${esc(topic)}</span>` +
           `<span class="chip">${plural(outlets.size, "outlet")}</span>` +
           (span ? `<span class="chip">${span}</span>` : "") + `</div>` +
           `<h3>${esc(title)}</h3><ul class="heads">${rows}</ul>${more}` +
           `${compare(list.map(i => articles[i][PAGE]).find(Boolean))}</article>`;
  };

  const articleCard = i => {
    const a = articles[i];
    return `<article class="hit"><div class="chips"><span class="chip">${esc(a[TOPIC])}</span>` +
           `<span class="chip">${esc(a[SOURCE])}</span>` +
           (a[DATE] ? `<span class="chip">${day(a[DATE])}</span>` : "") + `</div>` +
           `<h3>${outLink(a[URL_], a[TITLE])}</h3>` +
           (a[SNIPPET] ? `<p class="snip">${esc(a[SNIPPET])}</p>` : "") +
           `${compare(a[PAGE])}</article>`;
  };

  let latest = 0;
  const run = async text => {
    const token = ++latest;
    text = text.trim();
    try {
      const url = new URL(location.href);
      text ? url.searchParams.set("q", text) : url.searchParams.delete("q");
      history.replaceState(null, "", url);
    } catch (err) { /* file:// pages may refuse; the search still runs */ }
    if (!text) { out.innerHTML = ""; status.textContent = idle; return; }

    let semantic = true;
    if (!extractor) status.textContent = "Loading the language model (about 23 MB, " +
                                         "first search only)…";
    try { await ready; } catch (err) { semantic = false; }
    const scores = semantic
      ? semanticScores((await extractor(text, { pooling: "mean", normalize: true })).data)
      : wordScores(text);
    if (token !== latest) return;

    const shown = rank(scores, semantic ? MIN_SIMILARITY : MIN_WORD_SHARE);
    out.innerHTML = shown.map(i => articles[i][STORY] >= 0
      ? storyCard(articles[i][STORY], scores) : articleCard(i)).join("")
      || `<p class="empty">Nothing in the collection is close to “${esc(text)}”.</p>`;
    status.textContent = semantic
      ? `Closest matches for “${text}” across ${INDEX.count.toLocaleString("en")} articles.`
      : `Couldn’t load the language model, which needs an internet connection the ` +
        `first time. Showing word matches for “${text}” instead.`;
  };

  form.addEventListener("submit", event => { event.preventDefault(); run(input.value); });
  const initial = new URLSearchParams(location.search).get("q");
  if (initial) { input.value = initial; run(initial); }
}
</script>"""


def search_page(generated):
    body = (
        '<div class="sheet"><header>'
        '<h1>Search every article</h1>'
        '<p class="lede">Everything Newseye has collected, not only the stories on the '
        'dashboard. Articles that several outlets wrote about the same event are shown '
        'together as one story.</p></header>'
        f'<form id="sform" class="bigsearch" role="search">{ICON["search"]}'
        '<input id="sq" name="q" type="search" autocomplete="off" '
        'placeholder="e.g. police shot protesters" aria-label="Search every article">'
        '<button type="submit">Search</button></form>'
        '<p class="hint" id="sstatus"></p><div id="sresults"></div>'
        '<footer class="end">The search runs in your browser. The first search downloads a '
        'small language model; what you type is never sent anywhere.</footer></div>'
    )
    return shell("Search - Newseye", "Search", body, generated, search=None,
                 scripts=SEARCH_PAGE_JS)


def corpus_stats(clusters):
    """Totals for the dashboard's opening lines, with a fallback when the DB is absent."""
    stats = {"usable": len(clusters), "articles": 0, "outlets": len(RSS_FEEDS)}
    try:
        from backend.db.connection import get_cursor
        with get_cursor() as cur:
            cur.execute("SELECT count(*) n FROM articles")
            stats["articles"] = cur.fetchone()["n"]
            cur.execute("SELECT count(*) n FROM clusters WHERE coherence >= 0.50")
            stats["usable"] = cur.fetchone()["n"]
    except Exception as exc:
        # the export alone is enough to render; the page just loses the corpus totals
        print(f"  (corpus totals unavailable: {type(exc).__name__}) ")
    # the configured feed list, not DISTINCT source_name: the articles table still
    # carries 61 rows under "| Daily Nation", a malformed name from an earlier
    # feed config, and counting it would claim an outlet we do not poll
    return stats


# ---------------------------------------------------------------------------
# People: how each outlet presents one public figure
# ---------------------------------------------------------------------------
# A person gets a page once this many articles name them, from at least two
# outlets: below that there is nothing to set side by side.
PEOPLE_MIN_ARTICLES = 6
PEOPLE_MIN_OUTLETS = 2
# outlets that named them less often than this are listed, not broken down
PEOPLE_CARD_MIN = 3
FEEDS = {feed["name"] for feed in RSS_FEEDS}
# How a headline presents the person, in the same words everywhere on the page:
# the table says "Mostly named in passing", a headline "named in passing". The
# outlet cards used to name these "Speaking", "Acted on", "In others' words" and
# colour-code them, which readers had to learn from a key before anything made sense.
ROLE_ORDER = (
    ("speaks", "quoted speaking", "the headline reports their words"),
    ("acts", "shown doing something", "they are the one acting"),
    ("acted on", "on the receiving end", "something is done or said to them"),
    ("spoken about", "talked about by others", "they appear inside someone else's quoted words"),
    ("described", "described", "the sentence says what they are"),
    ("mentioned", "named in passing", "named, with none of the above"),
)
ROLE_WORDS = {role: words for role, words, _ in ROLE_ORDER}
ROLE_PHRASE = {role: f"Mostly {words}" for role, words in ROLE_WORDS.items()}
# Facts about two of the feeds that a reader needs to read their counts:
# covering government is their remit, not something these pages discovered.
STATE_MEDIA = {"KBC": "state broadcaster", "Kenya News": "government news agency"}
QUOTED = "quoted directly"
IRREGULAR = {"have": "has", "be": "is", "do": "does", "go": "goes"}


def people_data():
    """How each outlet presents every listed person named often enough to compare.

    Reads stored headlines and snippets only, so a paywalled outlet counts as
    fully as a readable one. None without a database, like the search index.
    """
    try:
        from backend.analysis.portrayal import corpus_context, portray
        from backend.nlp.entities import load_nlp, people
        nlp = load_nlp(lemmas=True)
        context = corpus_context()
        found = []
        for ident, entry in people().items():
            outlets, totals = portray(ident, nlp=nlp, context=context)
            outlets = {o: s for o, s in outlets.items() if o in FEEDS}
            articles = sum(s["articles"] for s in outlets.values())
            if articles >= PEOPLE_MIN_ARTICLES and len(outlets) >= PEOPLE_MIN_OUTLETS:
                found.append({"id": ident, "name": entry["name"],
                              "aliases": entry.get("aliases", []), "outlets": outlets,
                              "totals": {o: n for o, n in totals.items() if o in FEEDS},
                              "articles": articles})
    except Exception as exc:
        print(f"  (people pages unavailable: {type(exc).__name__}: {exc})")
        return None
    found.sort(key=lambda p: -p["articles"])
    return {"people": found, "first": context["first"], "last": context["last"]}


def headline_tense(phrase):
    """'urge' -> 'urges', 'hit back at' -> 'hits back at': the tense headlines use."""
    if not phrase or phrase in (QUOTED, "according to"):
        return phrase or ""
    first, _, rest = phrase.partition(" ")
    if first in IRREGULAR:
        first = IRREGULAR[first]
    elif first.endswith(("ss", "sh", "ch", "x", "z", "o")):
        first += "es"
    elif first.endswith("s"):
        pass   # already inflected: the parser sometimes leaves "mobilizes" whole
    elif first.endswith("y") and first[-2:-1] not in "aeiou":
        first = first[:-1] + "ies"
    else:
        first += "s"
    return f"{first} {rest}".strip()


def role_sentence(name, s, limit=3):
    """'Ruto is quoted speaking in 32% of mentions, shown doing something in 30% and
    named in passing in 20%.' The outlet's split in words, not a colour bar."""
    total = s["mentions"] or 1
    shares = sorted(((n / total, role) for role, n in s["roles"].items() if n), reverse=True)
    parts = [f"{ROLE_WORDS[role]} in {share:.0%}" + (" of mentions" if i == 0 else "")
             for i, (share, role) in enumerate(shares[:limit])]
    return f"{e(name)} is {e(listing(parts))}." if parts else ""


def outlet_label(outlet):
    own = STATE_MEDIA.get(outlet)
    return e(outlet) + (f"<small>{e(own)}</small>" if own else "")


def day(stamp):
    return f"{stamp.day} {stamp:%b}"


def people_chips(people_here):
    if not people_here:
        return ""
    chips = "".join(f'<a class="pchip" href="person-{e(ident)}.html">{e(name)}</a>'
                    for ident, name in people_here)
    return ('<p class="hint">People in this story: open one to see how each outlet covers '
            f'them across all stories.</p><div class="pchips">{chips}</div>')


def differ_panel(clusters, limit=5):
    """The stories where outlets' coverage differs most, each with its reasons.

    Counts only differences a reader can check on the story page - related
    wording, figures, reworded quotes, a wide tone gap - never a verdict about
    which outlet is right. The reasons are shown so a story's place is never a
    mystery, and stories with no checkable difference are left out.
    """
    from backend.analysis.divergence import differences

    scored = [(differences(c), c) for c in clusters]
    scored = sorted((t for t in scored if t[0]["score"]), key=lambda t: -t[0]["score"])[:limit]
    if not scored:
        return ""
    rows = "".join(
        f'<div class="r"><b>{i}</b><div><a href="story-{c["cluster_id"]}.html">'
        f'<span>{e(trim(c.get("title_summary") or "Untitled story", 80))}</span></a>'
        f'<small>{e(" · ".join(d["reasons"]))}</small></div></div>'
        for i, (d, c) in enumerate(scored, start=1))
    return ('<div class="panel"><h4>Start here: where outlets differ most</h4>'
            f'<div class="rank">{rows}</div></div>')


def people_panel(people):
    if not people or not people["people"]:
        return ""
    rows = "".join(
        f'<div class="r"><b>{i}</b><div><a href="person-{e(p["id"])}.html">'
        f'<span>{e(p["name"])}</span></a>'
        f'<small>{p["articles"]} articles &middot; {len(p["outlets"])} outlets</small></div></div>'
        for i, p in enumerate(people["people"][:6], start=1))
    return ('<div class="panel"><h4>People in the news</h4>'
            f'<div class="rank">{rows}</div>'
            '<a class="more" href="people.html">How each outlet presents them &rarr;</a></div>')


def person_headlines(records, limit=6):
    """A few headlines behind the counts: one per role first, then the newest."""
    picked, seen = [], set()
    ordered = sorted(records, key=lambda r: (r["field"] != "headline", -r["date"].timestamp()))

    def take(record):
        if record["url"] not in seen and len(picked) < limit:
            seen.add(record["url"])
            picked.append(record)

    for role, *_ in ROLE_ORDER:
        first = next((r for r in ordered if r["role"] == role and r["url"] not in seen), None)
        if first:
            take(first)
    for record in ordered:
        take(record)
    items = []
    for r in sorted(picked, key=lambda r: r["date"], reverse=True):
        where = " &middot; opening line" if r["field"] == "snippet" else ""
        items.append(
            f'<li><div><span class="role">{e(ROLE_WORDS[r["role"]])}</span>'
            f'<small>{e(day(r["date"]))}{where}</small></div>'
            f'{article_link(r["url"], e(r["headline"]))}</li>')
    return "".join(items)


def top_role(s):
    """The part an outlet most often gives them, with its share of mentions."""
    role, n = max(s["roles"].items(), key=lambda kv: kv[1])
    return role, n / (s["mentions"] or 1)


# What each group of reporting verbs conveys, in a reader's words
VERB_TONE = {"said": "neutral", "claimed": "distancing", "promised or assured": "promising",
             "praised": "praising", "criticised": "critical",
             "denied or defended": "defensive", "urged or warned": "urging"}


def words_used(s, limit=4):
    """The verbs an outlet reports their words with, grouped by what the verb
    conveys: "neutral: says, explains · critical: accuses". The verbs of what
    they do when the outlet never quotes them."""
    if not s["speaking_verbs"]:
        doing = ", ".join(e(headline_tense(v)) for v, _ in s["acting_verbs"].most_common(3))
        return f'<span class="vt">actions:</span> {doing}' if doing else ""
    from backend.analysis.portrayal import family_of
    groups = {}
    for verb, _ in s["speaking_verbs"].most_common(limit):
        tone = VERB_TONE.get(family_of(verb), "other")
        groups.setdefault(tone, []).append(headline_tense(verb))
    return " &middot; ".join(f'<span class="vt">{e(t)}:</span> {e(", ".join(v))}'
                             for t, v in groups.items())


def tone_cell(s):
    tone = s.get("tone")
    if not tone:
        return '<span class="few">too few headlines</span>'
    return (f'{e(tone["label"])}<small>{tone["n"]} headlines and opening lines</small>')


def anchor(outlet):
    return "o-" + re.sub(r"[^a-z0-9]+", "-", outlet.lower()).strip("-")


def usual_title(s):
    titles = [t for t, _ in s["titles"].most_common() if t != "(no title)"]
    return s["title_forms"].get(titles[0], titles[0]) if titles else ""


def glance_facts(named, absent):
    """Up to three plain sentences a reader can take in at once. Facts, not findings."""
    facts = []
    shares = [(s["articles"] / s["outlet_articles"], o, s) for o, s in named if s["outlet_articles"]]
    if shares:
        _, outlet, s = max(shares)
        facts.append(f"Named most often by <b>{e(outlet)}</b>: {s['articles']} of its "
                     f"{s['outlet_articles']:,} articles.")
    if absent:
        names = [o for o, _ in absent]
        shown = names if len(names) <= 4 else names[:3]
        listed = ", ".join(f"<b>{e(n)}</b>" for n in shown)
        more = f" and {len(names) - len(shown)} more" if len(names) > len(shown) else ""
        facts.append(f"Never named by {listed}{more}.")
    speaking = [(s["roles"].get("speaks", 0) / s["mentions"], o) for o, s in named
                if s["articles"] >= PEOPLE_CARD_MIN and s["mentions"]]
    if len(speaking) >= 2:
        high, low = max(speaking), min(speaking)
        if high[0] - low[0] >= 0.15:
            facts.append(f"Shown speaking most in <b>{e(high[1])}</b> ({high[0]:.0%} of "
                         f"mentions), least in <b>{e(low[1])}</b> ({low[0]:.0%}).")
    return facts


def glance_table(named, absent):
    """One row per outlet: how often, how they appear, the verbs, the title, the tone."""
    share = {o: s["articles"] / s["outlet_articles"] for o, s in named if s["outlet_articles"]}
    top = max(share.values(), default=0) or 1
    rows = []
    for outlet, s in named:
        cover = (f'<div class="meter"><i style="width:{share.get(outlet, 0) / top * 100:.0f}%">'
                 f'</i></div><small>{s["articles"]} &middot; {share.get(outlet, 0):.1%} of its '
                 f'articles</small>')
        name = outlet_label(outlet)
        if s["articles"] < PEOPLE_CARD_MIN:
            rest = '<td colspan="4" class="few">Too few articles to compare</td>'
        else:
            name = f'<a href="#{anchor(outlet)}">{name}</a>'
            role, part = top_role(s)
            rest = (f'<td>{e(ROLE_PHRASE[role])}<small>{part:.0%} of mentions</small></td>'
                    f'<td>{words_used(s) or "&mdash;"}</td>'
                    f'<td>{e(usual_title(s)) or "&mdash;"}</td>'
                    f'<td>{tone_cell(s)}</td>')
        rows.append(f'<tr><td class="o">{name}</td><td class="cov">{cover}</td>{rest}</tr>')
    for outlet, n in absent:
        rows.append(f'<tr class="none"><td class="o">{outlet_label(outlet)}</td>'
                    f'<td colspan="5">Never named in its {n:,} articles</td></tr>')
    return ('<div class="scroll"><table class="glance"><thead><tr><th>Outlet</th>'
            '<th>How often</th><th>How they appear</th><th>Verbs for what they said</th>'
            '<th>Called</th><th>Headline tone</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def outlet_card(outlet, s, name):
    """One outlet's headlines about the person, folded until the reader asks.

    The card used to repeat the table in a denser form - a colour-coded bar, two
    levels of verb counts, who did what to them, every title used - and readers
    found it the hardest part of the page. What the table cannot show is the
    headlines themselves, so the card is one sentence and those.
    """
    role, _ = top_role(s)
    return (f'<details class="pdet" id="{anchor(outlet)}"><summary><b>{e(outlet)}</b>'
            f'<span>{plural(s["articles"], "article")} &middot; '
            f'{e(ROLE_PHRASE[role].lower())}</span></summary>'
            f'<div class="pbody"><p class="psum">In {e(outlet)}\u2019s headlines, '
            f'{role_sentence(name, s)}</p>'
            f'<ul class="heads ph">{person_headlines(s["records"])}</ul>'
            '<p class="go">Open a headline to read the full article on '
            f'{e(outlet)}\u2019s site.</p></div></details>')


# A row's outlet name links to that outlet's folded headlines; open it on arrival
OPEN_TARGET = (
    "<script>(function(){function open(){var d=document.getElementById("
    "location.hash.slice(1));if(d&&d.tagName==='DETAILS'){d.open=true;}}"
    "window.addEventListener('hashchange',open);open();})();</script>")


def tone_targeted(outlets):
    """True when any outlet's headline tone was read toward the person (NewsMTSC)."""
    return any("targeted" in (s.get("tone_by") or ()) for s in outlets.values())


TONE_SENTENCE = ('<b>Headline tone</b> is an automatic reading of each headline or '
                 'opening line as a whole: “Ruto condemns the killings” reads '
                 'negative without being negative about Ruto.')
TONE_TARGETED = ('<b>Headline tone</b> is an automatic reading of the writer’s attitude '
                 'toward this person in each headline or opening line, not of the event: '
                 '“Ruto condemns the killings” is about how Ruto is shown, not '
                 'about the killings.')


def method_body(aliases, targeted=False):
    roles = "".join(f"<li><b>{e(words.capitalize())}</b>: {e(meaning)}</li>"
                    for _, words, meaning in ROLE_ORDER)
    matched = f"<p>Also matched as: {e(aliases)}.</p>" if aliases else ""
    tone = ('<p>Headline tone comes from NewsMTSC (Hamborg and Donnay, 2021), a model '
            'trained on news to judge the writer’s attitude toward one named person. '
            'Where it cannot score a mention, the sentence’s overall tone is used. It '
            'misreads Swahili and needs local context it does not have.</p>'
            if targeted else
            '<p>Headline tone comes from a sentiment model trained on social media posts, '
            'scoring each sentence from negative to positive. It reads the sentence, not '
            'the outlet’s view of the person, and it misreads sarcasm and Swahili.</p>')
    return (
        f'<ul class="plain">{roles}</ul>{matched}'
        '<p>Read from headlines and opening lines, which every outlet publishes in full '
        'even when the article itself is paywalled.</p>'
        '<p>KBC is the state broadcaster and Kenya News the government\u2019s own news '
        'agency: covering government activity is their remit.</p>'
        '<p>On a hand-checked sample of 40 headline mentions the role was right 34 '
        'times. A different person with the same name can be counted under the '
        'better-known one.</p>'
        + tone
        + '<p>Nothing here rates an outlet or a person. The conclusion is yours.</p>')


def person_page(person, people, generated):
    outlets, totals = person["outlets"], person["totals"]
    named = sorted(outlets.items(), key=lambda kv: -kv[1]["articles"])
    absent = sorted(((o, n) for o, n in totals.items() if o not in outlets),
                    key=lambda kv: -kv[1])
    facts = "".join(f"<li>{fact}</li>" for fact in glance_facts(named, absent))
    period = f'{day(people["first"])} to {day(people["last"])} {people["last"]:%Y}'
    detailed = "".join(outlet_card(o, s, person["name"]) for o, s in named
                       if s["articles"] >= PEOPLE_CARD_MIN)
    body = (
        f'<a class="back" href="people.html">{ICON["arrow"]}All people</a>'
        '<div class="sheet"><header>'
        f'<h1>{e(person["name"])}</h1>'
        f'<p class="lede">Named in {person["articles"]} articles by {len(named)} of '
        f'{len(FEEDS)} outlets &middot; {period}</p>'
        '</header>'
        + (f'<ul class="facts">{facts}</ul>' if facts else "")
        + '<h3 class="sub">Outlet by outlet</h3>'
        + glance_table(named, absent)
        + '<p class="hint">Counts reflect which stories each outlet covered, as well as how '
          'it wrote them. '
        + (TONE_TARGETED if tone_targeted(outlets) else TONE_SENTENCE)
        + ' It is a hint, not a verdict, and it can be wrong. These pages point to the '
          'reporting; they do not replace it.</p>'
        + '<h3 class="sub">Read the coverage yourself</h3>'
        + '<p class="hint">Open an outlet to see the headlines behind its row in the '
          'table.</p>'
        + detailed
        + OPEN_TARGET
        + '<details class="pdet method"><summary><b>How this works</b></summary>'
          f'<div class="pbody">{method_body(", ".join(person["aliases"]), tone_targeted(outlets))}'
          '</div></details>'
        + '</div>'
    )
    return shell(person["name"], "People", body, generated)


def people_index(people, generated):
    tiles = []
    for p in people["people"]:
        absent = sorted((o for o in p["totals"] if o not in p["outlets"]),
                        key=lambda o: -p["totals"][o])
        if absent:
            more = f" and {len(absent) - 2} more" if len(absent) > 2 else ""
            missing = f'<div class="srcline">Never named by {e(", ".join(absent[:2]))}{more}</div>'
        else:
            missing = '<div class="srcline">Named by every outlet</div>'
        tiles.append(
            f'<a class="tile" href="person-{e(p["id"])}.html"><h3>{e(p["name"])}</h3>'
            f'<div class="srcline">{p["articles"]} articles &middot; '
            f'{len(p["outlets"])} of {len(FEEDS)} outlets</div>{missing}</a>')
    body = (
        '<div class="colhead"><h2>People in the news</h2>'
        f'<span class="hint">{len(people["people"])} people &middot; '
        f'{day(people["first"])} to {day(people["last"])} {people["last"]:%Y}</span></div>'
        '<p class="hint">Pick a person to see how each outlet covers them, side by side.</p>'
        + f'<div class="grid">{"".join(tiles)}</div>')
    return shell("People - Newseye", "People", body, generated)


def build(export_path, out_dir):
    with open(export_path, encoding="utf-8") as fh:
        data = json.load(fh)
    generated = data.get("generated_at", "")
    # a page needs two outlets we could actually read: with one, there is nothing
    # to compare and the coverage grid has a single column
    clusters = [
        c for c in data["clusters"]
        if c.get("consensus")
        and len({a["source"] for a in c["articles"] if a["fetched"]}) >= 2
    ]
    clusters.sort(key=lambda c: (-len({a["source"] for a in c["articles"]}),
                                 -(c.get("coherence") or 0)))

    # overwrite in place rather than delete the directory: on Windows an open
    # browser tab holds a lock on it and rmtree fails with access denied
    os.makedirs(out_dir, exist_ok=True)
    for stale in os.listdir(out_dir):
        if stale.startswith(("story-", "person-")) and stale.endswith(".html"):
            try:
                os.remove(os.path.join(out_dir, stale))
            except OSError:
                pass

    stats = corpus_stats(clusters)
    people = people_data()
    # which listed people each article names, as the parse decided - so a story
    # set in Uhuru Park does not link to Uhuru Kenyatta
    named_in = defaultdict(set)
    names = {}
    for person in (people or {}).get("people", []):
        names[person["id"]] = person["name"]
        for summary in person["outlets"].values():
            for record in summary["records"]:
                named_in[record["url"]].add(person["id"])

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(dashboard(clusters, generated, stats, people, data.get("selection")))
    for cluster in clusters:
        here = {i for a in cluster["articles"] for i in named_in.get(a.get("url"), ())}
        path = os.path.join(out_dir, f"story-{cluster['cluster_id']}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(story_page(cluster, generated,
                                sorted(((i, names[i]) for i in here), key=lambda p: p[1])))
    with open(os.path.join(out_dir, "search.html"), "w", encoding="utf-8") as fh:
        fh.write(search_page(generated))
    if people:
        with open(os.path.join(out_dir, "people.html"), "w", encoding="utf-8") as fh:
            fh.write(people_index(people, generated))
        for person in people["people"]:
            path = os.path.join(out_dir, f"person-{person['id']}.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(person_page(person, people, generated))
        print(f"  people: {len(people['people'])} pages")

    # a script rather than JSON: browsers refuse fetch() on file:// pages, but
    # load a <script src> from beside the page without complaint
    index = search_index(clusters)
    if index:
        index_path = os.path.join(out_dir, "search-index.js")
        with open(index_path, "w", encoding="utf-8") as fh:
            fh.write("window.NEWSEYE_INDEX=" + json.dumps(index, separators=(",", ":"))
                     + ";\n")
        print(f"  search index: {index['count']:,} articles, "
              f"{os.path.getsize(index_path) / 1e6:.1f} MB")

    print(f"Wrote {len(clusters) + 2} pages to {out_dir}/")
    print(f"  open {os.path.join(out_dir, 'index.html')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", default="review_export.json")
    parser.add_argument("--out", default="site")
    args = parser.parse_args()
    build(args.export, args.out)
