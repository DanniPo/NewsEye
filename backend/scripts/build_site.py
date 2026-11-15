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
from datetime import datetime, timedelta

from backend.analysis.digest import digest_groups, summarise
from backend.config import RSS_FEEDS
from backend.ingestion.dedupe import is_web_url

CSS = """
:root{--bg:#F5F7F0;--panel:#FFFFFF;--rail:#FFFFFF;--ink:#1A2B20;--muted:#4F5D53;
--faint:#687469;--rule:#E2E8DC;--lime:#C9E265;--lime-ink:#3F5F0B;--lime-soft:#EEF5D6;
--dark:#1D2B22;--on-dark:#FFFFFF;--gap:#94580A;--gap-soft:#FBEFD8;--ok:#256B41;
--ok-soft:#E3F1E7;--blue:#2F6496;--blue-soft:#E6EEF7;--neg:#C2611F;--pos:#2F6EA5;
--neu:#C9CFC5;--shadow:0 1px 2px rgba(26,43,32,.05);
--sans:"Figtree",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0F1511;
--panel:#161E18;--rail:#121915;--ink:#E5ECE3;--muted:#A9B5AB;--faint:#8F9C92;
--rule:#27322A;--lime-ink:#CFE77A;--lime-soft:#253019;--dark:#C9E265;--on-dark:#142012;
--gap:#E8AE55;--gap-soft:#33270F;--ok:#73C795;--ok-soft:#142A1C;--blue:#8DB8E6;
--blue-soft:#162536;--neg:#E08A4E;--pos:#6FA6DA;--neu:#4A554C;--shadow:none}}
:root[data-theme=dark]{--bg:#0F1511;--panel:#161E18;--rail:#121915;--ink:#E5ECE3;
--muted:#A9B5AB;--faint:#8F9C92;--rule:#27322A;--lime-ink:#CFE77A;--lime-soft:#253019;
--dark:#C9E265;--on-dark:#142012;--gap:#E8AE55;--gap-soft:#33270F;--ok:#73C795;
--ok-soft:#142A1C;--blue:#8DB8E6;--blue-soft:#162536;--neg:#E08A4E;--pos:#6FA6DA;
--neu:#4A554C;--shadow:none}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;
line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
:focus-visible{outline:2px solid var(--lime-ink);outline-offset:2px;border-radius:6px}

/* ---- shell ---- */
.app{display:grid;grid-template-columns:236px minmax(0,1fr);min-height:100vh}
.rail{background:var(--rail);border-right:1px solid var(--rule);padding:22px 14px 18px;
display:flex;flex-direction:column;gap:28px;position:sticky;top:0;height:100vh}
.brand{display:flex;align-items:center;gap:11px;padding:0 6px}
.brand .glyph{width:40px;height:40px;border-radius:11px;background:var(--lime);
display:grid;place-items:center;flex:none}
.brand .glyph svg{width:21px;height:21px;display:block}
.brand b{display:block;font-size:19px;letter-spacing:-.02em;font-weight:700;line-height:1.1}
.brand small{display:block;font-size:9.5px;font-weight:700;letter-spacing:.04em;
text-transform:uppercase;color:var(--muted);margin-top:3px;white-space:nowrap}
.rlabel{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted);padding:0 10px;margin:0 0 8px}
.rail nav{display:flex;flex-direction:column;gap:4px}
.rail nav a{display:flex;align-items:center;gap:11px;padding:8px 10px;border-radius:11px;
font-size:14px;font-weight:500}
.rail nav .ico{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;
flex:none;background:var(--bg);border:1px solid var(--rule)}
.rail nav svg{width:14px;height:14px}
.rail nav a:hover{background:var(--bg)}
.rail nav a.on{background:var(--lime-soft);font-weight:700}
.rail nav a.on .ico{background:var(--lime);border-color:transparent;color:#1A2B20}
.snap{margin-top:auto;background:var(--bg);border:1px solid var(--rule);border-radius:13px;
padding:13px 14px;font-size:12px;color:var(--muted);line-height:1.5}
.snap b{display:flex;align-items:center;gap:7px;font-size:13px;color:var(--ink);margin-bottom:3px}
.snap b::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--lime-ink)}
.snap p{margin:0}

.main{min-width:0;display:flex;flex-direction:column}
.topbar{display:flex;gap:14px;align-items:center;padding:14px 32px;background:var(--bg);
border-bottom:1px solid var(--rule);position:sticky;top:0;z-index:6;min-height:64px}
.search{flex:1;max-width:420px;display:flex;align-items:center;gap:9px;background:var(--panel);
border:1px solid var(--rule);border-radius:11px;padding:8px 13px}
.search:focus-within{border-color:var(--lime-ink)}
.search svg{width:14px;height:14px;color:var(--muted);flex:none}
.search input{border:0;background:transparent;color:var(--ink);font:inherit;
font-size:13.5px;width:100%;outline:none}
.stamp{margin-left:auto;font-size:11px;font-weight:700;letter-spacing:.04em;
text-transform:uppercase;color:var(--lime-ink);background:var(--lime-soft);border-radius:20px;
padding:6px 13px;white-space:nowrap}
.content{padding:30px 32px 64px;max-width:1300px;width:100%}

/* ---- page heads ---- */
.intro{margin-bottom:6px}
.intro h1,.phead h1{font-size:clamp(25px,3.2vw,33px);font-weight:700;line-height:1.15;
letter-spacing:-.025em;margin:0 0 8px;text-wrap:balance}
.intro p{margin:0;max-width:74ch;color:var(--muted)}
ol.steps{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 0;padding:0;list-style:none;
counter-reset:step;font-size:13px;font-weight:500}
ol.steps li{counter-increment:step;display:flex;align-items:center;gap:8px;
background:var(--panel);border:1px solid var(--rule);border-radius:20px;padding:4px 12px 4px 5px}
ol.steps li::before{content:counter(step);width:20px;height:20px;border-radius:50%;
background:var(--lime);color:#1A2B20;font-size:11px;font-weight:700;display:grid;
place-items:center;flex:none}
.intro p.meta,p.meta{margin-top:12px;font-size:12.5px;color:var(--faint)}
.crumb{display:flex;gap:7px;align-items:center;font-size:11px;font-weight:700;
letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
.crumb a:hover{color:var(--lime-ink)}
.phead{display:flex;gap:16px;align-items:flex-start;justify-content:space-between;
flex-wrap:wrap}
.phead>div{min-width:0;flex:1 1 520px}
.phead p.pmeta{font-size:13px;color:var(--muted);margin:4px 0 0}
.kpill{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.05em;
text-transform:uppercase;color:var(--lime-ink);background:var(--lime-soft);border-radius:20px;
padding:5px 12px;margin-right:10px;vertical-align:1px}
.btn{display:inline-flex;align-items:center;gap:7px;border-radius:11px;padding:10px 16px;
font-size:13.5px;font-weight:600;white-space:nowrap}
.btn.line{background:var(--panel);border:1px solid var(--rule)}
.btn.line:hover{border-color:var(--lime-ink)}

/* ---- counts ---- */
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:24px 0 32px}
.stat{background:var(--panel);border:1px solid var(--rule);border-radius:15px;padding:16px 18px;
display:flex;flex-direction:column;min-width:0;box-shadow:var(--shadow)}
.stat .t{font-size:13px;color:var(--muted);font-weight:500}
.stat .n{font-size:28px;font-weight:700;letter-spacing:-.02em;line-height:1.15;
margin:8px 0 6px;font-variant-numeric:tabular-nums}
.stat .s{font-size:16px;font-weight:600;line-height:1.35;margin:8px 0 6px}
.stat .k{font-size:10.5px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
color:var(--muted)}
.stat small{font-size:12px;color:var(--muted);margin-top:auto}
.stat.hi{background:var(--lime-soft);border-color:transparent}
.stat.wide{grid-column:span 2}
.stats.three{grid-template-columns:repeat(3,minmax(0,1fr))}

/* ---- news categories ---- */
.catblock{margin:0 0 30px}
.cats{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.cats button{display:flex;flex-direction:column;align-items:flex-start;gap:1px;text-align:left;
border:1px solid var(--rule);background:var(--panel);color:var(--ink);font:inherit;
border-radius:13px;padding:11px 14px;cursor:pointer;box-shadow:var(--shadow)}
.cats button b{font-size:14px;font-weight:600}
.cats button small{font-size:12px;color:var(--muted)}
.cats button:hover{border-color:var(--lime-ink)}
.cats button.on{background:var(--lime-soft);border-color:var(--lime-ink)}

/* ---- two column body ---- */
.cols{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:24px;align-items:start}
.colhead{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
margin:0 0 3px;flex-wrap:wrap}
.colhead h2{font-size:22px;font-weight:700;margin:0;letter-spacing:-.015em}
.colhead .hint{font-size:12.5px;color:var(--muted)}
p.under{font-size:13px;color:var(--muted);margin:0 0 14px}
.sorts{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px}
.sorts button{border:1px solid transparent;background:transparent;color:var(--ink);font:inherit;
font-size:13px;font-weight:600;padding:6px 14px;border-radius:20px;cursor:pointer}
.sorts button:hover{border-color:var(--rule);background:var(--panel)}
.sorts button.on{background:var(--dark);color:var(--on-dark)}

/* ---- story cards ---- */
.grid{display:flex;flex-direction:column;gap:12px}
.tile{background:var(--panel);border:1px solid var(--rule);border-radius:15px;
padding:16px 20px 15px;display:flex;flex-direction:column;gap:7px;box-shadow:var(--shadow)}
.tile:hover{border-color:var(--lime-ink)}
.tile .top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.kick{font-size:10.5px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
color:var(--muted);padding-top:3px}
.tile h3{font-size:17px;font-weight:600;line-height:1.35;margin:0;letter-spacing:-.01em}
.tile .desc{font-size:13.5px;color:var(--muted);margin:0}
.tile .foot{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin-top:6px;
font-size:12.5px;color:var(--muted)}
.tile .foot b{color:var(--ink);font-weight:600}
.ochips{display:flex;gap:4px;flex-wrap:wrap}
.ochip{font-size:11px;font-weight:600;color:var(--ink);background:var(--bg);
border:1px solid var(--rule);border-radius:7px;padding:2px 7px}
.badges{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}
.badge{font-size:11.5px;font-weight:600;border-radius:20px;padding:4px 11px;white-space:nowrap;
display:inline-flex;align-items:center;gap:5px}
.badge.gap,.badge.loose{background:var(--gap-soft);color:var(--gap)}
.badge.fig{background:var(--lime-soft);color:var(--lime-ink)}
.badge.ok{background:var(--ok-soft);color:var(--ok)}
.badge.sim{background:var(--blue-soft);color:var(--blue)}
.why{display:flex;align-items:flex-start;gap:6px;margin:0;font-size:12.5px;color:var(--gap);
font-weight:600}
.why svg{width:12px;height:12px;flex:none;margin-top:3px}
.empty-grid{background:var(--panel);border:1px dashed var(--rule);border-radius:15px;
padding:26px;text-align:center;color:var(--muted);font-size:13.5px}
.chips{display:flex;flex-wrap:wrap;gap:5px}
.chip{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
background:var(--bg);border:1px solid var(--rule);color:var(--muted);border-radius:6px;
padding:3px 7px}
.srcline{display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--muted)}

/* ---- side panels ---- */
.panel{background:var(--panel);border:1px solid var(--rule);border-radius:15px;
padding:18px 20px;margin-bottom:16px;box-shadow:var(--shadow)}
.panel h4{font-size:17px;font-weight:600;margin:0 0 2px;letter-spacing:-.01em}
.panel p.sub{font-size:12.5px;color:var(--muted);margin:0 0 14px}
ul.latest{list-style:none;margin:0;padding:0}
ul.latest li{border-top:1px solid var(--rule);padding:11px 0}
ul.latest li:last-child{padding-bottom:0}
ul.latest a{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
ul.latest b{font-size:13.5px;font-weight:600;line-height:1.35}
ul.latest a:hover b{color:var(--lime-ink)}
ul.latest small{display:block;font-size:12px;color:var(--muted);margin-top:2px}
ul.latest time{font-size:12px;color:var(--muted);white-space:nowrap}
.rank{display:flex;flex-direction:column;gap:10px}
.rank .r{display:flex;gap:10px;align-items:flex-start}
.rank .r b{width:22px;height:22px;border-radius:7px;background:var(--lime-soft);
color:var(--lime-ink);font-size:11px;font-weight:700;display:grid;place-items:center;
flex:none}
.rank .r span{font-size:13.5px;font-weight:600;line-height:1.3;display:block}
.rank .r small{font-size:12px;color:var(--muted);display:block}
.rank .r a:hover span{color:var(--lime-ink)}
.panel .more{display:block;margin-top:12px;font-size:13px;font-weight:600;color:var(--lime-ink)}
.panel ul.plain{margin:0;padding-left:16px;font-size:12.5px;color:var(--muted)}
.panel ul.plain li{margin-bottom:5px}
details.howto{background:var(--panel);border:1px solid var(--rule);border-radius:15px;
margin-bottom:16px}
details.howto summary{cursor:pointer;padding:15px 20px;font-size:15px;font-weight:600}
details.howto .pbody{padding:0 20px 15px}
details.howto p{font-size:13px;color:var(--muted);margin:0 0 9px;line-height:1.55}

/* ---- story page ---- */
.tabbar{display:flex;gap:4px;overflow-x:auto;margin:20px 0 22px;padding:8px 0;
border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);position:sticky;top:64px;
z-index:5;background:var(--bg)}
.tabbar a{font-size:13.5px;font-weight:500;padding:7px 15px;border-radius:10px;
white-space:nowrap;color:var(--muted)}
.tabbar a:hover{background:var(--panel);color:var(--ink)}
.tabbar a.on{background:var(--lime-soft);color:var(--ink);font-weight:700}
.tabbar a small{font-size:11px;font-weight:600;color:var(--muted);background:var(--panel);
border:1px solid var(--rule);border-radius:10px;padding:0 6px;margin-left:6px}
.tabbar a.on small{border-color:transparent}
.tabs.tabbed .tabpanel:not(.on){display:none}
.tabs.tabbed .tabpanel{min-height:240px}
.heads-block{margin-top:22px;scroll-margin-top:136px}
.story{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:24px;align-items:start}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:15px;
padding:20px 22px;margin-bottom:18px;box-shadow:var(--shadow);scroll-margin-top:136px;
min-width:0}
.card>h2,h3.sub{font-size:19px;font-weight:600;letter-spacing:-.01em;margin:0 0 4px;
scroll-margin-top:136px}
p.hint{font-size:13.5px;color:var(--muted);margin:4px 0 14px;max-width:72ch}
.side{position:sticky;top:136px}
.minis{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0 4px}
.mini{border:1px solid var(--rule);border-radius:12px;padding:11px 13px}
.mini .t{font-size:12.5px;color:var(--muted)}
.mini .n{display:block;font-size:26px;font-weight:700;letter-spacing:-.02em;line-height:1.2;
margin:4px 0 2px}
.mini small{font-size:11.5px;color:var(--muted)}
.side h5{font-size:14px;font-weight:600;margin:18px 0 8px}
ul.outlets{list-style:none;margin:0;padding:0}
ul.outlets li{display:flex;align-items:center;gap:10px;padding:6px 0;font-size:13.5px}
ul.outlets .av{width:26px;height:26px;border-radius:7px;background:var(--bg);
border:1px solid var(--rule);display:grid;place-items:center;font-size:10.5px;font-weight:700;
flex:none}
ul.outlets li.no .av{background:var(--gap-soft);border-color:transparent;color:var(--gap)}
ul.outlets .go{margin-left:auto;font-size:12px;color:var(--muted);white-space:nowrap}
ul.outlets a.go:hover{color:var(--lime-ink)}
ul.outlets .tag{margin-left:auto;font-size:10.5px;font-weight:700;text-transform:uppercase;
letter-spacing:.04em;color:var(--gap);white-space:nowrap}
p.fine{font-size:12px;color:var(--muted);border-top:1px solid var(--rule);padding-top:12px;
margin:16px 0 0;line-height:1.5}
/* the story in a few sentences, before any table */
.atglance{background:var(--lime-soft);border-radius:12px;padding:14px 18px}
.atglance b.t{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;
color:var(--lime-ink);margin-bottom:4px}
.atglance ul{margin:0;padding-left:18px;font-size:14.5px;line-height:1.55}
.atglance li{margin:4px 0}
.atglance a{color:var(--lime-ink);font-weight:700;white-space:nowrap;text-decoration:underline;
text-underline-offset:2px}
.pills{display:flex;flex-wrap:wrap;gap:6px}
.pill{font-size:12.5px;border-radius:20px;padding:3px 10px;border:1px solid var(--rule);
background:var(--bg)}
.pill b{font-weight:700}
.trow{display:grid;grid-template-columns:170px minmax(0,1fr);gap:12px;align-items:center;
padding:11px 0 5px;border-top:1px solid var(--rule)}
.trow>div:first-child b{font-size:14px}
.trow small{display:block;font-size:11.5px;color:var(--muted)}
details.ex{margin:0 0 8px 182px;font-size:12.5px}
details.ex summary{cursor:pointer;color:var(--lime-ink);font-weight:700}
p.fgroup{font-size:13.5px;margin:12px 0 7px}
h4.fsub{font-size:13.5px;margin:12px 0 4px}
p.swipe{display:none;font-size:12.5px;font-weight:700;color:var(--lime-ink);margin:4px 0}
@media(max-width:820px){.trow{grid-template-columns:minmax(0,1fr);gap:6px}
details.ex{margin-left:0}p.swipe{display:block}}
.loose{border:1px solid var(--gap);background:var(--gap-soft);border-radius:12px;
padding:12px 14px;margin:0 0 14px;font-size:13.5px}
.loose b{color:var(--gap)}
.heads{margin:0;padding:0;list-style:none}
.heads li{display:grid;grid-template-columns:148px minmax(0,1fr);gap:13px;padding:10px 0;
border-bottom:1px solid var(--rule);align-items:baseline}
.heads li:first-child{border-top:1px solid var(--rule)}
.heads li:last-child{border-bottom:0}
.hsrc{font-size:12.5px;font-weight:700}
.hsrc .unread{display:block;font-size:10px;font-weight:700;text-transform:uppercase;
letter-spacing:.05em;color:var(--gap);margin-top:2px}
.heads a{font-size:15px;line-height:1.4;font-weight:500}
.heads a:hover{text-decoration:underline;text-decoration-color:var(--lime-ink)}
.scroll{overflow-x:auto;margin:6px 0}
table{border-collapse:collapse;width:100%;min-width:520px;font-size:13.5px}
th,td{padding:10px 8px;border-bottom:1px solid var(--rule)}
thead th{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
color:var(--muted);text-align:center;vertical-align:bottom}
thead th:first-child{text-align:left;width:48%}
td.f{font-size:14px;line-height:1.45}
td.f .st{display:block;font-size:11.5px;color:var(--muted);margin-top:5px}
td.m{text-align:center;font-size:15px;font-weight:700}
td.m.y{color:var(--ok)}td.m.n{color:var(--gap);background:var(--gap-soft)}
td.m.r{color:var(--blue);background:var(--blue-soft)}
details.rel{margin-top:6px;font-size:12.5px;color:var(--muted)}
details.rel summary{cursor:pointer;color:var(--blue);font-weight:700}
details.rel p{margin:5px 0 0;line-height:1.45}
.remark{border:1px solid var(--rule);border-radius:12px;padding:11px 14px 6px;margin-bottom:10px;
background:var(--bg)}
.rhead{display:flex;gap:10px;align-items:baseline;margin-bottom:6px}
.rhead b{font-size:14.5px}.rhead span{font-size:12px;color:var(--muted)}
.ver{display:grid;grid-template-columns:130px minmax(0,1fr);gap:12px;padding:8px 0;
border-top:1px solid var(--rule);align-items:start}
.vsrc{font-size:12.5px;font-weight:700}
.ver blockquote{margin:0;font-size:14px;line-height:1.5}
.ver mark{background:var(--lime-soft);color:var(--ink);border-radius:3px;padding:0 2px}
.vrel{display:inline-block;margin-top:5px;font-size:10.5px;font-weight:700;text-transform:uppercase;
letter-spacing:.04em;border-radius:5px;padding:2px 6px;border:1px solid var(--rule);color:var(--muted)}
.vrel.q-same{color:var(--ok);border-color:var(--ok)}
.vrel.q-more,.vrel.q-less{color:var(--lime-ink);border-color:var(--lime-ink)}
.vrel.q-diff{color:var(--blue);border-color:var(--blue)}
ul.qlist{margin:0;padding:0 0 4px;list-style:none}
ul.qlist li{padding:8px 0;border-top:1px solid var(--rule);font-size:13px}
ul.qlist li span{display:block;font-size:14px;margin-top:3px}
@media(max-width:820px){.ver{grid-template-columns:minmax(0,1fr);gap:4px}}
tfoot td{font-size:12px;color:var(--muted);border-bottom:none;padding-top:10px;
text-align:center;font-variant-numeric:tabular-nums}
tfoot td:first-child{text-align:left;font-weight:700;color:var(--ink)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted);padding:2px 0 6px}
.legend i{font-style:normal;font-weight:700}
.legend i.y{color:var(--ok)}.legend i.n{color:var(--gap)}.legend i.r{color:var(--blue)}
.quote{display:grid;grid-template-columns:132px minmax(0,1fr);gap:13px;padding:11px 0;
border-bottom:1px solid var(--rule);align-items:start}
.qsrc{display:block;font-size:12.5px;font-weight:700}
.qtone{display:block;font-size:11px;color:var(--muted)}
.quote blockquote{margin:0;font-size:14px;line-height:1.5;color:var(--ink)}
.qmark{display:block;font-size:11px;color:var(--faint);margin-top:4px}
.fig{border:1px solid var(--rule);border-radius:12px;padding:11px 13px;margin-bottom:9px;
background:var(--bg)}
.fhead{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;margin-bottom:5px}
.fnum{font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}
.fsrc{font-size:12.5px;font-weight:700;color:var(--muted)}
.ftag{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
background:var(--panel);border:1px solid var(--rule);color:var(--muted);border-radius:5px;
padding:2px 5px}
.fctx{font-size:13px;color:var(--muted);margin:0;line-height:1.55}
.fctx strong{color:var(--ink);font-weight:700;background:var(--lime-soft);border-radius:3px;
padding:0 3px}
.fctx a{color:var(--lime-ink);font-weight:700;white-space:nowrap}
.empty{font-size:13.5px;color:var(--muted);font-style:italic}
footer.end{margin-top:8px;padding-top:14px;border-top:1px solid var(--rule);
font-size:12.5px;color:var(--faint);line-height:1.55}

/* ---- search page ---- */
.bigsearch{display:flex;align-items:center;gap:9px;border:1px solid var(--rule);
background:var(--bg);border-radius:12px;padding:6px 6px 6px 13px;margin:0 0 8px}
.bigsearch:focus-within{border-color:var(--lime-ink)}
.bigsearch svg{width:16px;height:16px;color:var(--muted);flex:none}
.bigsearch input{flex:1;min-width:0;border:0;background:transparent;color:var(--ink);
font:inherit;font-size:16px;outline:none;padding:6px 0}
.bigsearch button{border:0;border-radius:9px;background:var(--dark);color:var(--on-dark);
font:inherit;font-size:14px;font-weight:600;padding:8px 18px;cursor:pointer}
.hit{padding:15px 0;border-top:1px solid var(--rule)}
.hit h3{font-size:17px;font-weight:600;line-height:1.35;margin:8px 0 6px}
.hit h3 a:hover{text-decoration:underline;text-decoration-color:var(--lime-ink)}
.hit .heads li{padding:7px 0}
.snip{font-size:13.5px;color:var(--muted);margin:0 0 6px}
.hitlink{display:inline-block;margin-top:8px;font-size:13px;font-weight:700;color:var(--lime-ink)}

/* ---- people ---- */
.tbar{display:flex;height:8px;border-radius:4px;overflow:hidden;background:var(--bg);
min-width:100px;max-width:200px}
.tbar i{display:block;height:100%}
.tbar i.ng{background:var(--neg)}.tbar i.nu{background:var(--neu)}.tbar i.ps{background:var(--pos)}
.tkey{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:10px 0 0}
.tkey span::before{content:"";display:inline-block;width:9px;height:9px;border-radius:3px;
margin-right:6px;vertical-align:-1px;background:var(--neu)}
.tkey .ng::before{background:var(--neg)}.tkey .ps::before{background:var(--pos)}
p.psum{font-size:14px;margin:2px 0 8px;max-width:72ch}
.role{display:block;font-size:12px;font-weight:600;color:var(--muted)}
.ph li{grid-template-columns:140px minmax(0,1fr)}
.ph small{display:block;font-size:11px;color:var(--faint);margin-top:3px}
.pchips{display:flex;flex-wrap:wrap;gap:7px;margin:6px 0 4px}
.pchip{font-size:13px;font-weight:600;border:1px solid var(--rule);background:var(--panel);
border-radius:20px;padding:4px 12px}
.pchip:hover{border-color:var(--lime-ink);background:var(--lime-soft)}
.card .people{margin-top:14px}
.card .people p.hint{margin-bottom:6px}
ul.facts{margin:6px 0 4px;padding-left:18px;font-size:14.5px;line-height:1.55}
ul.facts li{margin:4px 0}
table.glance{min-width:480px}table.ptable{min-width:620px}
table.glance thead th,table.ptable thead th{text-align:left}
table.glance thead th:first-child,table.ptable thead th:first-child{width:auto}
table.glance td,table.ptable td{vertical-align:middle}
table.glance td.o{font-weight:700;width:170px;line-height:1.25}
table.glance td.o small{display:block;font-weight:400;font-size:11px;color:var(--muted)}
table.glance td small,table.ptable td small{display:block;font-size:11.5px;color:var(--muted);
margin-top:3px}
table.glance tr.none td{color:var(--muted)}
table.glance td.o a{color:inherit;border-bottom:1px dashed var(--faint)}
table.glance td.o a:hover{color:var(--lime-ink);border-color:var(--lime-ink)}
table.ptable td.rk{color:var(--muted);font-size:12px;width:40px;font-variant-numeric:tabular-nums}
table.ptable td.num{font-variant-numeric:tabular-nums;font-weight:600}
table.ptable a.nm{font-weight:600}
table.ptable a.nm:hover,a.open:hover{color:var(--lime-ink)}
a.open{font-size:12.5px;font-weight:600;white-space:nowrap}
details.pdet{border:1px solid var(--rule);border-radius:12px;background:var(--bg);margin-bottom:9px}
details.pdet summary{cursor:pointer;padding:11px 14px;display:flex;gap:10px;align-items:baseline;
list-style:none}
details.pdet summary::-webkit-details-marker{display:none}
details.pdet summary span{font-size:12.5px;color:var(--muted)}
details.pdet summary::after{content:"+";margin-left:auto;font-weight:700;color:var(--lime-ink)}
details.pdet[open] summary::after{content:"–"}
details.pdet .pbody{padding:0 14px 12px}
details.method{background:var(--panel)}
details.method .pbody p,details.method .pbody li{font-size:12.5px;color:var(--muted)}
.vt{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--muted)}
.few{color:var(--faint);font-style:italic}
p.go{font-size:12.5px;color:var(--lime-ink);font-weight:700;margin:6px 0 2px}
@media(max-width:820px){.ph li{grid-template-columns:minmax(0,1fr)}}

@media(max-width:1180px){.cols,.story{grid-template-columns:minmax(0,1fr)}
.side{position:static}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:820px){
.app{grid-template-columns:1fr}
.rail{position:static;height:auto;flex-direction:row;align-items:center;gap:12px;
overflow-x:auto;padding:10px 16px;border-right:0;border-bottom:1px solid var(--rule)}
.brand{padding:0}.brand small,.rlabel,.snap{display:none}
.brand .glyph{width:32px;height:32px;border-radius:9px}
.rail nav{flex-direction:row;gap:4px}
.rail nav a{white-space:nowrap;padding:6px 8px}
.rail nav .ico{width:24px;height:24px}
.content{padding:20px 16px 56px}
.topbar{padding:10px 16px;position:static;min-height:0}.stamp{display:none}
.tabbar{top:0}
.card,.panel{padding:16px}
.quote{grid-template-columns:minmax(0,1fr);gap:5px}
.heads li{grid-template-columns:minmax(0,1fr);gap:3px}
.tile{padding:14px 16px}
.tile .top{flex-direction:column;gap:6px}
.cats{display:flex;overflow-x:auto;padding-bottom:4px}
.cats button{flex:none;min-width:128px}
.badges{justify-content:flex-start}
}
@media(max-width:560px){.stats{gap:10px;margin:18px 0 24px}.stat{padding:12px 14px}
.stat .n{font-size:23px;margin:6px 0 4px}.stat .s{font-size:14.5px}
.stats.three{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Figtree:wght@400;500;600;700&display=swap">')

# Inline so the pages work from the filesystem with no network and no build step.
ICON = {
 "eye": '<svg viewBox="0 0 24 24" fill="none" stroke="#1A2B20" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 12S5 5.5 12 5.5 22.5 12 22.5 12S19 18.5 12 18.5 1.5 12 1.5 12Z"/><circle cx="12" cy="12" r="2.6"/></svg>',
 "grid": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
 "doc": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2.5H7A1.5 1.5 0 0 0 5.5 4v16A1.5 1.5 0 0 0 7 21.5h10A1.5 1.5 0 0 0 18.5 20V7L14 2.5Z"/><path d="M13.5 2.5V7.5h5"/></svg>',
 "flame": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>',
 "info": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="M12 11v6M12 7.5v.01"/></svg>',
 "person": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7.5 8-7.5s8 3.1 8 7.5"/></svg>',
 "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m16.5 16.5 4 4"/></svg>',
 "arrow": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>',
 "out": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="width:11px;height:11px;vertical-align:-1px"><path d="M7 17 17 7M8 7h9v9"/></svg>',
}

# Five places, each a page a reader can name. Readers testing the site found the
# earlier eight links - several of them jumps to panels on the dashboard - more
# to take in than to use.
NAV = (("index.html", "grid", "Stories"),
       ("contested.html", "flame", "Contested"),
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
        # the row in words, counted over the outlets that could be read only
        status = f"Reported by {sum(1 for o in read if o in reported)} of {len(read)}"
        similar = sum(1 for o in read if o in related and o not in reported)
        fact += f'<span class="st">{status}' + (f" &middot; similar in {similar}"
                                                  if similar else "") + "</span>"
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
    return ('<h3 class="sub">How they were described</h3>'
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
        others = (f'<details class="pdet"{"" if shared else " open"}><summary><b>Other quotes'
                  f'</b><span>{len(single)} from '
                  f'{people} people, each in one outlet</span></summary>'
                  f'<ul class="qlist">{items}</ul></details>')
    hint = ('<p class="hint">The same remark as each outlet printed it. Highlighted words '
            'are ones the first outlet left out.</p>' if shared else "")
    return '<h3 class="sub">What was said</h3>' + hint + "".join(out) + others


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
        # folded beside the figures that can be compared; open when they are all
        # there is, or the Numbers tab would look empty
        opened = "" if out else " open"
        out.append(f'<details class="pdet"{opened}><summary><b>{lead}</b><span>'
                   f'{plural(len(ungrouped) + len(solo), "figure")} with nothing to set '
                   f'beside</span></summary><div class="pbody">{"".join(extra)}</div></details>')

    if not out:
        return ('<p class="empty">No outlet published a figure we could classify '
                'for this story.</p>')
    return "".join(out)


def rail(active, generated=""):
    items = []
    for href, icon, label in NAV:
        on = ' class="on"' if label == active else ""
        items.append(f'<a href="{href}"{on}><span class="ico">{ICON[icon]}</span>'
                     f'<span>{e(label)}</span></a>')
    # A snapshot, not a live feed: the pages are built from the database at one
    # moment, and say which. A "live" badge on a static page would be false.
    snap = (f'<div class="snap"><b>Snapshot</b><p>Built {e(generated)} from '
            f'{len(RSS_FEEDS)} outlets’ public feeds.</p></div>' if generated else "")
    return (
        '<aside class="rail">'
        f'<div class="brand"><span class="glyph">{ICON["eye"]}</span><div><b>Newseye</b>'
        '<small>Kenyan news compared</small></div></div>'
        f'<div><p class="rlabel">Browse</p><nav>{"".join(items)}</nav></div>'
        + snap + '</aside>')


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
        f'<div class="app">{rail(active, generated)}<div class="main">'
        f'<div class="topbar">{box}'
        f'<span class="stamp">Data as of {e(generated)}</span></div>'
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
  var cats=[].slice.call(document.querySelectorAll('.cats button'));
  var topic='';
  function filter(){
    var t=q.value.trim().toLowerCase(), n=0;
    tiles.forEach(function(el){
      var hit=(!t||(el.dataset.find||'').indexOf(t)>-1)&&(!topic||el.dataset.topic===topic);
      el.style.display=hit?'':'none'; if(hit)n++;
    });
    if(count) count.textContent=n+(n===1?' story':' stories');
    if(none) none.style.display=n?'none':'';
  }
  q.addEventListener('input',filter);
  cats.forEach(function(button){
    button.addEventListener('click',function(){
      topic=button.dataset.topic;
      cats.forEach(function(b){
        b.classList.toggle('on',b===button); b.setAttribute('aria-pressed',b===button);
      });
      filter();
    });
  });
})();
</script>"""

