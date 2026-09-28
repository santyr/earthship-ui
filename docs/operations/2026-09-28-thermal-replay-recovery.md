# Thermal replay-source recovery point — September 28

This is a same-host, private observational recovery point. It does not train,
promote, publish, actuate, or establish off-host disaster recovery.

The prior replay-source bundle predated the 07:49 MDT accepted artifact and
08:20 MDT forcing capture. The new `scripts/thermal-replay-bundle.py` reads
the installed runtime's exact 21-file revision list, refuses a mismatch with
`accepted.json`, captures the importable forcing-capture verifier and private
model/capture files, and writes a no-overwrite mode-0600 archive. The verifier
checks every archived member digest, inventory and accepted source revision.
Three focused tests cover private round-trip, revision mismatch and member
tampering.

The corrected private archive is
`/home/sat/backups/earthship-energy/thermal-replay-source-20260928T150544Z.tar.gz`,
SHA-256 `6c348c17815a10d45b010f94d981791de4e44b0f239a9b4528bc0e5976687ede`.
It contains 85 members including 59 forcing captures, with accepted revision
`53d96e5e9637d9c0c427afaffa35b29350243bf295ec6ed6f8a38f631d686396`
and accepted artifact SHA-256
`a9f608d638b5e450e4d0a6f53c7b887bbfdb74290f8d21b78364a313a5fcfc8a`.
Independent extraction in a private temporary tree matched the live accepted
artifact and selected installed runtime files byte-for-byte. Using only the
extracted runtime tree, all 59 archived captures passed the v4 semantic
capture verifier. The temporary tree and superseded, same-turn archive were
removed after verification; the earlier historical bundle was retained.

This establishes an up-to-date same-host replay evidence point, not a full
whole-host restore rehearsal or an off-host copy. It does not fix the model's
24-hour skill deficit, create action confirmations, or relax the shadow gate.
An automatic schedule, retention policy and off-host destination remain open.
