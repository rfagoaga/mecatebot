# Why MecateBot: a short summary of the findings
Provisional figures, November 2026 — all approximate. Full report: `mecatebot_figures_report_2026-11-10.txt`.

We are building a register of the world's social-science and humanities journals — **≈80,200 journals, with and
without ISSN** (≈70,300 with ISSN, ≈9,900 without), late 19th century to 2025. About 80 sources were consulted and
31 feed the register (119 distinct source labels once publisher and platform lists are counted separately):
national registers and union catalogues (ISSN ranges, ISSN-L table, ZDB, SUDOC, swisscovery, BNE, CCPP), directories
(DOAJ, ERIH PLUS, ROAD, Latindex, Mir@bel, Norwegian and Finnish registers), aggregators (OpenAlex, Wikidata,
JSTOR, BACON), and regional platforms (SciELO, Redalyc, Garuda, J-STAGE, DergiPark, ThaiJO, Hrčak, NepJOL,
BanglaJOL, Miguilim, OpenEdition, PKP Beacon). Everything is crossed with the Crossref Public Data File (March 2026).
Presence of the register's journals in some key infrastructures: OpenAlex ≈62,500 · Crossref ≈46,300 · library
catalogues ≈36,900 · Wikidata ≈35,800 · Open Journal Systems (PKP Beacon) ≈23,900 · DOAJ ≈11,200.
Comparing it with Wikidata shows three gaps.

**The problem in three layers** (what we learned building the register; figures approximate, "—" = not yet measured)

| Layer | Situation | Measured so far |
|---|---|---|
| **Journals** | 1. with ISSN | ≈70,300 of ≈80,200 |
| | 2. without ISSN | ≈9,900 |
| | 3. country of origin known (sources agree) | ≈62,900 |
| | 4. metadata on a platform (in Crossref) | ≈46,300 |
| | 5. articles and references open (deposit references) | ≈20,000 |
| | 6. articles open, references not | ≈26,300 |
| | 7. neither on any platform we can read | ≈24,000 ISSN journals not in Crossref (+ most without ISSN) |
| | 8. published with Open Journal Systems | — (PKP Beacon lists thousands; to be measured) |
| **Articles** | 1. research articles with DOI | ≈26.2 M works with DOI (all types) |
| | 2. book reviews with DOI | — (to be separated by visual review) |
| | 3. other DOI items (indexes, contents, author lists) | — |
| | 4. with bibliography in Crossref | ≈8.6 M (33%) |
| | 5. without bibliography in Crossref | ≈17.6 M (67%) |
| | 6. bibliography in non-standard form | see bibliographies 2, 7 |
| | 7. no bibliography at all | — |
| | 8. article not online | — |
| **Bibliographies** | 1. in Crossref / OpenAlex / open bibliographies | ≈334 M references in Crossref |
| | 2. structured for machines | ≈216 M (DOI or journal title) |
| | 3. with persistent identifiers (DOI) | ≈188 M |
| | 4. PDF with OCR and metadata | — |
| | 5. flat PDF (digitized image) | — |
| | 6. none, article not online | — |
| | 7. cited in no recognizable style | ≈68 M unstructured + ≈50 M partial (author/year only) |

Each MecateBot stage addresses one layer: journals first, then articles, then citations. Wikidata can hold
what the other infrastructures cannot: journals without ISSN, items without DOIs, and citations recovered from
bibliographies that exist nowhere else in structured form.


**1. A large share of these journals has no Wikidata item.**
Of ≈70,300 journals with an ISSN, about **30,000 (≈43%) have no item**. This was checked twice: first by SPARQL on
every ISSN, then journal by journal with the search API (ISSNs and title); only 0.1% of the "missing" journals
turned out to exist. Another ≈4,000 have only title-based candidates and will be reviewed by hand, never created
automatically.

**2. The gap is largest in the Global South.**
Share of ISSN journals verified as having no Wikidata item (journal-by-journal check, 11 Nov. 2026):
| Region | ISSN journals | No Wikidata item | In Crossref | Deposit references |
|---|---|---|---|---|
| Central Asia | 202 | 71% | 80% | 24% |
| South-eastern Asia | 11,190 | 69% | 82% | 10% |
| Africa | 2,396 | 57% | 63% | 14% |
| Southern Asia | 2,879 | 51% | 57% | 17% |
| Western Asia | 1,979 | 48% | 76% | 40% |
| Europe | 28,866 | 36% | 62% | 37% |
| Latin America and the Caribbean | 5,647 | 34% | 76% | 27% |
| Australia and New Zealand | 968 | 30% | 47% | 21% |
| Northern America | 10,957 | 30% | 58% | 32% |
| Eastern Asia | 3,439 | 28% | 61% | 24% |
| **Global South** | 24,369 | **56%** | 75% | **17%** |
| **Global North** | 44,174 | **34%** | 61% | **35%** |

