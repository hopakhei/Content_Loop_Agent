# Article source texts (Loop 3 input)

Drop each Substack long-form article's **full text** here as `<issue>.md` (or `.txt`),
named by its Issue #:

```
articles/101.md
articles/102.md
…
articles/107.md
```

Then fission them into Notion Content Drafts:

```bash
# one article
python main.py --loop 3 --issue 102 --article-file articles/102.md [--dry-run]

# every articles/<issue>.(md|txt) in one go
python main.py --loop 3 --all [--dry-run]
```

Each run sends the text through `prompts/generate.txt` (Hook framework baked in),
parses the 12 units, and writes drafts related to the matching **Article Library**
entry — inheriting that article's **CTA URL**. So before fissioning, make sure the
article's `CTA URL` (Substack link with your referral param) is filled in the
Article Library, or the generated CTAs will have no link.

`--dry-run` prints what would be created without writing to Notion.