# The order buttons above a story list re-order its cards in place. Each card
# carries what it is sorted by, so this needs no data beyond the markup.
SORT_JS = """<script>
(function(){
  [].forEach.call(document.querySelectorAll('.sorts'), function(group){
    var list = group.parentNode.querySelector('.grid'); if(!list) return;
    var cards = [].slice.call(list.children);
    cards.forEach(function(card, i){ card.dataset.i = i; });
    group.addEventListener('click', function(event){
      var button = event.target.closest('button'); if(!button) return;
      var key = button.dataset.sort;
      [].forEach.call(group.querySelectorAll('button'), function(b){
        b.classList.toggle('on', b === button); b.setAttribute('aria-pressed', b === button);
      });
      cards.slice().sort(function(a, b){
        return key === 'i' ? a.dataset.i - b.dataset.i
          : (+b.dataset[key] || 0) - (+a.dataset[key] || 0) || a.dataset.i - b.dataset.i;
      }).forEach(function(card){ list.appendChild(card); });
    });
  });
})();
</script>"""

# A story page's tabs: one section at a time, switched in place. Without the
# script every section shows, one under another, and the tabs are links down the
# page. Each copy readies the tab boxes parsed so far; the listeners are added
# once, because the single-file bundle holds every page in one document.
TABS_JS = """<script>
(function(){
  function select(panel){
    var box = panel.closest('.tabs'); if (!box) return;
    box.classList.add('tabbed');
    [].forEach.call(box.querySelectorAll('.tabpanel'), function(p){
      p.classList.toggle('on', p === panel);
    });
    [].forEach.call(box.querySelectorAll('.tabbar a'), function(a){
      var on = a.getAttribute('href').slice(1) === panel.id;
      a.classList.toggle('on', on); a.setAttribute('aria-selected', on);
    });
  }
  function panelFor(id){
    var el = id && document.getElementById(id);
    return el && el.closest('.tabpanel');
  }
  [].forEach.call(document.querySelectorAll('.tabs:not(.tabbed)'), function(box){
    var first = box.querySelector('.tabpanel'); if (first) select(first);
  });
  if (window.newseyeTabs) return; window.newseyeTabs = true;
  function fromHash(){
    var panel = panelFor(decodeURIComponent(location.hash.slice(1)));
    if (panel) select(panel);
  }
  // a tab, or a link to a section ("See which"), switches without a jump; if the
  // reader had scrolled down, the new section starts just under the tab bar
  document.addEventListener('click', function(event){
    var link = event.target.closest && event.target.closest('a[href^="#"]');
    var panel = link && panelFor(link.getAttribute('href').slice(1));
    if (!panel) return;
    event.preventDefault();
    select(panel);
    try { history.replaceState(null, '', link.getAttribute('href')); } catch (err) {}
    var box = panel.closest('.tabs'), bar = box.closest('.main').querySelector('.topbar');
    var offset = bar && getComputedStyle(bar).position === 'sticky' ? bar.offsetHeight : 0;
    var top = box.getBoundingClientRect().top + window.scrollY - offset;
    if (window.scrollY > top) window.scrollTo(0, top);
    // a link to a part of a section ("Read the originals") goes on to that part
    var target = document.getElementById(link.getAttribute('href').slice(1));
    if (target !== panel) target.scrollIntoView({block: 'start'});
  });
  window.addEventListener('hashchange', fromHash);
  document.addEventListener('DOMContentLoaded', fromHash);
  fromHash();
})();
</script>"""


