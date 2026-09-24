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
import html
import json
import os
import re
from collections import Counter

from backend.analysis.digest import digest_groups, summarise

CSS = """
:root{--bg:#F4F6F8;--panel:#FFFFFF;--rail:#0E1B2A;--rail-2:#16283C;--ink:#16202B;
--muted:#667585;--faint:#93A0AD;--rule:#E4E9EE;--accent:#12B39B;--accent-soft:#E2F7F3;
--gap:#C2571E;--gap-soft:#FDF0E6;--ok:#1F7A55;--ok-soft:#E6F4EC;
--serif:"Newsreader",Georgia,serif;--sans:"Source Sans 3",ui-sans-serif,system-ui,sans-serif}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0B1219;
--panel:#131D27;--rail:#0A121B;--rail-2:#16242F;--ink:#E7ECF1;--muted:#93A0AD;
--faint:#6B7885;--rule:#22303C;--accent:#3FD3BA;--accent-soft:#12312C;--gap:#E0954F;
--gap-soft:#33240F;--ok:#57B98A;--ok-soft:#12301F}}
:root[data-theme=dark]{--bg:#0B1219;--panel:#131D27;--rail:#0A121B;--rail-2:#16242F;
--ink:#E7ECF1;--muted:#93A0AD;--faint:#6B7885;--rule:#22303C;--accent:#3FD3BA;
--accent-soft:#12312C;--gap:#E0954F;--gap-soft:#33240F;--ok:#57B98A;--ok-soft:#12301F}
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
nav a .n{margin-left:auto;font-size:11px;font-weight:700;color:var(--accent)}
.rail .who{margin-top:auto;background:var(--rail-2);border-radius:9px;padding:10px 11px;
display:flex;align-items:center;gap:9px}
.rail .who .av{width:29px;height:29px;border-radius:50%;background:var(--accent);
display:grid;place-items:center;font-size:12px;font-weight:700;color:#06231E;flex:none}
.rail .who div span{display:block;font-size:12.5px;font-weight:700;color:#fff}
.rail .who div small{font-size:11px;color:#8496A6}

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

/* ---- honesty banner ---- */
.note{background:var(--accent-soft);border:1px solid var(--accent);border-radius:9px;
padding:10px 13px;font-size:13px;color:var(--ink);margin-bottom:18px}
.note b{font-weight:700}

/* ---- stat cards ---- */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(196px,1fr));gap:13px;
margin-bottom:22px}
.stat{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:14px 15px}
.stat .row{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.stat .lbl{font-size:12.5px;color:var(--muted);font-weight:600;line-height:1.35}
.stat .ico{width:27px;height:27px;border-radius:7px;background:var(--accent-soft);
display:grid;place-items:center;flex:none}
.stat .ico svg{width:14px;height:14px;color:var(--accent)}
.stat .big{font-family:var(--serif);font-size:30px;font-weight:700;letter-spacing:-.02em;
margin:6px 0 2px;font-variant-numeric:tabular-nums}
.stat .sub{font-size:11.5px;color:var(--faint)}
.stat .sub em{font-style:normal;color:var(--ok);font-weight:700}

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
.bar{display:flex;flex-direction:column;gap:5px}
.bar .keys{display:flex;justify-content:space-between;font-size:10.5px;font-weight:700;
color:var(--muted)}
.bar .keys .g{color:var(--gap)}
.bar .track{height:5px;border-radius:3px;background:var(--rule);overflow:hidden;display:flex}
.bar .track i{display:block;height:100%}
.bar .track i.all{background:var(--ok)}
.bar .track i.some{background:var(--gap)}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto}
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

/* ---- story detail ---- */
.back{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--accent);
font-weight:700;margin-bottom:14px}
.sheet{background:var(--panel);border:1px solid var(--rule);border-radius:11px;
padding:22px 24px;max-width:900px}
.sheet header h1{font-family:var(--serif);font-size:clamp(21px,3.4vw,30px);font-weight:700;
line-height:1.16;letter-spacing:-.015em;margin:0 0 9px;text-wrap:balance}
.sheet header p.lede{font-size:14px;color:var(--muted);margin:0 0 4px}
h3.sub{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.09em;
color:var(--muted);margin:26px 0 7px;padding-bottom:6px;border-bottom:1px solid var(--rule)}
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
thead th.na{color:var(--faint)}
td.f{font-family:var(--serif);font-size:14px;line-height:1.4}
td.m{text-align:center;font-size:15px;font-weight:700}
td.m.y{color:var(--ok)}td.m.n{color:var(--gap);background:var(--gap-soft)}
td.m.q{color:var(--faint);background:var(--bg);font-weight:400}
tfoot td{font-size:12px;color:var(--muted);border-bottom:none;padding-top:10px;
text-align:center;font-variant-numeric:tabular-nums}
tfoot td:first-child{text-align:left;font-weight:700;color:var(--ink)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);padding:2px 0 12px}
.legend i{font-style:normal;font-weight:700}
.legend i.y{color:var(--ok)}.legend i.n{color:var(--gap)}.legend i.q{color:var(--faint)}
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

@media(max-width:1080px){.cols{grid-template-columns:minmax(0,1fr)}}
@media(max-width:820px){
.app{grid-template-columns:1fr}
.rail{position:static;height:auto;flex-direction:row;align-items:center;gap:12px;
overflow-x:auto;padding:10px 14px}
.rail nav{flex-direction:row;gap:4px}
.rail nav a{white-space:nowrap}
.rail .who{display:none}
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
 "layers": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 2 7l10 5 10-5-10-5Z"/><path d="M2 12l10 5 10-5"/><path d="M2 17l10 5 10-5"/></svg>',
 "globe": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19"/><path d="M12 2.5a15 15 0 0 1 0 19a15 15 0 0 1 0-19Z"/></svg>',
 "gap": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3H4.5A1.5 1.5 0 0 0 3 4.5v15A1.5 1.5 0 0 0 4.5 21H9"/><path d="M15 3h4.5A1.5 1.5 0 0 1 21 4.5v15a1.5 1.5 0 0 1-1.5 1.5H15"/><path d="M12 8v8"/></svg>',
 "doc": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2.5H7A1.5 1.5 0 0 0 5.5 4v16A1.5 1.5 0 0 0 7 21.5h10A1.5 1.5 0 0 0 18.5 20V7L14 2.5Z"/><path d="M13.5 2.5V7.5h5"/></svg>',
 "hash": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3 7.5 21M16.5 3 15 21M3.5 8.5h17M3 15.5h17"/></svg>',
 "info": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="M12 11v6M12 7.5v.01"/></svg>',
 "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m16.5 16.5 4 4"/></svg>',
 "arrow": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>',
}

NAV = (("index.html", "grid", "Dashboard"),
       ("index.html#stories", "layers", "Stories"),
       ("search.html", "search", "Search"),
       ("index.html#outlets", "globe", "Outlets"),
       ("index.html#gaps", "gap", "Coverage gaps"),
       ("index.html#figures", "hash", "Figures"),
       ("index.html#about", "info", "What this is not"))


def e(text):
    return html.escape(str(text if text is not None else ""))


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


def coverage_table(cluster):
    """Facts down the side, outlets across the top."""
    read = sorted({a["source"] for a in cluster["articles"] if a["fetched"]})
    unread = sorted({a["source"] for a in cluster["articles"] if not a["fetched"]})
    outlets = read + unread
    if not cluster["consensus"] or not read:
        return '<p class="empty">No fact was carried by more than one readable outlet.</p>'

    head = "".join(
        f'<th scope="col"{" class=\'na\'" if o in unread else ""}>{e(o)}</th>'
        for o in outlets)
    rows, carried = [], dict.fromkeys(outlets, 0)
    for group in cluster["consensus"]:
        reported = set(group.get("reported_by") or [])
        cells = []
        for o in outlets:
            if o in unread:
                cells.append('<td class="m q">?</td>')
            elif o in reported:
                cells.append('<td class="m y">&check;</td>')
                carried[o] += 1
            else:
                cells.append('<td class="m n">&mdash;</td>')
        fact = group["anchor"]["text"]
        rows.append(f'<tr><td class="f">{e(trim(fact, 170))}</td>{"".join(cells)}</tr>')

    total = len(cluster["consensus"])
    foot = "".join(
        f'<td>{"not read" if o in unread else f"{carried[o]} of {total}"}</td>'
        for o in outlets)
    return (
        '<div class="scroll"><table><thead><tr>'
        f'<th scope="col">Fact reported</th>{head}</tr></thead><tbody>'
        f'{"".join(rows)}</tbody><tfoot><tr><td>Facts carried</td>{foot}</tr>'
        '</tfoot></table></div>'
        '<div class="legend"><span><i class="y">&check;</i> reported this</span>'
        '<span><i class="n">&mdash;</i> did not report this</span>'
        '<span><i class="q">?</i> we could not read this outlet</span></div>'
    )


def headline_list(cluster):
    items = []
    for article in cluster["articles"]:
        unread = "" if article["fetched"] else '<span class="unread">could not read</span>'
        link = e(article.get("url") or "")
        items.append(
            f'<li><div><span class="hsrc">{e(article["source"])}{unread}</span></div>'
            f'<a href="{link}" target="_blank" rel="noopener noreferrer">'
            f'{e(article["title"])}</a></li>')
    return f'<ul class="heads">{"".join(items)}</ul>'


def framing_block(cluster):
    records = [f for f in (cluster.get("framing") or []) if f.get("sources")]
    if not records:
        return '<p class="empty">No person or institution was described by two readable outlets.</p>'
    out = []
    for record in records[:3]:
        rows = []
        for entry in sorted(record["sources"], key=lambda s: -s["score"]):
            mentions = entry.get("mentions", 1)
            plural = "s" if mentions != 1 else ""
            own = entry.get("example_frame") or entry["frame"]
            rows.append(
                f'<div class="quote"><div><span class="qsrc">{e(entry["source"])}</span>'
                f'<span class="qtone">{e(entry["frame"])} overall</span>'
                f'<span class="qtone">across {mentions} mention{plural}</span></div>'
                f'<blockquote>{e(trim(entry.get("example"), 230))}'
                f'<span class="qmark">this sentence: {e(own)}</span></blockquote></div>')
        out.append(f'<h3 class="sub">How they described {e(record["entity"])}</h3>'
                   + "".join(rows))
    return ('<p class="hint">Each outlet’s label is its average across every mention '
            'of that name. The quote is its sharpest single mention, scored separately.</p>'
            + "".join(out))


def _figure_row(row):
    tags = []
    if row.get("credited_to"):
        tags.append(f'credits {e(row["credited_to"])}')
    if row.get("cumulative"):
        tags.append("running total")
    if row.get("currency") and row["currency"] != "unspecified":
        tags.append(e(row["currency"]).upper())
    elif row.get("unit") == "currency":
        tags.append("currency not stated")
    if row.get("breakdown"):
        tags.append("of which " + ", ".join(e(b) for b in row["breakdown"][:3]))
    tagging = "".join(f'<span class="ftag">{t}</span>' for t in tags)
    link = e(row.get("url") or "")
    more = (f' <a href="{link}" target="_blank" rel="noopener noreferrer">'
            f'read the original</a>') if link else ""
    return (f'<div class="fig"><div class="fhead">'
            f'<span class="fnum">{e(row["figure"])}</span>'
            f'<span class="fsrc">{e(row["source"])}</span>{tagging}</div>'
            f'<p class="fctx">{e(trim(row.get("context") or row["sentence"], 420))}'
            f'{more}</p></div>')


def figures_block(cluster):
    digest = cluster.get("figure_digest") or []
    groups = digest_groups(digest)
    out = []

    for group in groups:
        out.append(f'<p class="hint">{len(group["sources"])} outlets gave a figure in '
                   f'<b>{e(group["unit"])}</b>, counting the same thing.</p>')
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

    if ungrouped:
        out.append('<h3 class="sub">Same kind of figure, possibly not the same thing</h3>')
        out.append('<p class="hint">More than one outlet published a figure in this unit, '
                   'but they are far enough apart that calling them one quantity would be '
                   'a guess. Read the source and the context and judge for yourself &mdash; '
                   'a national total and a county total are both true.</p>')
        out.extend(_figure_row(row) for row in ungrouped)

    if solo:
        out.append('<h3 class="sub">Reported by one outlet only</h3>')
        out.append('<p class="hint">No other outlet we could read published a figure '
                   'counting the same thing, so there is nothing to set these beside.</p>')
        out.extend(_figure_row(row) for row in solo)

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
        '<div class="who"><span class="av">KE</span><div>'
        '<span>Kenyan reader</span><small>Demonstration</small></div></div>'
        '</aside>')


def shell(title, active, body, generated, search="link", scripts=""):
    """The page frame. search is how the top bar's box behaves: "filter" narrows
    the dashboard's stories as you type, "link" sends the query to the search
    page, and None leaves the box out (the search page has its own)."""
    box = ""
    if search:
        hint = ("Filter stories, or press Enter to search every article"
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
        f'<span class="stamp">Run of {e(generated)}</span></div>'
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


def stat(label, value, sub, icon):
    return (f'<div class="stat"><div class="row"><span class="lbl">{e(label)}</span>'
            f'<span class="ico">{ICON[icon]}</span></div>'
            f'<div class="big">{e(value)}</div>'
            f'<div class="sub">{sub}</div></div>')


def story_tile(cluster):
    articles = cluster["articles"]
    sources = sorted({a["source"] for a in articles})
    read = sorted({a["source"] for a in articles if a["fetched"]})
    groups = cluster["consensus"]
    total = len(groups) or 1
    # a fact every readable outlet carried, versus one some of them left out
    shared = sum(1 for g in groups if not g.get("omitted_by"))
    gaps = len(groups) - shared
    tiers = summarise(cluster.get("figure_digest") or [])
    coherence = cluster.get("coherence") or 0

    chips = [cluster.get("topic_label") or "General"]
    chips += list(sources[:2])
    badges = []
    if gaps:
        badges.append(f'<span class="badge gap">{gaps} '
                      f'fact{"s" if gaps != 1 else ""} not carried by all</span>')
    else:
        badges.append('<span class="badge ok">every fact carried by all</span>')
    if tiers["shared"]:
        badges.append(f'<span class="badge fig">{tiers["shared"]} figures from several outlets</span>')
    if coherence and coherence < 0.5:
        badges.append('<span class="badge loose">loose grouping</span>')

    find = " ".join([cluster.get("title_summary") or "", cluster.get("subject") or "",
                     cluster.get("topic_label") or ""] + sources).lower()
    chips_html = "".join(f'<span class="chip">{e(c)}</span>' for c in chips)
    return (
        f'<a class="tile" href="story-{cluster["cluster_id"]}.html" '
        f'data-find="{e(find)}">'
        f'<div class="chips">{chips_html}</div>'
        f'<h3>{e(trim(cluster.get("title_summary") or "Untitled story", 96))}</h3>'
        f'<div class="srcline">{ICON["doc"]}<span>{len(sources)} outlets covered this'
        f' &middot; {len(read)} readable</span></div>'
        f'<div class="bar"><div class="keys">'
        f'<span>{shared} carried by all</span>'
        f'<span class="g">{gaps} not</span></div>'
        f'<div class="track"><i class="all" style="width:{100*shared/total:.0f}%"></i>'
        f'<i class="some" style="width:{100*gaps/total:.0f}%"></i></div></div>'
        f'<div class="badges">{"".join(badges)}</div></a>')


def dashboard(clusters, generated, stats):
    tiles = "".join(story_tile(c) for c in clusters)

    outlets = {}
    for c in clusters:
        for a in c["articles"]:
            row = outlets.setdefault(a["source"], {"n": 0, "read": 0})
            row["n"] += 1
            row["read"] += 1 if a["fetched"] else 0
    ranked = sorted(outlets.items(), key=lambda kv: -kv[1]["n"])[:6]
    rank_rows = "".join(
        f'<div class="r"><b>{i}</b><div><span>{e(name)}</span>'
        f'<small>{d["n"]} article{"s" if d["n"] != 1 else ""} here'
        f' &middot; {d["read"]} readable</small></div></div>'
        for i, (name, d) in enumerate(ranked, start=1))

    unread = sorted({a["source"] for c in clusters for a in c["articles"]
                     if not a["fetched"]})

    body = (
        '<div class="note"><b>Demonstration.</b> Every number and quotation below comes '
        f'from a real Newseye run over 12 Kenyan RSS feeds, {e(generated)}. '
        'Nothing here is mock data.</div>'

        '<div class="stats">'
        + stat("Stories tracked", f'{stats["usable"]}',
               f'of {stats["clusters"]} groups &middot; <em>{stats["multi"]} span 2+ outlets</em>',
               "layers")
        + stat("Articles ingested", f'{stats["articles"]:,}',
               f'<em>+{stats["today"]} in 24h</em> &middot; unattended since 20 Sept',
               "doc")
        + stat("Facts not carried by all", f'{stats["gaps"]}',
               f'across the {len(clusters)} stories shown here', "gap")
        + stat("Outlets tracked", f'{stats["outlets"]}',
               f'RSS polled every 2 hours &middot; <em>{stats["filing"]} filed today</em>',
               "globe")
        + '</div>'

        '<div class="cols"><div>'
        '<div class="colhead" id="stories"><h2>Kenyan news stories</h2>'
        f'<span class="hint"><span id="shown">{len(clusters)} stories</span>'
        ' &middot; most outlets first</span></div>'
        f'<div class="grid">{tiles}</div>'
        '<div class="empty-grid" id="nores" style="display:none">No story on this page '
        'matches that. Press Enter to search every article.</div>'
        '</div><div>'

        f'<div class="panel" id="outlets"><h4>Most present outlets</h4>'
        f'<div class="rank">{rank_rows}</div></div>'

        '<div class="panel quiet" id="gaps"><h4>Why "not carried" is not "wrong"</h4>'
        '<p>An outlet can leave a fact out because it judged it unimportant, because it '
        'ran a shorter piece, or because it filed earlier. None of those is an error.</p>'
        '<p>The gap is worth seeing anyway: it is the difference between the story you '
        'got and the story that was available.</p></div>'

        + (f'<div class="panel quiet"><h4>Could not be read</h4>'
           f'<p>These outlets covered stories here but their article text was paywalled '
           f'or blocked, so they are never counted as having omitted anything:</p>'
           f'<ul class="plain">{"".join(f"<li>{e(s)}</li>" for s in unread)}</ul></div>'
           if unread else "")

        + '<div class="panel quiet" id="about"><h4>What this does not do</h4>'
        '<p>It does not detect contradictions. Across 151 story groups it found none '
        'between two different outlets, so there is no count for them.</p>'
        '<p>It does not label an outlet supportive or critical, score accuracy, or rank '
        'outlets by trust. It does not decide which of two numbers is right.</p>'
        '<p id="figures">Where two outlets publish figures too far apart to be one '
        'quantity, both are shown with their sentences and neither is called wrong.</p>'
        '</div></div></div>'
    )
    return shell("Newseye - Kenyan media coverage", "Dashboard", body, generated,
                 search="filter")


def story_page(cluster, generated):
    coherence = cluster.get("coherence") or 0
    sources = len({a["source"] for a in cluster["articles"]})
    loose = ""
    if coherence and coherence < 0.5:
        loose = (f'<div class="loose"><b>We are not confident these are one story.</b> '
                 f'These articles score {coherence:.2f} on our similarity check, below the '
                 f'0.50 floor. Asking who left a fact out only means something when every '
                 f'outlet is covering the same event, so read the comparison below with '
                 f'that in mind.</div>')
    subject = cluster.get("subject")
    body = (
        f'<a class="back" href="index.html">{ICON["arrow"]}All stories</a>'
        '<div class="sheet"><header>'
        f'<h1>{e(trim(cluster.get("title_summary") or "Untitled story", 110))}</h1>'
        f'<p class="lede">{sources} outlets covered this. {cluster["retrieved"]} of '
        f'{len(cluster["articles"])} articles could be read.</p>'
        + (f'<p class="lede">Subject: {e(subject)}</p>' if subject else "")
        + '</header>'
        + loose
        + '<h3 class="sub">The coverage</h3>' + headline_list(cluster)
        + '<h3 class="sub">Who told you what</h3>'
        + '<p class="hint">Each row is a fact one outlet reported. A dash means that '
          'outlet did not carry it. A question mark means we could not read that '
          'outlet at all, so it is never counted as leaving anything out.</p>'
        + coverage_table(cluster)
        + framing_block(cluster)
        + '<h3 class="sub">The numbers each outlet gave</h3>'
        + '<p class="hint">Grouped where two or more outlets published the same kind of '
          'figure. Read the context &mdash; some are not measuring the same thing.</p>'
        + figures_block(cluster)
        + '<footer class="end">Newseye groups articles reporting the same event and '
          'compares what each outlet included. It does not rate outlets, score accuracy, '
          'or tell you who to trust.</footer></div>'
    )
    return shell(cluster.get("title_summary") or "Story", "Stories", body, generated)


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
            row["url"],
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
             `<a href="${esc(a[URL_])}" target="_blank" rel="noopener noreferrer">` +
             `${esc(a[TITLE])}</a></li>`;
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
           `<h3><a href="${esc(a[URL_])}" target="_blank" rel="noopener noreferrer">` +
           `${esc(a[TITLE])}</a></h3>` +
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
    """Live totals for the header cards, with a fallback when the DB is absent."""
    gaps = sum(1 for c in clusters for g in c["consensus"] if g.get("omitted_by"))
    stats = {"gaps": gaps, "clusters": len(clusters), "usable": len(clusters),
             "multi": len(clusters), "articles": 0, "today": 0, "outlets": 12, "filing": 0}
    try:
        from backend.db.connection import get_cursor
        with get_cursor() as cur:
            cur.execute("SELECT count(*) n FROM articles")
            stats["articles"] = cur.fetchone()["n"]
            cur.execute("SELECT count(*) n FROM articles "
                        "WHERE inserted_at_utc > now() - interval '24 hours'")
            stats["today"] = cur.fetchone()["n"]
            cur.execute("SELECT count(*) c, count(*) FILTER (WHERE coherence >= 0.50) u "
                        "FROM clusters")
            row = cur.fetchone()
            stats["clusters"], stats["usable"] = row["c"], row["u"]
            cur.execute("""SELECT count(*) n FROM (
                             SELECT cm.cluster_id FROM cluster_members cm
                             JOIN articles a ON a.id = cm.article_id
                             JOIN clusters c ON c.id = cm.cluster_id
                             WHERE c.coherence >= 0.50
                             GROUP BY 1 HAVING count(DISTINCT a.source_name) >= 2) t""")
            stats["multi"] = cur.fetchone()["n"]
            # the configured feed list, not DISTINCT source_name: the articles
            # table still carries 61 rows under "| Daily Nation", a malformed
            # name from an earlier feed config, dormant since 30 August. It is
            # outside the 7-day clustering window so it never reaches a
            # comparison, but counting it would claim an outlet we do not poll.
            from backend.config import RSS_FEEDS
            stats["outlets"] = len(RSS_FEEDS)
            cur.execute("""SELECT count(DISTINCT source_name) n FROM articles
                           WHERE inserted_at_utc > now() - interval '24 hours'""")
            stats["filing"] = cur.fetchone()["n"]
    except Exception as exc:
        # the export alone is enough to render; the cards just lose the corpus totals
        print(f"  (corpus totals unavailable: {type(exc).__name__}) ")
    return stats


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
        if stale.startswith("story-") and stale.endswith(".html"):
            try:
                os.remove(os.path.join(out_dir, stale))
            except OSError:
                pass

    stats = corpus_stats(clusters)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(dashboard(clusters, generated, stats))
    for cluster in clusters:
        path = os.path.join(out_dir, f"story-{cluster['cluster_id']}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(story_page(cluster, generated))
    with open(os.path.join(out_dir, "search.html"), "w", encoding="utf-8") as fh:
        fh.write(search_page(generated))

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
