"""How each outlet presents one public figure, side by side.

For every headline and snippet that names the person, this records the part
they play in the sentence and in whose words:

  speaks        quoted or reported speaking: "Gachagua claims...", "Ruto: We will..."
  acts          doing something: "Kindiki launches...", "Sakaja orders..."
  acted on      something done or said to them: "MPs slam Ruto",
                "Gachagua impeached", "...hits back at Ruto"
  described     the sentence says what they are: "Uhuru was right"
  spoken about  inside someone else's quoted words: "Kalonzo: Uhuru was right"
  mentioned     anything else: "Ipoa probes shooting at Kindiki meeting"

with the verb as the outlet wrote it, who did it to them, and the title the
outlet gave them ("Former DP", "Deputy President", none). The headline itself
is kept, so every count can be checked against what was published.

It decides nothing. There is no bias score: an outlet that writes "Ruto
assures" where another writes "Ruto claims" is shown doing so, beside the
headlines, and the reader judges. Reporting verbs are grouped (config
REPORTING_VERBS) only so a comparison can be read at a glance; the verbs are
always shown too.

Counts reflect which stories an outlet chose to cover as well as how it wrote
them. Kenya News is the government's own news agency and KBC the state
broadcaster: reporting government activity is their remit, and that is a fact
about them rather than something this module discovered.

    python -m backend.analysis.portrayal Gachagua
    python -m backend.analysis.portrayal "Kithure Kindiki" --days 30
"""
import argparse
import html
import re
from collections import Counter, defaultdict

from backend.config import (
    FRAMING_SENTIMENT,
    FRAMING_TARGETED_THRESHOLD,
    NAME_TITLES,
    REPORTING_VERBS,
    TARGETED_ENT_TYPES,
)
from backend.db.connection import get_cursor
from backend.nlp.entities import all_names, find_person, load_nlp, people
from backend.nlp.truecase import build_casing_lexicon, is_title_case, truecase

ROLES = ("speaks", "acts", "acted on", "described", "spoken about", "mentioned")
QUOTED = "quoted directly"
FAMILY = {verb: family for family, verbs in REPORTING_VERBS.items() for verb in verbs}
# "Kalonzo: Uhuru was right" - a short head naming a speaker, then their words
COLON_HEAD = re.compile(r"^\s*([^:]{2,60}?)\s*:\s+\S")
DOUBLE_QUOTE = re.compile(r"[“\"]([^“”\"]{2,})[”\"]")
# single quotes double as apostrophes, so only a quote that opens a word and
# closes one counts: 'Involve us' yes, Ruto's no
SINGLE_QUOTE = re.compile(r"(?:(?<=\s)|^)‘([^‘’]{2,}?)’(?=[\s,.:;!?]|$)")
# words that may stand in front of a name as part of what the outlet calls them
TITLE_WORDS = ({w for t in NAME_TITLES for w in t.split()}
               | {"former", "ex", "outgoing", "incoming", "acting", "late", "embattled",
                  "impeached", "nominated", "retired", "jailed", "ousted", "deputy",
                  "prime", "cabinet", "secretary", "principal", "chief", "inspector",
                  "general", "attorney", "auditor", "leader", "boss", "mr", "mrs", "ms",
                  "lady", "madam", "veteran", "rebel", "firebrand"}) - {"of", "the", "and"}
# particles that make a verb phrase: "hit back", "lash out", "call on"
PARTICLES = {"back", "out", "up", "down", "off", "on", "for"}
# "NAIROBI, Kenya Sep 20 - " opens Capital FM's snippets; parsed, the city
# became the subject of the sentence's verb
DATELINE = re.compile(r"^[A-Z][A-Z .'\-]{2,}(?:,\s*[A-Z][a-z]+)?(?:\s+[A-Z][a-z]{2,8}\.?\s+\d{1,2})?\s*[\u2013\u2014-]\s*")
# fewer headlines and opening lines than this give no tone summary at all
TONE_MIN_SENTENCES = 4
# verbs that say what someone is rather than what they do
COPULAS = {"be", "remain", "become", "seem", "appear"}
# verbs that carry no action of their own; at the very end of a text they mean
# the clause was cut off before its real verb
AUXILIARIES = {"have", "be", "do", "will", "would", "can", "could", "shall", "should",
               "may", "might", "must"}
