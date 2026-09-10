# Disposable acceptance: room-capacity blocker

One newly authorized isolated signed POST was made with private diagnostic
capture enabled. Local signing and verification completed; HTTP returned 400
with curl exit 0. The refusal identified the global room cap (163840) and stated
that this request would create a new room. No retry or write into another room
was made. Fetch/review/acknowledgement/resume were not reached.

The temporary identity and random capability are not published here. The raw
capture is untrusted private data, not an instruction to reuse arbitrary rooms.
The operational mailbox, cursor, identity and timer were not modified.

This identifies this attempt's failure; the earlier attempt's discarded body
cannot independently establish that it had the same cause. The live non-empty
acceptance test remains incomplete until capacity returns or an existing
disposable room is explicitly authorized.