def gaps_in(cluster):
    """Facts that not every readable outlet reported word for word."""
    return sum(1 for g in cluster["consensus"] if g.get("omitted_by") or g.get("related"))


def story_tile(cluster, why=None):
    """Headline, who covered it, and in a few words what differs; why, when
    given, is a line saying why the tile is on the list it is on.

    The tile used to carry a bar of "0 carried by all / 4 not", which readers had
    to decode, and two outlet chips that looked like the only outlets. It now says
    the same things in words: the line under the headline lists the differences
    a reader can check on the story page, never a verdict on them.
    """
    from backend.analysis.divergence import differences

    sources = sorted({a["source"] for a in cluster["articles"]})
    _, unread = read_outlets(cluster)
    gaps = gaps_in(cluster)
    tiers = summarise(cluster.get("figure_digest") or [])
    coherence = cluster.get("coherence") or 0
    found = differences(cluster)
    latest = newest(cluster)

    badges = []
    if gaps:
        badges.append(f'<span class="badge gap">{plural(gaps, "fact")} not in every '
                      'outlet</span>')
    else:
        badges.append('<span class="badge ok">same facts in every outlet we read</span>')
    if coherence and coherence < 0.5:
        badges.append('<span class="badge loose">may mix two stories</span>')

    if why:
        line = f'<p class="why">{ICON["flame"]}<span>{e(why)}</span></p>'
    elif found["reasons"]:
        reasons = " · ".join(found["reasons"])
        line = f'<p class="desc">{e(reasons[:1].upper() + reasons[1:])}.</p>'
    elif gaps:
        line = '<p class="desc">Some facts appear in only some of the outlets we could read.</p>'
    else:
        line = '<p class="desc">Every outlet we could read reported the same facts.</p>'

    chips = "".join(f'<span class="ochip">{e(s)}</span>' for s in sources[:3])
    if len(sources) > 3:
        chips += f'<span class="ochip">+{len(sources) - 3}</span>'
    meta = [f'<b>{plural(len(sources), "outlet")}</b>',
            plural(len(cluster["articles"]), "article")]
    if tiers["shared"]:
        meta.append(f'{plural(tiers["shared"], "number")} to compare')
    if unread:
        meta.append(f'{len(unread)} could not be read')
    if latest:
        meta.append(f"latest {day(latest)}")
    find = " ".join([cluster.get("title_summary") or "", cluster.get("subject") or "",
                     cluster.get("topic_label") or ""] + sources).lower()
    return (
        f'<a class="tile" href="story-{cluster["cluster_id"]}.html" data-find="{e(find)}" '
        f'data-topic="{e(cluster.get("topic_label") or "General")}" '
        f'data-diff="{found["score"] + gaps / 100:.2f}" '
        f'data-latest="{int(latest.timestamp()) if latest else 0}">'
        f'<div class="top"><span class="kick">{e(cluster.get("topic_label") or "General")}</span>'
        f'<span class="badges">{"".join(badges)}</span></div>'
        f'<h3>{e(trim(cluster.get("title_summary") or "Untitled story", 110))}</h3>'
        + line
        + f'<div class="foot"><span class="ochips">{chips}</span>'
        + "".join(f"<span>{m}</span>" for m in meta) + '</div></a>')