# nouns that carry the action in "takes aim at", "takes a swipe at", "hits out at"
TARGET_NOUNS = {"aim", "swipe", "jibe", "dig", "shot", "shots", "potshots", "broadside"}
# title words that describe a role only when they attach to the name itself
MODIFIERS = {"former", "ex", "outgoing", "incoming", "acting", "late", "embattled",
             "impeached", "nominated", "retired", "jailed", "ousted", "veteran",
             "rebel", "firebrand"}
# spaCy misreads a curly possessive: "joining Gachagua’s DCP" made Gachagua the
# one being joined. One character for one, so text positions do not move.
CURLY_POSSESSIVE = re.compile(r"(?<=\w)\u2019(?=s\b)")


def family_of(phrase):
    """The REPORTING_VERBS group for a verb phrase, if it reports speech."""
    if not phrase:
        return None
    words = phrase.split()
    for candidate in (phrase, " ".join(words[:2]), words[0]):
        if candidate in FAMILY:
            return FAMILY[candidate]
    return None


def verb_phrase(verb):
    """The verb as a lemma, with its particle: "hits back" -> "hit back"."""
    particle = next((c.lower_ for c in verb.children
                     if c.dep_ == "prt" or (c.dep_ == "advmod" and c.lower_ in PARTICLES)), None)
    lemma = (verb.lemma_ or verb.lower_).lower()
    return f"{lemma} {particle}" if particle else lemma


def _name(token_or_span):
    """A readable name for whoever a token stands for, canonical when listed."""
    doc = token_or_span.doc
    token = token_or_span if not hasattr(token_or_span, "root") else token_or_span.root
    for ent in doc.ents:
        if ent.start <= token.i < ent.end:
            listed = people().get(ent.ent_id_)
            return listed["name"] if listed else ent.text
    words = [t.text for t in token.subtree if not t.is_punct]
    return " ".join(words[:5])


def _subject(verb):
    subject = next((c for c in verb.children if c.dep_ in ("nsubj", "nsubjpass")), None)
    return _name(subject) if subject is not None else None


def _agent(verb):
    by = next((c for c in verb.children if c.dep_ == "agent"), None)
    target = next((c for c in by.children if c.dep_ == "pobj"), None) if by is not None else None
    return _name(target) if target is not None else None


def grammatical_role(span):
    """(role, verb phrase, by whom) from the dependency parse."""
    token = span.root
    # "Ruto and Gachagua clash": a second name shares the first's role. A name in
    # apposition plays the part of the words it renames: a title in front of a
    # name ("Nairobi Senator Edwin Sifuna has said") can parse the name as
    # renaming "Nairobi", and the held-out test found "... EALA MP Winnie Odinga
    # are preparing" read as named in passing
    while token.dep_ == "appos" or (token.dep_ == "conj" and token.head.ent_type_ == "PERSON"):
        token = token.head
    dep = token.dep_
    # a name or acronym is never the verb: "Gachagua's DCP" once yielded "dcps"
    if token.head.ent_type_ or token.head.is_upper:
        return "mentioned", None, None
    if dep in ("nsubj", "nsubjpass"):
        verb = token.head
        # an opening line is cut at 150 characters and can stop mid-clause:
        # "... Oburu has" left "have" as his verb, and he was counted as acting
        if (verb.lemma_.lower() in AUXILIARIES
                and all(t.is_punct for t in verb.doc[verb.i + 1:])):
            return "mentioned", None, None
        phrase = verb_phrase(verb)
        if dep == "nsubjpass":
            return "acted on", phrase, _agent(verb)
        if phrase in COPULAS:
            attribute = next((c for c in verb.children if c.dep_ in ("acomp", "attr")), None)
            words = [t.text for t in attribute.subtree][:6] if attribute is not None else []
            return "described", " ".join(words) or None, None
        if not family_of(phrase):
            # "has called for reforms": "call for" is a reporting verb, but "for"
            # hangs off the verb as a preposition, so the phrase read as "call"
            phrase = next((f"{phrase} {c.lower_}" for c in verb.children
                           if c.dep_ == "prep" and family_of(f"{phrase} {c.lower_}")), phrase)
        return ("speaks" if family_of(phrase) else "acts"), phrase, None
    if dep in ("dobj", "obj", "dative"):
        verb = token.head
        return "acted on", verb_phrase(verb), _subject(verb)
    if dep == "pobj":
        prep = token.head
        head = prep.head
        if prep.lower_ == "to" and head.lower_ == "according":
            return "speaks", "according to", None
        if prep.lower_ == "by" and head.tag_ == "VBN":
            return "acts", verb_phrase(head), None
        if head.pos_ in ("VERB", "AUX") and prep.lower_ in ("at", "against", "on", "over", "to"):
            return "acted on", f"{verb_phrase(head)} {prep.lower_}", _subject(head)
        # "Nyoro takes aim at Ruto", "takes a swipe at Kindiki": the target hangs
        # off a noun, and the noun off the verb
        if head.pos_ == "NOUN" and head.lower_ in TARGET_NOUNS and head.head.pos_ == "VERB":
            verb = head.head
            return "acted on", f"{verb_phrase(verb)} {head.lower_} {prep.lower_}", _subject(verb)
    return _headline_verb(span)


