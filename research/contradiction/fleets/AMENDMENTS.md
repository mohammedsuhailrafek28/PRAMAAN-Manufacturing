# Fleet amendments (Experiment B)

Fleets and their authored ground truth were first committed at `e641285`, before any detector (B0 or B1) existed.

## AM-1 (before any detector result existed): B15 truth omitted the lot-identity conflict

While specifying the lot-identity rule I noticed that B15 (serial SN-1015 recorded as lot BR-204 by one motor and BR-310 by another,
supplier missing on one claim) had a truth entry for the overlap only. If the two claims are the same bearing, the lot disagreement is
a second contradiction on the same claims, exactly as in B10. `B15-C2` (INSUFFICIENT, LOT_IDENTITY) was added to the truth. The
sensitivity truth for B15 was already written assuming both effects and is unchanged.