def dashboard(clusters, generated, stats, people=None, selection=None):
    """What Newseye is for, then the stories.

    Readers shown an earlier version asked what they were looking at and what
    they were meant to do: four counter cards and six side panels came before any
    answer. So the page opens with what it is and what to do in three steps, and
    every count after that is one a story page can show. Nothing here is live;
    the counts are of this snapshot.
    """
    tiles = "".join(story_tile(c) for c in clusters)
    unread = sorted({a["source"] for c in clusters for a in c["articles"]
                     if not a["fetched"]})
    # a demonstration set is chosen for what it shows, and says so: contested
    # stories are not a typical day's mix
    chosen = {"showcase": ' These stories were picked to show every kind of comparison, so '
                          'they are more contested than a typical day.',
              "contested": ' These are the most contested stories of the past week, not a '
                           "typical day's mix."}.get(selection, "")
    body = (
        '<section class="intro"><h1>See how Kenyan outlets cover the same story</h1>'
        f'<p>Newseye reads {stats["outlets"]} Kenyan news sites, groups the articles about '
        'each event, and shows what each outlet reported, who it quoted and which numbers '
        'it gave. It does not say who is right: you compare.</p>'
        '<ol class="steps"><li>Pick a story</li><li>See what each outlet reported, side by '
        'side</li><li>Open the original articles</li></ol>'
        f'<p class="meta">A demonstration on real data: nothing here is made up.{chosen}</p>'
        '</section>'
        + dashboard_counts(clusters, stats)
        + categories_section(clusters)
        + '<div class="cols"><div>'
        '<div class="colhead" id="stories"><h2>Stories to compare</h2>'
        f'<span class="hint"><span id="shown">{plural(len(clusters), "story", "stories")}'
        '</span></span></div>'
        '<p class="under">Open a story to see what each outlet reported, side by side.</p>'
        '<div class="sorts" role="group" aria-label="Order the stories">'
        '<button type="button" class="on" aria-pressed="true" data-sort="i">Most outlets'
        '</button><button type="button" aria-pressed="false" data-sort="diff">Most '
        'differences</button><button type="button" aria-pressed="false" '
        'data-sort="latest">Latest</button></div>'
        f'<div class="grid">{tiles}</div>'
        '<div class="empty-grid" id="nores" style="display:none">No story on this page '
        'matches that. Press Enter to search every article.</div>'
        '</div><div>'
        + latest_panel(clusters)
        + people_panel(people)
        + about_panel(unread)
        + '</div></div>'
        + OPEN_TARGET + SORT_JS
    )
    return shell("Newseye - Kenyan media coverage", "Stories", body, generated,
                 search="filter")


