# Data sources

One row per source. Original files are never edited. Exclusions are recorded here or in a manifest, never made by deleting files.

| Source | Where in project | Origin | Version / date | Licence | Collected by | Use |
|---|---|---|---|---|---|---|
| AnnoCTR (Bosch, LREC-COLING 2024) | `data/raw/annoctr/` | https://github.com/boschresearch/anno-ctr-lrec-coling-2024 (paper: https://arxiv.org/abs/2404.07765) | repo `main`, downloaded 17 Oct 2026 | CC BY-SA 4.0 (`LICENSE.txt`) | Rijun | Training, validation and test (official report-level splits in `splits.tsv`) |
| MITRE ATT&CK Enterprise (STIX 2.0) | `data/reference/mitre/enterprise-attack.json` | MITRE ATT&CK Enterprise STIX 2.0 bundle, format of https://github.com/mitre/cti (the file records no release number) | snapshot: bundle--fc207382-c9d1-4ece-bce2-6ef555c62d0a, ATT&CK spec 3.3.0, newest object 2026-10-13, SHA-256 66f3fe3f07ef1a2de0bd2fe4b3e8a9ea06c1d0bb2c46171bdbb57c7f7b666524; 706 active techniques | MITRE ATT&CK Terms of Use (attribution) | Rijun | Reference only: names, descriptions, tactics, revoked/deprecated checks |
| CISA cybersecurity advisories | `data/raw/cisa/pdf/` + `data/raw/cisa/manifest.csv` | https://www.cisa.gov/news-events/cybersecurity-advisories (per-file URLs in `manifest.csv`, derived from each advisory ID; report dates not yet recorded) | 2020–2025 | US Government work (public domain); joint advisories credit co-authors | Amar | External test set and demo passages only, never training |
| TRAM, Procedures, Derived Procedures, Expert (Nguyen et al., EACL 2024, "Security TTP Mapping") | `data/raw/ttpm/` | https://github.com/tumeteor/mitre-ttp-mapping (paper: https://aclanthology.org/2024.findings-eacl.25) | labels remapped by the authors to ATT&CK v12.0; downloaded 17 Oct 2026 | README text says CC BY 4.0, its badge says CC BY-NC-SA 4.0 (non-commercial use either way) | Shabnam | Training, validation and test (authors' own splits) |

## Notes

- **AnnoCTR subset copied:** `text/`, `linking_mitre_only/`, `entities/`, `splits.tsv`, README, licence and annotation guidelines. NER, temporal and Wikipedia-linking layers were not needed. The repo download also contained `process_reports.py` and `dataset_10k_processed.csv`, which are not part of the official release, so they were left out.
- **CISA manifest:** 120 PDFs. 86 `use`, 30 `demo_only` (no ATT&CK IDs in the text), 4 `exclude` (3 Spanish translations, 1 ICS notice). Files sharing an advisory ID are versions of the same advisory and must stay in one split group. D28 and D34 still need advisory IDs.
