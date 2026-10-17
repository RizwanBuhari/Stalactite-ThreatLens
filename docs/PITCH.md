# ThreatLens: pitch kit (Team Stalactite)

Required submission (hack2skill): demo video of **3 minutes or less**, GitHub link, pitch deck PDF named
**`Stalactite_IBM Z Datathon 2026 Project.pdf`**, and links to open-source resources (in the README).

Judging (10 points each): **community value and theme fit**, **novelty**, **technical design and use of LinuxONE + AI/ML**, **execution and pitch**.

## 3-minute video script

| Time | Show on screen | Say |
|---|---|---|
| 0:00–0:20 | Brand board (`design/brand-board.png`) | "Security teams translate long threat reports into MITRE ATT&CK by hand. It's slow, it needs scarce experts, and the reports are sensitive. Pasting them into a public AI service exposes the victim's systems. We built ThreatLens: clarity without exposure." |
| 0:20–0:40 | Data slide: 4 datasets → 24,872 sentences | "We combined four public labelled datasets and 82 CISA advisories into one corpus on LinuxONE. We updated old ATT&CK IDs, and we removed answers hidden in the text, such as technique IDs and table labels, so the model can't cheat." |
| 0:40–1:40 | **Live app** at `http://localhost:8050/#/analyze`. Paste a passage containing an IP and a domain, then click Suggest techniques | "The IP and domain are masked before anything else happens. In about 60 milliseconds on LinuxONE we get three ATT&CK techniques. Each comes with the sentence that supports it and the words that drove the score, taken from the model's own weights. If I click *AI explanation*, IBM Granite explains it, generated on LinuxONE." |
| 1:40–2:10 | Click **Correct** → choose an alternative; open Review queue; Accept / Change; Save review; Export CSV | "The analyst stays in control: accept, change or reject, and add a note. Saved reviews and exports contain only the masked text." |
| 2:10–2:35 | Model evaluation page | "We report honest numbers: 81% top-3 on held-out test data, 80% on a low-overlap subset, and 59% on CISA advisories the model never saw. That gap is why ThreatLens suggests and a human decides." |
| 2:35–2:55 | Jupyter: `htop` with 3 busy Python processes during training, plus the evidence notebook showing `s390x` and `NNPA present` | "Everything runs in a container on IBM LinuxONE. We trained on all three cores, Granite runs through llama.cpp built with IBM zDNN, and the app is reachable only through an encrypted SSH tunnel to a socket, with no additional ports opened." |
| 2:55–3:00 | Logo | "ThreatLens: powerful AI, protected data. Team Stalactite." |

**Recording tips:** record the app at 1536×960 or larger. Use `#/analyze?sample=1` for a guaranteed clean first result (it includes an IP and a domain to show masking). Keep the video under 3:00, because the time limit is part of the score.

## Deck (14 slides: `submission/Stalactite_IBM Z Datathon 2026 Project.pdf`)

1. Cover: ThreatLens, MAHE Dubai, Team Stalactite
2. Problem: specialist work, consistency, disclosure risk
3. Who benefits: evidence-backed mapping assistance
4. Solution: paste, mask, rank, review, optionally explain
5. Close-up: one ranked technique with visible evidence and a Granite explanation
6. Close-up: an analyst refines a mapping and saves the review
7. Data: 24,872 sentences; CISA kept for external evaluation
8. Architecture: one server, one container, no external AI calls
9. LinuxONE: built, trained and served on s390x, with platform evidence
10. Results: baseline evaluation; evaluated vs served model
11. Privacy, honesty, originality and known limits
12. Next steps, closing statement, team, GitHub QR code
13. Appendix A: references
14. Appendix B: detailed architecture

For the 3-minute video, spend most of the time on slides 5, 6, 8 and 10.

## Evidence screenshots (judges look for these)

- [ ] `htop` during training: 3 Python processes on 3 CPUs (compute)
- [ ] `podman ps` showing the `notebook` container (containerisation)
- [ ] Evidence notebook cell 1: `Architecture: s390x`, `NNPA (on-chip AI): present`
- [ ] App top bar showing "LinuxONE · s390x · Local", plus the "Private by design" card with the live LinuxONE timing
- [ ] Masked passage with `[IP]` / `[DOMAIN]` chips (security)
- [ ] Granite "AI explanation" box ("generated on LinuxONE")
- [ ] Model evaluation page
- [ ] Both IBM labs executed: `shared/threatlens/labs/Lab1…html`, `Lab2…html`