Countries with the largest gaps (≥300 ISSN journals): Thailand 90%, Nigeria 77%, Indonesia 69%, Pakistan 61%,
Malaysia 60%, India 53%. Latin America is comparatively well covered (Brazil 31%, Mexico 33%, Argentina 38%),
probably thanks to earlier imports from Latindex, SciELO and Redalyc; the largest gaps are in Africa and in
Southern and South-eastern Asia. (Some European countries also have large gaps, e.g. France 56% and Germany
50%, mostly ceased titles known only from library catalogues.)

**3. Having DOIs is not the same as being visible in the citation graph.**
Journals of the Global South are *more* often in Crossref than those of the North (≈75% vs ≈61%), but only ≈17%
deposit their references, against ≈35% in the North. In Indonesia, the second country of the register by
number of journals, ≈85% of journals are in Crossref but fewer than 1 in 10 of those deposit references.
Across the register, only a third of the articles in Crossref carry reference lists.


**Easy and hard cases: the infrastructure ladder** (all ≈80,200 journals; share within each group)

| Rung | What exists | All journals | Global North | Global South |
|---|---|---|---|---|
| A | DOIs **and** deposited references (full, machine-readable infrastructure) | 19,975 (25%) | 35% | 17% |
| B | DOIs but **no** references (infrastructure exists but is empty) | 26,278 (33%) | 26% | **57%** |
| C | indexed or hosted somewhere (OpenAlex, DOAJ, OJS, regional platform), no DOIs | 23,307 (29%) | 22% | 23% |
| D | known only from library catalogues and registers | 10,654 (13%) | 18%* | 3% |

\* mostly ceased titles known from European catalogues. For rung A our work is simple: identifiers and
references already exist. Rung B is the signature of the Global South: the journals paid for DOIs, but their
bibliographies never reached the citation graph. Rungs C and D need reconciliation with platforms, catalogues and
authority files before anything can be added. Other barriers we met but did not measure: websites without the
metadata tags that Google Scholar and harvesters need, OAI-PMH endpoints that answer empty, bot walls, and PDFs
without text layer. (OpenAlex: harvesting it at scale now costs money — an API key and paid usage beyond a small daily
allowance — so we measured it on anthropology only: there it held references for 39% of articles versus 31% in
Crossref, and it recovered about a third of a sample of articles that had no references in Crossref. Useful, but
not a substitute for the journals' own bibliographies.)

**Expected scale of the links in Wikidata** (orders of magnitude, upper bounds, to be refined stage by stage)
- Journals: ≈80,000 linked through QIDs (≈36,000 existing, ≈2,150 completed, ≈30,000 created; ≈9,900 without
  ISSN need authority work first).
- Articles: up to ≈26 million with DOIs (how many already exist will be measured first), plus articles without DOIs
  on OJS and regional platforms (not yet counted).
- Citations: ≈185 million references whose cited DOI resolves in Crossref (the "easy" layer) and ≈146 million that
  are journal-title only, unstructured or partial (the "hard" layer: many must be matched against library
  catalogues, searched by hand or parsed from bibliographies before they can be compared with Wikidata).

**Subjects.** Wikidata has ≈121,600 items for scientific or academic journals (all fields), but only ≈24,300 (20%)
say what the journal is about (main subject, P921). Our register records, for each journal, the subject or
discipline that its sources assign (directories, national registers, library classifications, platform areas).
MecateBot will add P921 only from that evidence, with the source as reference — not from title keywords or
guesses.

**Behind the bot.** MecateBot only writes the last step. Before it, each journal, article and cited work has to be
identified across platforms, library catalogues and authority files, and cited works have to be found and
described precisely enough to be matched with Wikidata. That reconciliation is the slow, skilled part of the
project, and it is what the published Dataverse datasets will document.

**What MecateBot will do about it** (in stages, each with its own trial and review):
1. **Journals:** complete ≈2,150 existing items (missing ISSN or country) and create the ≈30,000 verified
   missing journals, with a referenced source for every statement.
2. **Articles:** add articles of those journals, after measuring which already exist, with a visual review of
   document types (articles vs reviews, notes, editorials).
3. **Citations:** add "cites work" only from checked reference lists, starting with journals whose citations
   are absent from the open citation graph.

The resulting datasets will be published on Harvard Dataverse with the source of every record and its
Wikidata QID, so that others do not have to repeat the reconciliation.

*Caveats: the register is still under review; article and citation figures count only what publishers
deposited in Crossref, which under-represents precisely the journals we focus on; regional figures come from the journal-by-journal check (journals without an assigned country, ≈1,700 with ISSN, are not in the regional table); "Global North" here =
Northern America, Europe, Australia/New Zealand, Japan, South Korea, Israel, Taiwan, Singapore, Hong Kong.*