def dashboard_counts(clusters, stats):
    """Three counts, each one a story page can show."""
    if not clusters:
        return ""
    differing = sum(1 for c in clusters if gaps_in(c))
    # "General" is the label for a story no topic fitted, so it never "leads"
    topics = Counter(c.get("topic_label") or "General" for c in clusters)
    named = [(t, n) for t, n in topics.most_common() if t != "General"]
    if named:
        top = [t for t, n in named if n == named[0][1]]
        lead = (f"{e(top[0])} leads: {plural(named[0][1], 'story', 'stories')} of the "
                f"{len(clusters)} here." if len(top) == 1 else
                f"{e(listing(top))} lead: {named[0][1]} stories each, of the {len(clusters)} here.")
    else:
        lead = f"No one topic: {len(clusters)} stories with no clear topic."
    collected = (f"{stats['articles']:,} articles collected &middot; {stats['usable']:,} "
                 "stories in the database" if stats["articles"] else "")
    return (
        '<div class="stats">'
        f'<div class="stat"><span class="t">Outlets read</span><span class="n">{stats["outlets"]}'
        '</span><small>Kenyan news sites, through their public feeds</small></div>'
        f'<div class="stat hi"><span class="t">Stories with differences</span>'
        f'<span class="n">{differing}</span><small>of the {len(clusters)} here: facts not in '
        'every outlet</small></div>'
        '<div class="stat wide"><span class="k">In this snapshot</span>'
        f'<span class="s">{lead}</span><small>{collected}</small></div></div>')


