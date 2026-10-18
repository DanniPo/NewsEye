# Chapter 5 figures

Twelve figures, numbered in order of first appearance. Each caption goes below
its figure, as the table captions do. Every image is real output: screenshots
of the site built from a pipeline run on 16 October 2026, terminal output from
fresh runs or from the runs' own logs, and charts drawn from the logged data.
Where a terminal figure leaves lines out, the image says so in place.

| Figure | File | Section | Caption (below the figure) |
|---|---|---|---|
| 5.1 | `figure-5-01-dashboard.png` | 5.4.4 | The Newseye dashboard, built from a run on 16 October 2026: stories ordered by the number of outlets covering them, the "Where outlets differ most" panel, and the outlets and people panels. |
| 5.2 | `figure-5-02-story-coverage.png` | 5.4.4 | A story page: each outlet's headline and the "Who told you what" table. ✓ reported the fact, ≈ said something related but not the same, – did not report it, ? the outlet could not be read and is never counted as leaving anything out. |
| 5.3 | `figure-5-03-story-quotes-framing.png` | 5.4.4 | The same story page: each remark as quoted by different outlets (same words, worded differently, or with words added, highlighted), and how each outlet described each person, scored by targeted sentiment (NewsMTSC). |
| 5.4 | `figure-5-04-story-figures.png` | 5.4.4 | The figures on a story page (EPRA fuel prices, 14 October 2026): each figure in bold inside its own sentence, grouped where outlets counted the same thing and kept apart where they may not have. |
| 5.5 | `figure-5-05-people-page.png` | 5.4.4 | A person page (William Ruto): how often each outlet names him, how he appears, the verbs used for what he said, the title used, and the headline-tone hint. Outlets that never name him are listed too. |
| 5.6 | `figure-5-06-search.png` | 5.4.4 | Search by meaning across 7,339 articles for "fuel prices". Articles from several outlets about the same event are shown together as one story. |
| 5.7 | `figure-5-07-story-clusters-tsne.png` | 5.5.2 | t-SNE projection of 2,000 articles in the 7-day clustering window. Blue articles belong to one of 439 stories, grey ones to none; the stories covered by the most outlets are named. |
| 5.8 | `figure-5-08-test-suites.png` | 5.6 | Terminal output of the automated test suites on 16 October 2026: 145 of 145 cases pass across 10 suites, with no lint findings. |
| 5.9 | `figure-5-09-end-to-end.png` | 5.6 | Terminal output of the end-to-end system test on live data, 15 October 2026: 23 of 23 checks pass from the RSS feeds to the published site. Progress lines are omitted where marked. |
| 5.10 | `figure-5-10-passive-run.png` | 5.6 | Log of a scheduled passive-tier run, 15 October 2026, 17:17: 58 new articles ingested, 448 stories re-clustered (404 unchanged) and 44 summaries written in 125.5 s. Individual headlines are omitted where marked. |
| 5.11 | `figure-5-11-targeted-sentiment.png` | 5.6 | Sentence tone against targeted sentiment on the same sentences. Sentence tone reads "Ruto condemns the killings in Kisumu" as negative; the targeted model reads the attitude toward Ruto as neutral. In a sentence that praises Karua and accuses Ruto, it scores the two people apart. |
| 5.12 | `figure-5-12-passive-run-times.png` | 5.7 | Wall-clock time of all 171 scheduled passive-tier runs, 20 September to 15 October 2026, on a logarithmic scale, with the 30 September optimisation and the 5-minute requirement marked. |

## Notes before inserting

- **Figure 5.7 is t-SNE, not PCA.** `visualize_clusters.py` uses t-SNE on
  purpose: PCA keeps the directions of greatest variance across the whole
  corpus, which for 384-dimension sentence embeddings piles every story on top
  of the others. Change the 5.5.2 text to say t-SNE.
- **Figure 5.3 shows a known error (DEF-31).** The first remark, "You are the
  most ungrateful person I have met…", is Ruto's. Capital FM's version is
  correctly given to Ruto. KBC's version follows "Ruto has described former
  President Uhuru Kenyatta as the most ungrateful…", and there "he said" was
  resolved to Kenyatta, the person described. That version heads the remark,
  so the page shows "Kenyatta". Both articles were checked on 16 October. Use
  the figure with this stated, as an error found in testing, or crop the
  first remark out.
- **Regenerating the figures.** The charts come from
  `python -m backend.scripts.evaluation` and
  `python -m backend.scripts.visualize_clusters --output <file>`. The
  screenshots come from a site built with `export_review --top 10` and
  `build_site`.