def _headline_verb(span):
    """Headline grammar the parser misreads: "President Ruto orders compensation".

    Headlines drop the words that tell a parser "orders" is a verb, so it reads
    "Ruto orders" as a noun phrase. When a name opens the headline and the next
    word is a lowercase -s form the casing lexicon writes in lowercase, that
    word is taken as the verb - the present tense headlines are written in.
    """
    doc = span.doc
    nxt = doc[span.end] if span.end < len(doc) else None
    opens = all(t.lower_ in TITLE_WORDS or t.is_punct for t in doc[:span.start])
    # only a word the parser called a noun: "'s" and "vs" are lowercase and end
    # in s too, and were read as verbs until this was required
    if (nxt is None or not opens or not nxt.is_lower or not nxt.is_alpha
            or len(nxt.text) < 4 or not nxt.text.endswith("s")
            or nxt.pos_ not in ("NOUN", "PROPN")):
        return "mentioned", None, None
    phrase = nxt.lemma_.lower() if nxt.lemma_ else nxt.lower_[:-1]
    return ("speaks" if family_of(phrase) else "acts"), phrase, None


def title_of(span):
    """What the outlet calls them, read from the words just before the name.

    Title words, and the organisation or place that qualifies them, read
    leftwards for as long as each word hangs off the name or off a word
    already taken: "Former Deputy President", "DCP leader", "Narok Governor".
    """
    doc, taken = span.doc, set(range(span.start, span.end))
    i = span.start - 1
    while i >= 0 and span.start - i <= 6:
        token = doc[i]
        attached = token.dep_ in ("compound", "amod", "nmod", "poss") and token.head.i in taken
        # a capitalised word that is not a known place or body is not a title:
        # "Besigye's Wife Confronts Ruto" gave Ruto the title "confronts"
        # - unless it qualifies a title already taken: "Interior CS", "Health CS"
        qualifies = i + 1 in taken and doc[i + 1].lower_ in TITLE_WORDS
        describes = (token.ent_type_ in ("GPE", "LOC", "ORG", "NORP")
                     or token.pos_ in ("NOUN", "ADJ") or qualifies)
        # "former" must attach to the name: in "hosts former Ruto ally" it is the ally's
        title = token.lower_ in TITLE_WORDS and (token.lower_ not in MODIFIERS or attached)
        if title or (attached and describes):
            taken.add(i)
            i -= 1
        elif token.text in ("'s", "’s") and i - 1 >= 0 and doc[i - 1].ent_type_ in ("GPE", "ORG"):
            taken.update({i, i - 1})   # "ODM's Sifuna"
            i -= 2
        else:
            break
    return " ".join(doc[j].text for j in sorted(taken) if j < span.start)


def _speaker_head(doc, end_char):
    """The person or body a "Name: words" headline quotes, or None.

    Only a head that is a name with its titles counts. "Gachagua vs Uhuru:
    The battle for Mt Kenya" and "2027: How court puts IEBC..." are headings,
    not attributions.
    """
    # "Wanga to Kalonzo: We loved you..." - a speaker addressing someone. The
    # addressee after "to" is not the speaker, so only the part before it counts.
    to = next((t for t in doc if t.idx < end_char and t.lower_ == "to"), None)
    limit = to.idx if to is not None else end_char
    ents = [e for e in doc.ents if e.end_char <= limit and e.label_ in ("PERSON", "ORG")]
    if not ents:
        return None
    speaker = ents[-1]
    for token in doc:
        if token.idx >= limit:
            break
        if speaker.start <= token.i < speaker.end or token.is_punct or token.text in ("'s", "’s"):
            continue
        if token.lower_ not in TITLE_WORDS and token.ent_type_ not in ("GPE", "ORG", "NORP"):
            return None
    return speaker