def categories_section(clusters):
    """Browse by news category: a button per topic on the page, most stories first.

    General is the label for a story no topic fitted, so it comes last whatever its
    count. The filtering is done in the reader's browser, together with the search
    box (SEARCH_JS), so it needs no server and no network.
    """
    counts = Counter(c.get("topic_label") or "General" for c in clusters)
    if len(counts) < 2:
        return ""
    topics = sorted(counts, key=lambda t: (t == "General", -counts[t], t))
    button = ('<button type="button" class="{on}" aria-pressed="{pressed}" data-topic="{topic}">'
              '<b>{name}</b><small>{count}</small></button>')
    cards = [button.format(on="on", pressed="true", topic="", name="All stories",
                           count=plural(len(clusters), "story", "stories"))]
    cards += [button.format(on="", pressed="false", topic=e(t), name=e(t),
                            count=plural(counts[t], "story", "stories")) for t in topics]
    return ('<section class="catblock"><div class="colhead"><h2>Browse by category</h2></div>'
            '<p class="under">Pick a category to show only its stories.</p>'
            f'<div class="cats" role="group" aria-label="News categories">{"".join(cards)}'
            '</div></section>')


def latest_panel(clusters, limit=4):
    """The stories with the newest articles in this snapshot."""
    dated = sorted(((newest(c), c) for c in clusters if newest(c)),
                   key=lambda t: -t[0].timestamp())[:limit]
    if not dated:
        return ""
    rows = "".join(
        f'<li><a href="story-{c["cluster_id"]}.html"><span><b>'
        f'{e(trim(c.get("title_summary") or "Untitled story", 72))}</b><small>'
        f'{plural(len(c["articles"]), "article")} &middot; '
        f'{plural(len({a["source"] for a in c["articles"]}), "outlet")}</small></span>'
        f'<time>{e(day(when))}</time></a></li>'
        for when, c in dated)
    return ('<div class="panel"><h4>Latest stories</h4><p class="sub">By their newest article '
            f'in this snapshot</p><ul class="latest">{rows}</ul></div>')


def newest(cluster):
    """When the story's latest article was published; None for an export made
    before articles carried their dates."""
    dates = [datetime.fromisoformat(str(a["published"])) for a in cluster["articles"]
             if a.get("published")]
    return max(dates) if dates else None


