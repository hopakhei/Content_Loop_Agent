# Audience log

`ig_comments.jsonl` — every Instagram comment the DM loop sees, appended one
JSON object per line and committed by `instagram-dm.yml`. Written before the
keyword gate on purpose: the comments that *don't* ask for the link are the ones
worth reading, and they were exactly the ones being dropped.

Append-only. Do not rewrite or prune it.

This is a hypothesis source, not evidence. A reader saying they wanted something
tells you what to test; it does not tell you it would have reached more people.
Only a randomised run on our own account closes a card — see
`research/hypotheses/`.