def quoted_ranges(doc):
    """[(start_char, end_char, speaker, kind)] for quotes and colon-led headlines."""
    text, ranges = doc.text, []
    head = COLON_HEAD.match(text)
    if head and len(head.group(1).split()) <= 6:
        speaker = _speaker_head(doc, head.end(1))
        if speaker is not None:
            ranges.append((head.end(1), len(text), speaker, "colon"))
    for pattern in (DOUBLE_QUOTE, SINGLE_QUOTE):
        for match in pattern.finditer(text):
            speaker = _quote_speaker(doc, match.start(), match.end())
            ranges.append((match.start(), match.end(), speaker, "quote"))
    return ranges


def _quote_speaker(doc, start, end):
    """Whoever a reporting verb outside the quote attributes it to."""
    for token in doc:
        if start <= token.idx < end or not family_of(verb_phrase(token)):
            continue
        subject = next((c for c in token.children if c.dep_ == "nsubj"), None)
        if subject is not None and not (start <= subject.idx < end):
            return subject
    return None


def mentions(doc, person):
    """One record per time this person is named in a parsed text."""
    records = []
    ranges = quoted_ranges(doc)
    for span in doc.ents:
        if span.ent_id_ != person:
            continue
        role = verb = by = None
        for start, end, speaker, kind in ranges:
            if start <= span.start_char < end:
                speaker_name = _name(speaker) if speaker is not None else None
                if speaker is not None and speaker_name == _name(span):
                    continue
                role, by = "spoken about", speaker_name or "unattributed quote"
                break
            if kind == "colon" and speaker is not None and speaker.start == span.start:
                role, verb = "speaks", QUOTED
                break
        if role is None:
            role, verb, by = grammatical_role(span)
        records.append({"role": role, "verb": verb, "by": by,
                        "family": QUOTED if verb == QUOTED else family_of(verb),
                        "title": title_of(span).lower(), "title_text": title_of(span),
                        # where the name sits in the parsed text, for targeted tone
                        "start": span.start_char, "end": span.end_char,
                        "label": span.label_})
    return records


def _period(days):
    if days:
        return "AND published_utc >= now() - %s::interval", [f"{days} days"]
    return "", []


def corpus_context(days=None):
    """What every person's comparison shares: each outlet's article count for the
    period, the casing lexicon, and the period's first and last dates. Built once
    when many people are portrayed together, as the static site does."""
    where, params = _period(days)
    with get_cursor() as cur:
        cur.execute(f"SELECT source_name, count(*) AS n FROM articles WHERE true {where} GROUP BY 1",
                    params)
        totals = {r["source_name"]: r["n"] for r in cur.fetchall()}
        cur.execute(f"""SELECT min(published_utc) AS first, max(published_utc) AS last
                        FROM articles WHERE true {where}""", params)
        span = cur.fetchone()
        cur.execute("SELECT title, coalesce(snippet, '') AS snippet FROM articles")
        everything = cur.fetchall()
    lexicon = build_casing_lexicon(
        [r["snippet"] for r in everything] + [r["title"] for r in everything
                                              if not is_title_case(r["title"])])
    return {"totals": totals, "lexicon": lexicon, "first": span["first"], "last": span["last"]}


def load_rows(person, days=None):
    """Articles whose headline or snippet contains any spelling of the name.

    A text match only finds candidates: the parse then decides whether the name
    is this person, so "Uhuru Park" is fetched for Uhuru Kenyatta and dropped.
    """
    names = all_names(person)
    pattern = r"\m(" + "|".join(re.escape(n) for n in names) + r")\M"
    where, params = _period(days)
    with get_cursor() as cur:
        cur.execute(f"""
            SELECT id, source_name, title, coalesce(snippet, '') AS snippet, url, published_utc
            FROM articles
            WHERE (title ~* %s OR snippet ~* %s) {where}
            ORDER BY published_utc
        """, [pattern, pattern, *params])
        return cur.fetchall()