def contested_page(clusters, generated, days=7):
    """The latest stories whose coverage reports a dispute, most contested first.

    What counts is what the headlines and quotes report - accusations, denials,
    rows, probes, arrests (backend/analysis/contention.py) - and each card says
    what was counted. It is not a finding that the outlets disagree, and the page
    says that too. The days count back from the newest article in the build.
    """
    from backend.analysis.contention import LISTED, contention

    dated = {c["cluster_id"]: newest(c) for c in clusters}
    end = max((d for d in dated.values() if d), default=None)
    rows = []
    for cluster in clusters:
        when = dated[cluster["cluster_id"]]
        if end and (when is None or when < end - timedelta(days=days)):
            continue
        score, reasons = contention([a["title"] for a in cluster["articles"]],
                                    cluster.get("topic_label"), cluster.get("quotes"))
        if score >= LISTED:
            rows.append((score, when, cluster, reasons))
    rows.sort(key=lambda t: (-t[0], -(t[1].timestamp() if t[1] else 0)))
    window = (f"the {days} days to {end:%d %B %Y}" if end
              else "this build (its export has no dates, so every story is included)")
    tiles = "".join(story_tile(c, " · ".join(reasons)) for _, _, c, reasons in rows)
    body = (
        '<section class="intro"><h1>Contested stories</h1>'
        '<p>The latest stories whose coverage reports a dispute: headlines about '
        'accusations, denials, rows, probes, arrests or protests, and quotes reported as '
        'criticism or denial. Each card says what was counted. This is about what the '
        'stories report, not about which outlet is right: open one to compare how each '
        'outlet covered it.</p>'
        f'<p class="meta">{plural(len(rows), "story", "stories")} from {e(window)}, most '
        'contested first.</p></section>'
        + (f'<div class="grid">{tiles}</div>' if rows else
           '<div class="empty-grid">No story in this window has headlines or quotes that '
           'report a dispute.</div>'))
    return shell("Contested stories - Newseye", "Contested", body, generated)


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
    """The comparison for one story: a tab bar over its sections, and beside them
    who covered it, which outlets could not be read, and what differs."""
    coherence = cluster.get("coherence") or 0
    sources = len({a["source"] for a in cluster["articles"]})
    loose = ""
    if coherence and coherence < 0.5:
        loose = (f'<div class="loose"><b>We are not confident these are one story.</b> '
                 f'These articles score {coherence:.2f} on our similarity check, below the '
                 f'0.50 floor. Asking who left a fact out only means something when every '
                 f'outlet is covering the same event, so read the comparison below with '
                 f'that in mind.</div>')
    dates = sorted(datetime.fromisoformat(str(a["published"])) for a in cluster["articles"]
                   if a.get("published"))
    when = (f' &middot; first reported {day(dates[0])} &middot; latest {day(dates[-1])}'
            if dates else "")
    quotes, tone = quotes_block(cluster), framing_block(cluster)
    # (id, tab label, count shown on the tab, section)
    # the headlines are part of the overview: they are what a reader checks first
    headlines = ('<div class="heads-block" id="sources"><h3 class="sub">Headlines</h3>'
                 '<p class="hint">Each outlet’s own headline, linking to its article.</p>'
                 + headline_list(cluster) + '</div>')
    sections = [
        ("overview", "Overview", None,
         loose + story_glance(cluster) + headlines + people_chips(people_here)),
        ("facts", "Facts", len(cluster["consensus"] or []),
         '<h2>What each outlet reported</h2><p class="hint">Each row is a fact from one of '
         'the articles. Read across to see which outlets reported it.</p>'
         + coverage_table(cluster)),
    ]
    if quotes:
        sections.append(("quotes", "Quotes", len(cluster.get("quotes") or []), quotes))
    if tone:
        sections.append(("tone", "Tone", None, tone))
    sections.append(("numbers", "Numbers", len(cluster.get("figure_digest") or []),
                     '<h2>The numbers</h2><p class="hint">Each number with the sentence it '
                     'came from. Read the sentence: two numbers can count different '
                     'things.</p>' + figures_block(cluster)))
    tabbar = "".join(
        f'<a href="#{ident}" role="tab" aria-selected="{"true" if i == 0 else "false"}"'
        f'{" class=on" if i == 0 else ""}>{label}'
        + (f"<small>{count}</small>" if count else "") + "</a>"
        for i, (ident, label, count, _) in enumerate(sections))
    panels = "".join(f'<section class="card tabpanel" id="{ident}" role="tabpanel">{html}'
                     '</section>' for ident, _, _, html in sections)
    body = (
        f'<div class="crumb"><a href="index.html">Stories</a><span>/</span>'
        f'<span>Story {cluster["cluster_id"]}</span></div>'
        '<div class="phead"><div>'
        f'<h1>{e(trim(cluster.get("title_summary") or "Untitled story", 110))}</h1>'
        f'<p class="pmeta">How {sources} Kenyan outlets covered this story &middot; '
        f'{plural(len(cluster["articles"]), "article")}{when}</p></div>'
        '<a class="btn line" href="#sources">Read the originals</a></div>'
        '<div class="tabs">'
        f'<nav class="tabbar" role="tablist" aria-label="Sections of this story">{tabbar}</nav>'
        f'<div class="story"><div>{panels}'
        '<footer class="end">Newseye compares what each outlet included. It does not rate '
        'outlets or tell you who to trust.</footer></div>'
        f'{story_side(cluster)}</div></div>'
        + TABS_JS
    )
    return shell(cluster.get("title_summary") or "Story", "Stories", body, generated)


def initials(outlet):
    """'Nation Africa' -> 'NA', 'The Kenya Times' -> 'KT', 'KBC' -> 'KB'."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", outlet) if w.lower() != "the"]
    letters = "".join(w[0] for w in words[:2]) if len(words) > 1 else (words or ["?"])[0][:2]
    return letters.upper()


def story_side(cluster):
    """Who covered the story, and what differs: counts the sections show, the
    outlets that could not be read named as such, never as leaving facts out."""
    from backend.analysis.divergence import differences

    read, unread = read_outlets(cluster)
    gaps = gaps_in(cluster)
    found = differences(cluster)
    signals = []
    if gaps:
        signals.append(f'<span class="badge gap">{plural(gaps, "fact")} not in every '
                       'outlet</span>')
    signals += [f'<span class="badge sim">{e(r)}</span>' for r in found["reasons"]]
    if not signals:
        signals.append('<span class="badge ok">same facts in every outlet we read</span>')
    # each outlet's link goes to an article that could be read, where it has one
    first = {}
    for article in cluster["articles"]:
        have = first.get(article["source"])
        if have is None or (article["fetched"] and not have["fetched"]):
            first[article["source"]] = article
    rows = []
    for outlet in sorted(set(read) | set(unread)):
        link = web_link(first[outlet].get("url"))
        if outlet in unread:
            end = '<span class="tag">could not open</span>'
        elif link:
            end = (f'<a class="go" href="{link}" target="_blank" rel="noopener noreferrer">'
                   f'Read {ICON["out"]}</a>')
        else:
            end = ""
        rows.append(f'<li{" class=no" if outlet in unread else ""}><span class="av">'
                    f'{e(initials(outlet))}</span><span>{e(outlet)}</span>{end}</li>')
    could = (f"{len(read)} read &middot; {len(unread)} could not open" if unread
             else "all could be read")
    return (
        '<aside class="side"><div class="panel"><h4>Coverage at a glance</h4>'
        '<p class="sub">The outlets that covered this story</p>'
        '<div class="minis">'
        f'<div class="mini"><span class="t">Outlets</span><span class="n">{len(read) + len(unread)}'
        f'</span><small>{could}</small></div>'
        f'<div class="mini"><span class="t">Articles</span><span class="n">'
        f'{len(cluster["articles"])}</span><small>in this story</small></div></div>'
        f'<h5>What differs</h5><div class="badges" style="justify-content:flex-start">'
        f'{"".join(signals)}</div>'
        f'<h5>Outlets</h5><ul class="outlets">{"".join(rows)}</ul>'
        '<p class="fine">Differences show what each outlet included and how it worded it. '
        'They do not say which account is correct.</p></div></aside>')


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
        '<section class="intro"><h1>Search every article</h1>'
        '<p>Everything Newseye has collected, not only the stories on the dashboard. '
        'Articles that several outlets wrote about the same event are shown together as '
        'one story.</p></section>'
        '<div class="card" style="margin-top:22px">'
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


def people_panel(people):
    if not people or not people["people"]:
        return ""
    rows = "".join(
        f'<div class="r"><b>{i}</b><div><a href="person-{e(p["id"])}.html">'
        f'<span>{e(p["name"])}</span></a>'
        f'<small>{p["articles"]} articles &middot; {len(p["outlets"])} outlets</small></div></div>'
        for i, p in enumerate(people["people"][:6], start=1))
    return ('<div class="panel"><h4>People in the news</h4><p class="sub">Named most often '
            f'across the outlets</p><div class="rank">{rows}</div>'
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


def tone_bar(tone):
    """A tone mix as one bar: negative, neutral, positive, in that order, with the
    label and the count in words beside it, so the colours are never the only key."""
    if not tone:
        return '<span class="few">too few headlines</span>'
    negative, positive = tone["negative"], tone["positive"]
    neutral = max(0.0, 1 - negative - positive)
    words = f"{negative:.0%} negative, {neutral:.0%} neutral, {positive:.0%} positive"
    label = f'{e(tone["label"])} &middot; ' if tone.get("label") else ""
    return (f'<div class="tbar" role="img" aria-label="{words}" title="{words}">'
            f'<i class="ng" style="width:{negative * 100:.1f}%"></i>'
            f'<i class="nu" style="width:{neutral * 100:.1f}%"></i>'
            f'<i class="ps" style="width:{positive * 100:.1f}%"></i></div>'
            f'<small>{label}{tone["n"]} headlines &amp; openings</small>')


TONE_KEY = ('<p class="tkey"><span class="ng">negative</span><span>neutral</span>'
            '<span class="ps">positive</span></p>')


def tone_cell(s):
    return tone_bar(s.get("tone"))


def overall_tone(person):
    """Every outlet's tone mix for a person, weighted by its headline count."""
    tones = [s["tone"] for s in person["outlets"].values() if s.get("tone")]
    n = sum(t["n"] for t in tones)
    if not n:
        return None
    return {"n": n, "negative": sum(t["negative"] * t["n"] for t in tones) / n,
            "positive": sum(t["positive"] * t["n"] for t in tones) / n}


