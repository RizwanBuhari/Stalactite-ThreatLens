# ThreatLens: pitch kit (Team Stalactite)

Required submission (hack2skill): demo video of **3 minutes or less**, GitHub link, pitch deck PDF named
**`Stalactite_IBM Z Datathon 2026 Project.pdf`**, and links to open-source resources (in the README).

Judging (10 points each): **community value and theme fit**, **novelty**, **technical design and use of LinuxONE + AI/ML**, **execution and pitch**.

## 3-minute video script

| Time | Show on screen | Say |
|---|---|---|
| 0:00–0:20 | Brand board (`design/brand-board.png`) | "Security teams translate long threat reports into MITRE ATT&CK by hand. It's slow, it needs scarce experts, and the reports are sensitive. Pasting them into a public AI service exposes the victim's systems. We built ThreatLens: clarity without exposure." |
| 0:20–0:40 | Data slide: 4 datasets → 24,872 sentences | "We combined four public labelled datasets and 82 CISA advisories into one corpus on LinuxONE. We updated old ATT&CK IDs, and we removed answers hidden in the text, such as technique IDs and table labels, so the model can't cheat." |
| 0:40–1:40 | **Live app** at `http://localhost:8050/#/analyze`. Paste a passage containing an IP and a domain, then click Suggest techniques | "The IP and domain are masked before anything else happens. In about 60 milliseconds on LinuxONE we get three ATT&CK techniques. Each comes with the sentence that supports it and the words that drove the score, taken from the model's own weights. If I ask *Why?*, IBM Granite explains it, running locally on LinuxONE." |
| 1:40–2:10 | Click **Correct** → choose an alternative; open Review queue; Accept / Change; Save review; Export CSV | "The analyst stays in control: accept, change or reject, and add a note. Saved reviews and exports contain only the masked text." |
| 2:10–2:35 | Model evaluation page | "We report honest numbers: 81% top-3 on held-out test data, 80% after removing near-duplicates, and 59% on CISA advisories the model never saw. That gap is why ThreatLens suggests and a human decides." |
| 2:35–2:55 | Jupyter: `htop` with 3 busy Python processes during training, plus the evidence notebook showing `s390x` and `NNPA present` | "Everything runs in a container on IBM LinuxONE. We trained on all three cores, Granite runs through llama.cpp built with IBM zDNN, and the app is reachable only through an encrypted SSH tunnel to a socket, with no open ports." |
| 2:55–3:00 | Logo | "ThreatLens: powerful AI, protected data. Team Stalactite." |

**Recording tips:** record the app at 1536×960 or larger. Use `#/analyze?sample=1` for a guaranteed clean first result. Keep the video under 3:00, because the time limit is part of the score.

## Deck outline (8 slides)

1. **Title.** ThreatLens: Clarity without exposure · Team Stalactite · Theme 2: AI Secured: Innovation Without Exposure.
2. **Problem and who benefits.** Manual ATT&CK mapping is slow and needs experts, and the reports are sensitive. It helps SOC analysts, incident responders, under-resourced public bodies, hospitals and schools, and students.
3. **Solution.** Paste → mask → top-3 techniques with evidence → Granite explanation → human review → export (use `docs/screenshots/analyze.png`).
4. **Data.** 4 sources, 24,872 sentences, 497 techniques in training; leakage removal; CISA held out as a real-world test.
5. **Architecture on LinuxONE.** The mermaid diagram from the README: container, Unix socket plus SSH, predictive + generative AI, NNPA/zDNN.
6. **Results.** The Hit@3 table (80.9% / 79.7% clean / 59.2% CISA), 40 ms per sentence, plus one real hit and one real miss from the Model evaluation page.
7. **Why it matters / AI for Good.** Defenders get faster, consistent ATT&CK mapping without handing sensitive incident data to third parties. Every decision is documented and reviewable.
8. **Honesty and next steps.** Prior ICS paper disclosed; code written during the event; AI-assistant use disclosed. Next: transformer encoder on NNPA, more CISA training data, and full-report upload.

## Evidence screenshots (judges look for these)

- [ ] `htop` during training: 3 Python processes on 3 CPUs (compute)
- [ ] `podman ps` showing the `notebook` container (containerisation)
- [ ] Evidence notebook cell 1: `Architecture: s390x`, `NNPA (on-chip AI): present`
- [ ] App top bar showing "LinuxONE · s390x · Local", plus the "Private by design" card with the live LinuxONE timing
- [ ] Masked passage with `[IP]` / `[DOMAIN]` chips (security)
- [ ] Granite "Why?" explanation with "running locally on LinuxONE"
- [ ] Model evaluation page
- [ ] Both IBM labs executed: `shared/threatlens/labs/Lab1…html`, `Lab2…html`
