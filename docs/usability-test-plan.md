# Usability and acceptance test plan

**Status: planned. No sessions have been run, so there are no results yet.** Fill in
the sheets in Section 6 during the sessions and report only what was observed.

## 1. Purpose

The technical tests show that Newseye computes its comparisons correctly. This
test asks whether its intended users can use them. Three questions:

1. Can a reader find what each outlet reported, quickly and without help?
2. Do readers read the comparison as intended? A dash means the outlet did not
   carry the fact, an outlet left out of the table could not be opened (it did
   not omit anything), and the tone label is a hint, not a verdict (NFR-04).
3. Would they use it? This is measured with the System Usability Scale.

## 2. Participants and ethics

- **Number:** 5 to 8 participants. Five users typically find most usability
  problems in a design, and each extra session finds fewer new ones.
- **Who:** adults who read Kenyan news online at least weekly, for example
  students and staff. Exclude anyone who worked on the project.
- **Consent:** obtain informed consent before each session. Record no names:
  participants are P1, P2 and so on. Collect only an age band and how often they
  read news. Check whether Strathmore requires ethics approval for testing with
  students before the first session.

## 3. Set-up

- **The site:** the single-file site (`dist/newseye.html`, built with
  `python -m backend.scripts.single_file`), opened on the participant's own
  phone or laptop with an internet connection.
- **Procedure:** participants think aloud. The observer times each task and
  notes errors and any help given. The observer does not explain the interface
  during a task.
- **Choose the stories in advance:** fix the stories and facts used in each task
  before the first session, from the demonstration site, and write them in
  Section 4. Every participant gets the same tasks.

## 4. Tasks and success criteria (fixed before testing)

| Task | Instruction to the participant | Success means | Traces to |
|---|---|---|---|
| T1 | "Find the story about ______. Which outlets covered it?" | Names every outlet listed on the page, within 2 minutes | FR-09 |
| T2 | "Which outlet did not report that ______?" | Names the outlet with a dash for that fact | FR-04 |
| T3 | "What figure did ______ give for ______, and what was it counting?" | Gives the figure and reads its context correctly | FR-06 |
| T4 | "Did two outlets quote ______ differently? How?" | Finds the remark and says which version is shorter or reworded | FR-05 |
| T5 | "Open ______'s page. Which outlet never names them?" | Names an outlet listed as never naming them | FR-07 |
| T6 | "Search, in your own words, for a news topic you care about, and open its comparison." | Reaches a story page from the search | FR-10 |
| C1 | "______ covered this story but is not in the table. Did it leave these facts out?" | No: its article could not be opened, so nothing is known about what it reported | NFR-04 |
| C2 | "Does this tone label tell you an outlet is biased?" | No: it is a hint that can be wrong, and the headlines are the evidence | NFR-04 |

## 5. Measures and acceptance criteria

| Measure | How | Acceptance |
|---|---|---|
| Task success | Success or failure per task, as defined above | At least 80% of all task attempts succeed |
| Time on task | Seconds from the end of the instruction to the answer | Reported as a median; no threshold |
| Comprehension | C1 and C2 answered as intended | At least 80% of answers |
| Satisfaction | SUS questionnaire (Section 7), 0 to 100 | Mean of at least 68, the commonly cited average |

Report every task, including failed ones. A pattern of failures is a design
defect: give it a defect ID in the corrections log, fix it, and retest.

## 6. Recording sheets

**Session record:**

| Participant | Age band | Reads news | Device | T1 | T2 | T3 | T4 | T5 | T6 | C1 | C2 | SUS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | | | | | | | | | | | | |
| P2 | | | | | | | | | | | | |
| P3 | | | | | | | | | | | | |
| P4 | | | | | | | | | | | | |
| P5 | | | | | | | | | | | | |

Mark each task ✓ or ✗ with its time, for example "✓ 45 s". Note any help
given, for example "✗ helped".

**Observations:** for each problem seen, record the participant, the task, what
happened, how severe it was (cosmetic, minor or major), and the fix you propose.

## 7. System Usability Scale

The participant rates each statement from 1 (strongly disagree) to 5 (strongly
agree), straight after the tasks.

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

**Scoring:** for odd-numbered items, subtract 1 from the score. For
even-numbered items, subtract the score from 5. Add the ten results and
multiply by 2.5. This gives a score from 0 to 100 (Brooke, 1996).

Two closing questions:

- What would make you use this instead of reading a single outlet?
- What, if anything, did you find misleading?