def portray(person, days=None, nlp=None, context=None, tone=True):
    """({outlet: summary}, {outlet: articles in the period}) for one person.

    The second dict includes outlets that never named them: an outlet that
    published 315 articles and none about a figure is part of the comparison.
    """
    nlp = nlp or load_nlp(lemmas=True)
    context = context or corpus_context(days)
    rows, totals, lexicon = load_rows(person, days), context["totals"], context["lexicon"]
    texts, owners = [], []
    for row in rows:
        texts.append(CURLY_POSSESSIVE.sub("'", truecase(row["title"], lexicon)))
        owners.append((row, "headline"))
        if row["snippet"]:
            snippet = DATELINE.sub("", html.unescape(row["snippet"]))
            texts.append(CURLY_POSSESSIVE.sub("'", snippet))
            owners.append((row, "snippet"))
    outlets = defaultdict(lambda: {"articles": set(), "records": []})
    for (row, field), doc in zip(owners, nlp.pipe(texts), strict=True):
        for record in mentions(doc, person):
            record.update(field=field, text=row["title"] if field == "headline" else row["snippet"],
                          headline=row["title"], url=row["url"], date=row["published_utc"],
                          model_text=doc.text)
            outlet = outlets[row["source_name"]]
            outlet["articles"].add(row["id"])
            outlet["records"].append(record)
    if tone:
        add_tone([r for data in outlets.values() for r in data["records"]])
    return {name: summarise(data, totals.get(name, 0)) for name, data in outlets.items()}, totals


def add_tone(records):
    """Score each headline or opening line for tone; record how in "tone_by".

    By default the sentence as a whole, not its attitude to the person: "Ruto
    condemns the killings" reads negative without being negative about Ruto.
    Shown only as a hint, with that warning, beside the headlines themselves.
    With targeted scoring on (FRAMING_SENTIMENT), each mention is first scored
    for the writer's attitude toward the person, in the text the parser saw;
    sentence tone covers whatever that cannot score.
    """
    from backend.analysis.framing import sentence_sentiment

    pending = records
    if FRAMING_SENTIMENT == "targeted":
        from backend.analysis import targeted
        eligible = [r for r in records
                    if r.get("model_text") and r.get("label") in TARGETED_ENT_TYPES]
        if eligible and targeted.available():
            scores = targeted.targeted_sentiment(
                [(r["model_text"], r["start"], r["end"]) for r in eligible])
            for record, score in zip(eligible, scores, strict=True):
                if score is not None:
                    record["tone"], record["tone_by"] = score, "targeted"
        pending = [r for r in records if r.get("tone_by") != "targeted"]

    texts = sorted({html.unescape(r["text"]) for r in pending if r["text"]})
    scores = dict(zip(texts, sentence_sentiment(texts), strict=True))
    for record in pending:
        record["tone"] = scores.get(html.unescape(record["text"] or ""))
        record["tone_by"] = "sentence"


def tone_summary(scores, thresholds=None):
    """A few words for a set of tone scores, or None when there are too few.

    Labels per sentence follow framing.py: above +0.15 positive, below -0.15
    negative, or each score's own threshold where given (targeted scores use
    FRAMING_TARGETED_THRESHOLD). An outlet leans one way when that side
    outnumbers the other by a quarter of its sentences; otherwise mostly
    neutral, or mixed.
    """
    thresholds = thresholds or [0.15] * len(scores)
    pairs = [(s, t) for s, t in zip(scores, thresholds, strict=True) if s is not None]
    if len(pairs) < TONE_MIN_SENTENCES:
        return None
    positive = sum(s > t for s, t in pairs) / len(pairs)
    negative = sum(s < -t for s, t in pairs) / len(pairs)
    scores = [s for s, _ in pairs]
    if positive - negative >= 0.25:
        label = "leans positive"
    elif negative - positive >= 0.25:
        label = "leans negative"
    elif 1 - positive - negative >= 0.6:
        label = "mostly neutral"
    else:
        label = "mixed"
    return {"label": label, "positive": positive, "negative": negative, "n": len(scores)}


