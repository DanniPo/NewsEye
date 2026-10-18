"""Bundle the built static site into one HTML file that can be sent to anyone.

The site is 50-odd pages plus a 4.5 MB search index - fine to host, awkward to
email. This folds every page into one file: each page becomes a hidden section,
links between pages become in-file navigation (#story-485, #person-...), and
the search index is embedded. It opens from an email attachment or a phone's
downloads, with no unzipping and no server.

Needs an internet connection only for what the site always fetched from
outside: the fonts (it falls back to system fonts), the original articles it
links to, and the meaning-based search model (without it, search falls back to
matching words).

    python -m backend.scripts.build_site --export review_export.json --out site
    python -m backend.scripts.single_file --site site --out dist/newseye.html
"""
import argparse
import os
import re

# ids the page scripts look up by name; every other id is namespaced per page
SCRIPT_IDS = {"q", "shown", "nores", "sform", "sq", "sstatus", "sresults"}
LOCAL_PAGE = re.compile(r"^(index|people|search|story-\d+|person-[a-z0-9-]+)\.html(?:#([\w-]+))?$")

ROUTER = """<script>
(function(){
  // Which page to show: #story-485, or #person-x--o-kbc for a part of a page
  function show(){
    var hash = location.hash.slice(1) || 'home';
    var page = hash.split('--')[0];
    var section = document.getElementById('page-' + page) || document.getElementById('page-home');
    var all = document.querySelectorAll('section.page');
    for (var i = 0; i < all.length; i++) all[i].hidden = all[i] !== section;
    document.title = section.getAttribute('data-title');
    var part = hash.indexOf('--') > 0 ? document.getElementById(hash) : null;
    if (part) { if (part.tagName === 'DETAILS') part.open = true; part.scrollIntoView(); }
    else window.scrollTo(0, 0);
  }
  // links built by the search page at run time still say story-485.html
  document.addEventListener('click', function(event){
    var link = event.target.closest && event.target.closest('a[href]');
    if (!link) return;
    var match = link.getAttribute('href').match(%s);
    if (!match) return;
    event.preventDefault();
    location.hash = target(match[1], match[2]);
  });
  // every top-bar search box sends its words to the search section
  document.addEventListener('submit', function(event){
    var form = event.target;
    if (!form.classList.contains('search')) return;
    event.preventDefault();
    var words = (form.querySelector('input') || {}).value || '';
    location.hash = 'search';
    var box = document.getElementById('sq'), search = document.getElementById('sform');
    if (box && search && words) { box.value = words; search.requestSubmit(); }
  });
  function target(page, part){
    page = page === 'index' ? 'home' : page;
    return part ? page + '--' + part : page;
  }
  window.addEventListener('hashchange', show);
  show();
})();
</script>"""


def page_name(filename):
    stem = filename[:-len(".html")]
    return "home" if stem == "index" else stem


def local_href(href, here):
    """An href inside the bundle: page links become hashes, anchors are namespaced."""
    if href.startswith("#") and len(href) > 1:
        return f"#{here}--{href[1:]}"
    match = LOCAL_PAGE.match(href)
    if not match:
        return href
    page = page_name(match.group(1) + ".html")
    return f"#{page}--{match.group(2)}" if match.group(2) else f"#{page}"


def section(filename, html, index_js):
    """One page's body as a hidden section, with its ids and links rewritten."""
    here = page_name(filename)
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    body = html.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    body = re.sub(r'\bid="([^"]+)"',
                  lambda m: m.group(0) if m.group(1) in SCRIPT_IDS else f'id="{here}--{m.group(1)}"',
                  body)
    body = re.sub(r'\bhref="([^"]*)"', lambda m: f'href="{local_href(m.group(1), here)}"', body)
    # the dashboard's filter must only touch the dashboard's story tiles
    body = body.replace("document.querySelectorAll('.tile')",
                        "document.querySelectorAll('#page-home .tile')")
    body = body.replace('<script src="search-index.js"></script>', f"<script>{index_js}</script>")
    return f'<section class="page" id="page-{here}" data-title="{title}" hidden>{body}</section>'


def bundle(site, out):
    pages = sorted(f for f in os.listdir(site) if f.endswith(".html"))
    order = ["index.html", "people.html", "search.html"]
    pages = [p for p in order if p in pages] + [p for p in pages if p not in order]
    index_path = os.path.join(site, "search-index.js")
    index_js = open(index_path, encoding="utf-8").read() if os.path.exists(index_path) else ""
    first = open(os.path.join(site, "index.html"), encoding="utf-8").read()
    head = first.split("<body>", 1)[0].replace("</head>", "<style>[hidden]{display:none!important}"
                                               "</style>\n</head>")
    head = re.sub(r"<title>.*?</title>", "<title>Newseye</title>", head, flags=re.S)
    sections = [section(p, open(os.path.join(site, p), encoding="utf-8").read(), index_js)
                for p in pages]
    router = ROUTER % ("/" + LOCAL_PAGE.pattern.replace("/", "\\/") + "/")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + "<body>\n" + "\n".join(sections) + router + "\n</body>\n</html>\n")
    os.replace(tmp, out)
    return len(pages), os.path.getsize(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bundle the static site into one HTML file")
    parser.add_argument("--site", default="site")
    parser.add_argument("--out", default=os.path.join("dist", "newseye.html"))
    args = parser.parse_args()
    count, size = bundle(args.site, args.out)
    print(f"Bundled {count} pages into {args.out} ({size / 1e6:.1f} MB)")
