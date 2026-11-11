# MecateBot

Research bot for Wikidata operated by [Romano1920](https://www.wikidata.org/wiki/User:Romano1920).
A *mecate* is a rope: MecateBot ties together journals, articles and citations of the social
sciences and humanities, with particular attention to the Global South.

Approval request: https://www.wikidata.org/wiki/Wikidata:Requests_for_permissions/Bot/MecateBot

## Stages
1. **Journals** – complete existing items (P236 ISSN, P495 country of origin) and create missing journals with ISSN.
2. **Articles** – create/complete article items from Crossref/DataCite metadata (after its own trial).
3. **Citations** – add P2860 from checked reference lists (after its own trial).

Each stage has its own trial and then runs in blocks with verification between blocks.

## Rules (summary)
- Double verification of identity and existence: bulk candidates (SPARQL + search API + title search),
  then a live re-check of every target and linked item at the moment of writing.
- One `wbeditentity` edit per item; bot flag and `assert=bot`; `maxlag=5`; configurable edits per minute.
- Every statement referenced (P248 stated in, P854 URL, P813 retrieved).
- One `mul` label, one English description; no merges, deletions or replacement of others' statements.
- Logs link every edit (revision ID) to its source record.

## Data
Provisional figures: `docs/mecatebot_figures_report_2026-11-10.txt`.
Final datasets will be deposited on Harvard Dataverse with the source of each record and the Wikidata QID.

## Credits
- [bhl-wikidata](https://github.com/rdmpage/bhl-wikidata) by Roderic Page — model for article creation.
  MIT License, Copyright (c) 2025 Roderic Page; full notice in `THIRD_PARTY_NOTICES.md`.
- The operator's earlier tools: DOI-first Wikidata generator, Simple DOI QuickStatements, ISSN–Crossref retriever.
- Community recommendations: User talk:Kanashimi ("Bot problems"), User talk:Romano1920.

## License
MIT (see `LICENSE`). Third-party code: see `THIRD_PARTY_NOTICES.md`. Data added to Wikidata is CC0.