def overall_title(person):
    """The title most outlets' headlines give them: 'President', 'DCP leader'."""
    titles = Counter()
    forms = {}
    for s in person["outlets"].values():
        for title, n in s["titles"].items():
            if title != "(no title)":
                titles[title] += n
                forms.setdefault(title, s["title_forms"].get(title, title))
    return forms[titles.most_common(1)[0][0]] if titles else ""


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
    """One row per outlet: what it calls them and the tone of its headlines.

    The table also had columns for how often each outlet names them, the part it
    most often gives them and the verbs for their words. They made the widest
    table on the site, and the part and the verbs read better beside the
    headlines they come from, so they are in each outlet's card below.
    """
    rows = []
    for outlet, s in named:
        name = outlet_label(outlet)
        count = f'<small>{plural(s["articles"], "article")}</small>'
        if s["articles"] < PEOPLE_CARD_MIN:
            rest = '<td colspan="2" class="few">Too few articles to compare</td>'
        else:
            name = f'<a href="#{anchor(outlet)}">{name}</a>'
            rest = (f'<td>{e(usual_title(s)) or "&mdash;"}</td>'
                    f'<td>{tone_cell(s)}</td>')
        rows.append(f'<tr><td class="o">{name}{count}</td>{rest}</tr>')
    for outlet, n in absent:
        rows.append(f'<tr class="none"><td class="o">{outlet_label(outlet)}</td>'
                    f'<td colspan="2">Never named in its {n:,} articles</td></tr>')
    return ('<div class="scroll"><table class="glance"><thead><tr><th>Outlet</th>'
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
    verbs = words_used(s)
    return (f'<details class="pdet" id="{anchor(outlet)}"><summary><b>{e(outlet)}</b>'
            f'<span>{plural(s["articles"], "article")} &middot; '
            f'{e(ROLE_PHRASE[role].lower())}</span></summary>'
            f'<div class="pbody"><p class="psum">In {e(outlet)}\u2019s headlines, '
            f'{role_sentence(name, s)}</p>'
            # words_used names the verbs of what they do when the outlet never quotes them
            + (f'<p class="psum">{"Words for what they said: " if s["speaking_verbs"] else ""}'
               f'{verbs}</p>' if verbs else "")
            + f'<ul class="heads ph">{person_headlines(s["records"])}</ul>'
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
        '<p>On a check of 40 mentions from articles collected later, the role was right '
        '37 times. A different person with the same name can be counted under the '
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
    title = overall_title(person)
    never = (f"never named by {plural(len(absent), 'outlet')}" if absent
             else "named by every outlet")
    # tone stays in the table below, beside the counts it rests on: it is the
    # least certain reading on the page, so it is not one of the headline numbers
    counts = (
        '<div class="stats three">'
        f'<div class="stat"><span class="t">Articles naming them</span><span class="n">'
        f'{person["articles"]:,}</span><small>headlines and opening lines</small></div>'
        f'<div class="stat hi"><span class="t">Outlets</span><span class="n">{len(named)} of '
        f'{len(FEEDS)}</span><small>{e(never)}</small></div>'
        f'<div class="stat"><span class="t">Period</span><span class="s">{e(period)}</span>'
        '<small>every stored headline naming them</small></div></div>')
    body = (
        f'<div class="crumb"><a href="people.html">People</a><span>/</span>'
        f'<span>{e(person["name"])}</span></div>'
        '<div class="phead"><div>'
        f'<h1>{e(person["name"])}</h1>'
        f'<p class="pmeta">{f"<span class=kpill>{e(title)}</span>" if title else ""}'
        f'Named in {person["articles"]} articles by {len(named)} of {len(FEEDS)} outlets'
        f' &middot; {period}</p></div></div>'
        + counts
        + (f'<section class="card"><h2>At a glance</h2><ul class="facts">{facts}</ul></section>'
           if facts else "")
        + '<section class="card"><h2>Outlet by outlet</h2>'
        + '<p class="hint">Counts reflect which stories each outlet covered, as well as how '
          'it wrote them. '
        + (TONE_TARGETED if tone_targeted(outlets) else TONE_SENTENCE)
        + ' It is a hint, not a verdict, and it can be wrong. These pages point to the '
          'reporting; they do not replace it.</p>'
        + glance_table(named, absent) + TONE_KEY + '</section>'
        + '<section class="card"><h2>Read the coverage yourself</h2>'
        + '<p class="hint">Open an outlet to see how its headlines present them: the part '
          'they most often play, the words used for what they said, and the headlines '
          'themselves.</p>'
        + detailed
        + '</section>'
        + OPEN_TARGET
        + '<details class="pdet method"><summary><b>How this works</b></summary>'
          f'<div class="pbody">{method_body(", ".join(person["aliases"]), tone_targeted(outlets))}'
          '</div></details>'
    )
    return shell(person["name"], "People", body, generated)


def people_index(people, generated):
    """Everyone named often enough to compare, most named first, as one table."""
    rows = []
    for i, p in enumerate(people["people"], start=1):
        absent = sorted((o for o in p["totals"] if o not in p["outlets"]),
                        key=lambda o: -p["totals"][o])
        never = (f"never named by {e(listing(absent[:2]))}"
                 + (f" and {len(absent) - 2} more" if len(absent) > 2 else "")
                 if absent else "named by every outlet")
        title = overall_title(p)
        page = f'person-{e(p["id"])}.html'
        rows.append(
            f'<tr><td class="rk">{i:02d}</td>'
            f'<td><a class="nm" href="{page}">{e(p["name"])}</a>'
            + (f'<small>{e(title)}</small>' if title else "") + '</td>'
            + f'<td class="num">{p["articles"]:,}</td>'
            f'<td class="num">{len(p["outlets"])} of {len(FEEDS)}<small>{never}</small></td>'
            f'<td>{tone_bar(overall_tone(p))}</td>'
            f'<td><a class="open" href="{page}">View &rarr;</a></td></tr>')
    period = f'{day(people["first"])} to {day(people["last"])} {people["last"]:%Y}'
    top = people["people"][0] if people["people"] else None
    counts = (
        '<div class="stats">'
        f'<div class="stat"><span class="t">People with a page</span><span class="n">'
        f'{len(people["people"])}</span><small>named in {PEOPLE_MIN_ARTICLES}+ articles by '
        f'{PEOPLE_MIN_OUTLETS}+ outlets</small></div>'
        + (f'<div class="stat hi"><span class="t">Named most</span><span class="s">'
           f'{e(top["name"])}</span><small>{top["articles"]:,} articles</small></div>'
           if top else "")
        + f'<div class="stat"><span class="t">Outlets</span><span class="n">{len(FEEDS)}</span>'
        '<small>headlines and opening lines read</small></div>'
        f'<div class="stat"><span class="t">Period</span><span class="s">{e(period)}</span>'
        '<small>every stored headline</small></div></div>')
    body = (
        '<section class="intro"><h1>People in the news</h1>'
        '<p>How each outlet presents the people it names most: how often, in what role, '
        'with which words. Pick a person to see the outlets side by side.</p></section>'
        + counts
        + '<section class="card"><h2>Most named people</h2>'
        '<p class="hint">Ranked by the articles naming them. Headline tone is an automatic '
        'reading and can be wrong: open a person to see the headlines behind it.</p>'
        '<div class="scroll"><table class="ptable"><thead><tr><th>#</th><th>Person</th>'
        '<th>Articles</th><th>Outlets</th><th>Headline tone</th>'
        f'<th></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        + TONE_KEY + '</section>')
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
    with open(os.path.join(out_dir, "contested.html"), "w", encoding="utf-8") as fh:
        fh.write(contested_page(clusters, generated, data.get("contested_days") or 7))
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

    print(f"Wrote {len(clusters) + 3} pages to {out_dir}/")
    print(f"  open {os.path.join(out_dir, 'index.html')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", default="review_export.json")
    parser.add_argument("--out", default="site")
    args = parser.parse_args()
    build(args.export, args.out)