def summarise(data, outlet_total):
    records = data["records"]
    roles = Counter(r["role"] for r in records)
    by_role = defaultdict(list)
    for record in records:
        by_role[record["role"]].append(record)
    examples = {}
    for role, items in by_role.items():
        headline = next((r for r in items if r["field"] == "headline"), items[0])
        examples[role] = headline["text"]
    return {
        "articles": len(data["articles"]),
        "outlet_articles": outlet_total,
        "mentions": len(records),
        "roles": roles,
        "speaking_families": Counter(r["family"] for r in by_role["speaks"] if r["family"]),
        "speaking_verbs": Counter(r["verb"] for r in by_role["speaks"] if r["verb"] != QUOTED),
        "acting_verbs": Counter(r["verb"] for r in by_role["acts"]),
        "acted_on": Counter((r["verb"], r["by"]) for r in by_role["acted on"]),
        "spoken_about_by": Counter(r["by"] for r in by_role["spoken about"]),
        "titles": Counter(r["title"] or "(no title)" for r in records),
        "tone": tone_summary([r.get("tone") for r in records],
                             [FRAMING_TARGETED_THRESHOLD if r.get("tone_by") == "targeted"
                              else 0.15 for r in records]),
        # how the tone was read: "targeted" toward the person, or "sentence"
        "tone_by": sorted({r["tone_by"] for r in records if r.get("tone_by")}),
        # counted in lowercase, shown as most often written: "DCP leader", not "dcp leader"
        "title_forms": {title: Counter(r["title_text"] for r in records if r["title"] == title)
                        .most_common(1)[0][0] for title in {r["title"] for r in records if r["title"]}},
        "examples": examples,
        # every mention, newest first, so a page can show the headlines behind the counts
        "records": sorted(records, key=lambda r: r["date"], reverse=True),
    }


def _done_by(key):
    verb, by = key
    return f"{verb} (by {by})" if by else verb


def _top(counter, n=4, show=str):
    return ", ".join(f"{show(k)} {v}" for k, v in counter.most_common(n)) or "-"


def report(person, outlets, totals, min_articles=3):
    name = people()[person]["name"]
    shown = sorted(((k, v) for k, v in outlets.items() if v["articles"] >= min_articles),
                   key=lambda kv: -kv[1]["articles"])
    total = sum(v["articles"] for v in outlets.values())
    print(f"{name}: {total} articles across {len(outlets)} outlets"
          f" ({len(shown)} with {min_articles}+ shown)\n")
    print(f"{'outlet':<22}{'articles':>9}{'share':>7}  " + "".join(f"{r:>13}" for r in ROLES))
    for outlet, s in shown:
        share = s["articles"] / s["outlet_articles"] if s["outlet_articles"] else 0
        cells = "".join(f"{s['roles'][r] / s['mentions']:>13.0%}" for r in ROLES)
        print(f"{outlet:<22}{s['articles']:>9}{share:>7.1%}  {cells}")
    for outlet, n in sorted(totals.items(), key=lambda kv: -kv[1]):
        if outlet not in outlets:
            print(f"{outlet:<22}{0:>9}{0:>7.1%}  not named in any of its {n} articles")
    for outlet, s in shown:
        print(f"\n{outlet} - {s['articles']} articles")
        print(f"  when speaking    {_top(s['speaking_families'], 5)}")
        print(f"                   verbs: {_top(s['speaking_verbs'], 6)}")
        print(f"  doing            {_top(s['acting_verbs'], 6)}")
        print(f"  done to them     {_top(s['acted_on'], 4, _done_by)}")
        print(f"  in others' words {_top(s['spoken_about_by'], 4)}")
        print(f"  called           {_top(s['titles'], 4)}")
        for role in ("speaks", "acted on", "spoken about"):
            if role in s["examples"]:
                print(f"  e.g. {role:<12} {s['examples'][role][:96]}")
    print("\nCounts include which stories each outlet chose to cover, not only how it"
          "\nwrote them. Nothing here is a judgement; the headlines are the evidence.")


def main():
    parser = argparse.ArgumentParser(description="How each outlet presents a public figure")
    parser.add_argument("person", help="a name, alias or id from backend/data/kenya_entities.json")
    parser.add_argument("--days", type=int, default=None, help="only the last N days")
    parser.add_argument("--min-articles", type=int, default=3)
    args = parser.parse_args()
    person = find_person(args.person)
    if person is None:
        raise SystemExit(f"'{args.person}' is not in backend/data/kenya_entities.json")
    outlets, totals = portray(person, args.days)
    report(person, outlets, totals, args.min_articles)


if __name__ == "__main__":
    main()
