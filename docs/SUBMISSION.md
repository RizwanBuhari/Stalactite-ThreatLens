# hack2skill submission answers (Team Stalactite)

Each answer is under the form's 1,024-character limit (checked by script). Copy the text inside each block.

## Challenges
AI Secured: Innovation Without Exposure

## What is the Problem you are trying to solve?
```
Security teams must translate long cyber threat reports into MITRE ATT&CK techniques (e.g. "dumped credentials from LSASS memory" = T1003.001) to build detections and find gaps in their defences. Done by hand, this is slow and inconsistent, and it needs scarce experts, so many under-resourced teams (public bodies, hospitals, schools, NGOs) skip it. AI chatbots could help, but threat and incident reports are sensitive: they name the victim's servers, accounts, IP addresses and weaknesses. Pasting them into an external AI service exposes exactly what an attacker wants and often breaks confidentiality rules. Teams need AI-assisted ATT&CK mapping that keeps the data private and keeps a human accountable for every decision.
```

## How are you planning to solve the problem? (Brief Overview)
```
ThreatLens is a private web app running entirely on IBM LinuxONE. An analyst pastes a report passage. 1) IPs, domains, URLs, emails, hashes and user names are masked first; only masked text is ever stored. 2) A classifier (TF-IDF word + character n-grams, one-vs-rest logistic regression in scikit-learn) ranks the most likely MITRE ATT&CK Enterprise techniques for each sentence in ~60 ms. It shows the supporting sentence and the words that drove each score, taken from the model's own weights. 3) On request, IBM Granite 4.0 (350M, llama.cpp) writes a short explanation, generated on the server. 4) The analyst accepts, corrects or rejects each suggestion, adds a note and exports CSV/JSON. We built a 24,872-sentence corpus from AnnoCTR, TRAM, Procedure+, Expert and 82 CISA advisories, remapped old ATT&CK IDs and removed label leakage. Results: 80.9% top-3 hit rate on test; 59.2% on CISA advisories never used for training.
```

## How does your solution leverage IBM Z / LinuxONE technologies?
```
Everything runs in a Podman container on our IBM LinuxONE Community Cloud server (s390x). That covers the data pipeline (82 CISA PDFs and 4 datasets processed in ~50 s), training (3 candidate models in parallel on all CPUs; final model in 147 s), evaluation, and live inference (40 ms per sentence, ~2,265 sentences/s in batch). The generative step uses IBM Granite through llama.cpp built with the IBM zDNN backend; the server provides the NNPA on-chip AI accelerator (our classifier itself runs on the CPU). Security: the app listens on a Unix socket inside the container, not a network port, and is reached only through key-based, encrypted SSH tunnels. No report text leaves the server and only masked text is stored. This is why LinuxONE fits: sensitive security data stays on isolated, enterprise-grade infrastructure while still getting AI assistance. We also completed both IBM labs (hybrid multi-model; predictive + generative AI) on this server.
```

## What value does your solution deliver, and who will benefit from it?
```
Who benefits: security operations (SOC) analysts, incident responders and threat-intelligence teams, especially small or under-resourced defenders in the public sector, healthcare, education and NGOs, plus cybersecurity students learning ATT&CK. Value: faster, more consistent mapping of reports to ATT&CK, which feeds detection rules, threat hunting and gap analysis. Every suggestion comes with its evidence and a documented human decision (accept, correct or reject, plus a note), giving an auditable record. Sensitive incident data never goes to a third-party AI service, so teams that cannot use public chatbots can still use AI. Expected outcome: on held-out data the right technique is in the top 3 for about 4 in 5 sentences, so analysts confirm a shortlist instead of searching ~700 techniques. On unfamiliar CISA reports it is about 3 in 5, which is why a human always makes the final call.
```

## GitHub link
```
https://github.com/RizwanBuhari/Stalactite-ThreatLens
```

## Link to all open-source resources used
```
Full list: https://github.com/RizwanBuhari/Stalactite-ThreatLens#open-source-resources-used | scikit-learn https://scikit-learn.org | NumPy https://numpy.org | SciPy https://scipy.org | pandas https://pandas.pydata.org | joblib https://joblib.readthedocs.io | pypdf https://github.com/py-pdf/pypdf | llama.cpp https://github.com/ggml-org/llama.cpp | llama-cpp-python https://github.com/abetlen/llama-cpp-python | IBM zDNN https://github.com/IBM/zDNN | IBM Granite https://huggingface.co/ibm-granite | JupyterLab https://jupyter.org | AnnoCTR https://github.com/boschresearch/anno-ctr-lrec-coling-2024 | TTP mapping datasets https://github.com/tumeteor/mitre-ttp-mapping | CISA advisories https://www.cisa.gov/news-events/cybersecurity-advisories | MITRE ATT&CK https://github.com/mitre-attack/attack-stix-data
```

## Any other document (architecture diagram)
```
https://github.com/RizwanBuhari/Stalactite-ThreatLens/blob/main/submission/ThreatLens_Architecture.pdf
```

## Still to provide
- **Pitch deck PDF** (upload, 5 MB maximum): `Stalactite_IBM Z Datathon 2026 Project.pdf`
- **Video link**: YouTube or Vimeo, 3 minutes or less, set to Public or Unlisted (720p/1080p MP4)
