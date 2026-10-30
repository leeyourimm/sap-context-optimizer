# Public ABAP export provenance

These are unmodified bytes downloaded over HTTPS at the exact Git commits in
manifest.json. Git blob SHA-1 was checked against each upstream tree; SHA-256 and
byte counts are recorded for offline CI verification. No ABAP is executed and no
source is sent to Claude or another model during this evaluation.

- SAP-samples/abap-platform-rap100 — Apache-2.0; copyright 2024 SAP SE or an SAP
  affiliate company and abap-platform-rap110 contributors, as stated in the
  preserved upstream REUSE.toml. LICENSE and LICENSES/Apache-2.0.txt are included.
  Upstream's External Products/API Calls limitations in REUSE.toml are preserved;
  this fixture grants no access or license to an SAP backend.
- abapGit-tests/CLAS, INTF, FUGR, PROG — MIT; upstream copyright notices and
  license texts are preserved in each repository's LICENSE file.

The selected upstream src directories are complete at their pinned commits;
dependencies outside those directories/repositories are deliberately not invented.
Missing /DMO and SAP standard objects are snapshot gaps, not proof of absence.
cases.json is authored here: expected source ranges were read from these pinned
files independently of the optimizer's parser/output. This is a small development
regression corpus, not a held-out SAP answer accuracy benchmark.
