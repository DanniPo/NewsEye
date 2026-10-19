# Quote speakers: AI-assisted check on a separate group - 2026-10-19

**Judged by Claude (an AI assistant), not by a human labeller.** This is not the
held-out human evaluation (`docs/evidence/heldout/quotes.csv`, 8 of 40 labelled by
hand). It is a separate group, checked to the same rule, and must be reported as
AI-assisted.

## Method

- **Group:** every multi-outlet story (coherence 0.50 or more) made only of articles
  collected after 15 Oct 18:30: 8 stories from the 19 Oct passive run, unseen by the
  code and by the held-out sheets. The active tier analysed them on 19 Oct.
- **Sample:** 45 quotes found; 40 drawn at random (seed 20261019).
- **Judgement:** each article was fetched again and the quote located in it (40 of
  40 found). The rule is the held-out sheet's: correct if the article attributes the
  words to the speaker given; for "(unattributed)", correct only if the article
  itself does not make the speaker clear. An office, statement or document counts as
  a speaker when the article names it. Every judgement and its reason is in
  `quotes-ai-check-2026-10-19.csv`.
- **Code:** quote attribution unchanged since the 14 Oct freeze (the 19 Oct role
  fixes do not touch it).

## Result

| | Right | Accuracy (95% Wilson interval) |
|---|---|---|
| All quotes | 25 of 40 | 62.5% (47.0% to 75.8%) |
| Quotes given a speaker | 25 of 27 | 92.6% (76.6% to 97.9%) |
| Quotes left unattributed | 0 of 13 | every one had a clear speaker in the article |

By how the speaker was found: named 9 of 9, pronoun 4 of 4, described 2 of 2,
continued 10 of 12, unattributed 0 of 13.

Against the 90% target: not met overall. When Newseye names a speaker it is right
93% of the time; the shortfall is quotes it leaves unattributed.

## Errors

| Cause | Quotes |
|---|---|
| An English translation in brackets after a Swahili quote, with no attribution of its own | 5 (items 21, 25, 28, 35, 38) |
| A Swahili quote whose reporting verb ("Ruto stated", "he declared", "he stated") was not connected to it, or the second half of such a quote | 4 (items 1, 6, 8, 13) |
| A statement or notice named as the source ("the statement read", "reads part of the notice", "In their statement, KNH...") | 3 (items 17, 26, 34) |
| "she said" where "she" is an unnamed person ("the patient") | 1 (item 20) |
| The previous speaker carried over although the quote had its own "she said" | 1 (item 23) |
| A title cut down to a fragment: "Exchequer" from "The Exchequer chief" (Mbadi) | 1 (item 27) |

## Limits

- One Nairobi Wire article (story 1254, President Ruto on KCC) gave 15 of the 40
  quotes and 9 of the 15 errors: its Swahili quotes each come with a bracketed
  English translation. Quotes from one article are not independent, so the interval
  above is optimistic.
- 40 quotes from 11 articles in 8 stories, one day's news.
