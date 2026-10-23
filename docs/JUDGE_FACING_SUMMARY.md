# What this demo shows, and what it does not

PRAMAAN Manufacturing is a **local, loopback-only prototype running on synthetic data**. It is not production-ready and has not passed independent safety certification (its checkpoint safety layer, "H1/H2", is our own design and has been reviewed by us, not certified).

| Thing on screen | What it is | What it is NOT |
|---|---|---|
| **Synthetic, locally recorded evidence** | Events written to a local append-only ledger from made-up EPCIS-style documents. Each is hash-chained to its original document. | Not real supplier or factory data, not independently witnessed, not proof of physical truth. |
| **Evaluator findings and recall holds** | Output of our pinned recall evaluator (v3, unchanged) over that recorded evidence: Affected / Unresolved / Excluded-with-evidence, and a hold or release action per motor. Holds are conservative: missing or ambiguous evidence stays held. | Not a quality release or safety certificate. "Release eligible" means only "the recorded evidence does not tie this motor to the recalled lot", and only while the checkpoint is current. |
| **Locally accepted checkpoint custody** | A checkpoint is a recorded snapshot (hashes and counts) of the ledger's history, kept in a file outside the database. When a new capture arrives, the screen drops to **Checkpoint required / Do not ship or release** until an operator proposes, accepts (typed digest, named person) and restarts with a successor checkpoint. | Acceptance happens on the same machine, asserted by whoever runs it. It is **not independent custody**: someone who controls the host controls the checkpoint. |
| **Genuine independent custody** | **Not demonstrated.** It would need a separately held, separately controlled copy of the latest checkpoint (and a way to detect two competing versions). | Not claimed. |
| **Recorded shipment claims vs confirmed delivery** | The ledger records that a shipment event was *claimed* (shipment id, time). A recorded claim does not confirm delivery, receipt, or that the goods are what the claim says. | We never present a shipment record as delivery confirmation or as release authorization. |

Known limitations we state up front: one recall scope per database; at 100 motors / 1000 journal entries the app returns a safe "verifying" refusal instead of answers; a forged first publication at an old watermark by someone with write access to the journal is documented but not cryptographically prevented; two competing checkpoint histories cannot be detected without a new custody design.
