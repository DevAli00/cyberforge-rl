# W1 research: how real ransomware intrusions progress

Goal: check the attack model in `docs/w01-spec.md` §4.2–4.3 against public data, and propose numbers that match it.
Scope: attack progression only. Alert noise (false-alarm rates, alert mix, severities) is covered in a separate note.
Date: 2026-10-18. Time box: about 45 minutes, so this is a first pass, not a literature review.

Source types used below:

- **Incident data**: numbers measured from real investigations (incident response or managed detection cases).
- **Survey**: people answering a questionnaire.
- **Vendor marketing**: claims without a clear dataset. None of the numbers below rely on this type.

"Secondary" means a news article that repeats the report's number; we could not open the report itself.

## Summary

- **The stage order is right.** Real ransomware intrusions go: get in → create accounts / grab admin rights → scan and move to other machines → encrypt. This matches MITRE ATT&CK and a 2025 US government (CISA) advisory, step by step.
- **Stage 1 misses the biggest entry points.** For ransomware, the top ways in are password guessing (brute force, 26%), stolen passwords (21%) and exploiting an internet-facing device such as a VPN (21%). Phishing is small (6–7% or less in the newest incident data). We already have a `failed_login_burst` alert type; making it a stage-1 alert closes most of the gap without changing the interface.
- **p_advance = 0.6 is fine, if one turn means about half a day.** Real data puts the time from getting in to ransomware at roughly 17 hours to 5 days. With p = 0.6, an attack needs a median of 5 turns, so 1 turn ≈ 3–24 hours. We propose **1 turn ≈ 12 hours**, so a 10-turn shift ≈ a 5-day work week. If a turn must be 1 hour, p_advance would have to drop to about 0.13–0.18, and very few attacks would reach ransomware in a shift.
- **"Ransomware is detected too late" is backed.** In ransomware cases, the attacker told the victim (ransom note) 49% of the time in 2024 and 44% in 2025 (Mandiant). But defenders are getting better: about half of attacks are now stopped before encryption (Sophos survey, Microsoft).
- **Two numbers have no public data:** 2–4 attacks per shift, and the 20/30/50% target split. Keep them as game choices and say so. The direction of the target split (attackers go for domain controllers, file and backup servers) is backed, but the first machine they touch is usually an edge device or an ordinary one.

## Model vs. evidence

| Model number (spec) | Our value | What the evidence says | Source(s) | Verdict | Proposed value |
|---|---|---|---|---|---|
| Attacks per shift (§4.2) | 2, 3 or 4 | No public data on how many intrusions one SOC handles at the same time. The only related evidence is case studies of 2–3 ransomware gangs hitting the same network within days or weeks. | [S17] | Our assumption | Keep 2–4. Say in the spec it is a training dial, not a measured rate. |
| Start turn (§4.2) | Uniform, turn 1–6 | No public data. Attackers launch ransomware outside business hours 83–88% of the time, but that is about deployment, not about when the intrusion starts. | [S1] §"Games without frontiers", [S2] | Our assumption | Keep. |
| Speed `p_advance` (§4.2) | 0.6 per turn → median 5 turns from stage 1 to 4 | Getting in → ransomware: median under 1 day (2022–23), average about 17 h (2024). Ransomware dwell time: 3 days (MDR) and 4 days (IR) in 2024. Dwell time when the attacker announced themselves: 5 days (2024). | [S9], [S10], [S1] §"We're one (but we're not the same)", [S3] p.2 | Backed, **if** 1 turn ≈ 3–24 h. Contradicted if 1 turn = 1 h. | Keep 0.6 and define **1 turn ≈ 12 h** (see "What one turn means"). |
| Speed is the same at every stage (§4.2) | Same 0.6 for 1→2, 2→3, 3→4 | Early steps are fast: first move to another machine in 48 min on average (2024); first attempt on Active Directory after a median 11 h (2024) and 3.4 h (2025). The last step is slower: data theft comes first, at a median of about 73–79 h, then encryption. | [S11], [S1] §"No time to waste", [S2], [S1] §"Other findings" | Contradicted (mildly) | W1: keep one value. W2 idea: faster early stages, slower 3→4. |
| Stage order (§4.2) | 1 gets in → 2 settles in → 3 spreads → 4 ransomware | Matches the ATT&CK tactic order (Initial Access → Persistence / Privilege Escalation → Discovery / Lateral Movement → Impact). The CISA Akira advisory and two DFIR Report cases follow the same order. Real cases add a data-theft step before encryption. | [S18], [S12], [S13], [S14] | Backed | Keep. Data theft could be a W2 stage. |
| Stage-1 alert types (§4.3) | `phishing_link_clicked`, `off_hours_login`, 50/50 | Ransomware entry points (2024): brute force 26%, stolen credentials 21%, exploit 21%, prior compromise 15%, third party 10%. Phishing is not in the top five. All intrusions: exploits are #1 (33% in 2024, 32% in 2025); email phishing fell from 14% to 6%. Sophos 2026 report (2025 cases, all types): compromised credentials 42%, exploited vulnerability 16%, brute force 16%, phishing 6%. Verizon: credential abuse 22%, exploits 20%, phishing 16% (2025 report); exploits 31% and #1 (2026 report). | [S5], [S3] p.2, [S6] p.3, [S2], [S7], [S8] | Contradicted: phishing is overweighted, brute force and exploits are missing | Stage 1 = `failed_login_burst` 0.48, `off_hours_login` 0.39, `phishing_link_clicked` 0.13 (math below). W2: add an exploit-on-edge-device alert. |
| Stage-2 alert: `new_admin_account` (§4.3) | Stage 2 | Akira actors create new domain accounts and add users to admin groups (T1136.001/.002). In the Lynx case, look-alike admin accounts were created in the first hour. Sophos names account creation among the common techniques but gives no percentage. | [S12], [S13], [S1] §"You down with TTP?" | Backed | Keep. |
| Stage-2 alert: `cloud_key_new_asn` (§4.3) | Stage 2 | No public source found that ties a cloud key used from a new network to ransomware intrusions. Mandiant 2026 stresses identity and SaaS / cloud abuse in general, not for ransomware. | [S6] p.4 | Our assumption | Keep for W1 (it is a "good clue" type). Revisit if W2 models cloud. |
| Stage-3 alert: `internal_port_scan` (§4.3) | Stage 3 | Network scanners (Advanced IP Scanner, SoftPerfect NetScan, T1046) appear in the CISA Akira advisory and in both DFIR cases. But most spreading uses RDP with stolen passwords (RDP used inside the network in 83% of 2024 Sophos cases), so a scan is one sign among several. | [S12], [S13], [S14], [S1] §"The main event" | Backed | Keep. |
| Stage-4 alert: `mass_file_rename` (§4.3) | Stage 4 | Encryption is ATT&CK T1486 (Data Encrypted for Impact), the final step in every case above. | [S18], [S12] | Backed | Keep. |
| Target importance (§4.2) | 1: 20%, 2: 30%, 3: 50% | No public percentage split. Direction is backed for later stages: attackers reach Active Directory fast (median 11 h → 3.4 h), and ransomware runs on file and backup servers (both DFIR cases); recent attacks also go after backups and virtualization hosts. But the **first** machine is usually an internet-facing service or an unmanaged device: remote services in 71% of Sophos 2024 cases; unmanaged devices in more than 90% of Microsoft cases that reached the ransom stage. | [S1] §"Come together", §"No time to waste", [S2], [S13], [S14], [S6] p.5, [S15] | Direction roughly backed; numbers are our assumption | Keep 20/30/50 for W1. W2 idea: importance depends on stage (stage 1 on ordinary machines, stages 2–4 on important ones). |
| Ransomware detected late (§4.3 "always too late") | `mass_file_rename` is reliable but late | In ransomware cases, the attacker told the victim 49% of the time (2024) and 44% (2025); the victim found it internally 30% (2024) and 41% (2025). Survey: data was encrypted in 49% of enterprise attacks; 47% were stopped before encryption (up from 22% in 2023). Microsoft: share of attacks reaching encryption fell threefold over two years. | [S3] p.2, [S6] p.3, [S16], [S15] | Backed (but the trend is toward earlier detection) | Keep. |

### Stage-1 weights: the math

We only have three alert types that can stand for a stage-1 entry. We map each real entry point to one of them, using Mandiant's 2024 numbers for ransomware cases [S5]:

| Real entry point | Share of ransomware cases | Our alert type |
|---|---|---|
| Brute force (password spraying, many RDP logins) | 26% | `failed_login_burst` |
| Stolen credentials (attacker logs in with a real account) | 21% | `off_hours_login` |
| Phishing | not in the top five, so at most 7% (100 − 26 − 21 − 21 − 15 − 10 = 7) | `phishing_link_clicked` |
| Exploit, prior compromise, third party | 21 + 15 + 10 = 46% | none |

Rescale the three we can represent so they sum to 1: total = 26 + 21 + 7 = 54.

- `failed_login_burst` = 26 / 54 ≈ **0.48**
- `off_hours_login` = 21 / 54 ≈ **0.39**
- `phishing_link_clicked` = 7 / 54 ≈ **0.13** (an upper bound, so phishing is, if anything, still overweighted)

Notes:

- `failed_login_burst` is already in the catalogue and is noisy (noise_freq 0.12), so the design rule "early alert types stay noisy" still holds. The number of alert types (12) and the observation layout in §5 do not change.
- About 46% of real ransomware entries have no matching alert type. A stricter "match the data" option is to make 46% of attacks enter stage 1 **silently** (no alert). Mandiant 2026 supports this in part: edge devices "typically lack standard telemetry" [S6] p.2. This makes the game harder, so it is Ali's call; we do not recommend it for W1.

## What one turn means

**Key fact.** An attack must advance 3 times (1→2, 2→3, 3→4). Each turn it advances with probability p. On average that takes 3 / p turns. With p = 0.6: 3 / 0.6 = **5 turns**. The median is also 5 turns (we checked by summing the probabilities), and about 68% of attacks finish within 5 turns.

So: **real time from getting in to ransomware = 5 × (length of one turn).** Turn length = real time ÷ 5.

| Source | Real time, getting in → ransomware | One turn (= real time ÷ 5) |
|---|---|---|
| Huntress 2025 report (2024 data) [S10] | about 17 h (average, not median) | about 3.4 h |
| Secureworks 2023 (Jun 2022 – Jul 2023) [S9] | median under 1 day (24 h) | under 4.8 h |
| Sophos 2025, ransomware dwell time, MDR (2024) [S1] | median 3 days (72 h) | about 14.4 h |
| Sophos 2025, ransomware dwell time, IR (2024) [S1] | median 4 days (96 h) | about 19.2 h |
| Mandiant 2025, dwell time when the attacker announced themselves (2024) [S3] | median 5 days (120 h) | 24 h |

Caveats: these sources measure slightly different things. Secureworks and Huntress measure the time to ransomware directly. Sophos and Mandiant measure "dwell time" (start of attack to detection); for ransomware, detection usually happens at or after encryption, so it is a fair stand-in, but not the same thing. Populations differ too (Huntress and Sophos are mostly small and mid-size firms).

Trend: the 2023 Secureworks report said the median fell from 4.5 days to under 1 day in a year. Since then, time to Active Directory dropped further (11 h → 3.4 h, Sophos 2025 → 2026) and the "hand-off" from the first intruder to the ransomware group fell from more than 8 h (2022) to 22 seconds (2025) [S6] p.5. Overall dwell time went up (11 → 14 days, Mandiant), but that rise is driven by spies and fake IT workers, not ransomware [S6] p.2.

**Proposal: keep p_advance = 0.6 and say 1 turn ≈ 12 hours.**

- The five values above run from about 3 h to 24 h per turn. Their middle value is 14.4 h. A round 12 h sits in the middle of the evidence.
- Then 5 turns ≈ 60 h ≈ 2.5 days from getting in to ransomware, between the fast (17–24 h) and slow (3–5 days) sources.
- A 10-turn shift ≈ 120 h = 5 days, roughly one work week. "Shift" becomes "one SOC week".

**Alternative: keep 1 turn = 1 hour (a real 10-hour shift).** Then p must shrink: p = 3 ÷ (hours to ransomware).

| Hours to ransomware | p_advance | Chance an attack starting on turn 1 reaches ransomware within 10 turns |
|---|---|---|
| 5 h (fastest 10% of Secureworks cases) | 0.6 | 99% |
| 17 h (Huntress average) | 3 / 17 ≈ 0.18 | 26% |
| 24 h (Secureworks median) | 3 / 24 = 0.125 | 12% |

With p ≈ 0.13–0.18, most attacks would end the shift still running (−1), and the −5 ransomware penalty would be rare. The current game (p = 0.6, 1 h turns) would only model the fastest gangs. We do not recommend this.

**Open point for the alert-noise research.** If 1 turn ≈ 12 h, then "9 false alarms per turn" means about 18 false alarms per day reach this analyst, and "1 alert opened per turn" means 2 investigations per day. Those numbers should be checked against the alert-volume data before Ali picks the turn length.

## Proposed changes (for a spec PR Ali reviews)

| Spec item | Now | Proposed | Why |
|---|---|---|---|
| §4.3 stage-1 alert types | `phishing_link_clicked`, `off_hours_login`, picked 50/50 | `failed_login_burst` 0.48, `off_hours_login` 0.39, `phishing_link_clicked` 0.13 | Brute force and stolen passwords dominate ransomware entry; phishing is small [S5], [S6], [S2] |
| §4.2 meaning of a turn | not defined | 1 turn ≈ 12 hours; a shift ≈ 5 days | Makes p = 0.6 match 17 h – 5 days to ransomware [S1], [S3], [S9], [S10] |
| §4.2 p_advance | 0.6 | 0.6 (no change) | Backed once a turn is defined as above |
| §4.2 attacks per shift, start turn, target split | 2–4, turn 1–6, 20/30/50 | No change; label as "our assumption, no public data" | Nothing public to match |

W2 ideas, not for W1: an alert type for exploits on edge devices; a data-theft stage before encryption; faster early stages and a slower last stage; target importance that depends on the stage.

## Sources

| ID | Report, year | Data | Type | Where in the source | Link |
|---|---|---|---|---|---|
| S1 | Sophos, 2025 Active Adversary Report | 413 IR and MDR cases, 2024 | Incident data | Sections "Come together: Root cause", "We're one (but we're not the same)", "No time to waste", "Games without frontiers", "The main event", "You down with TTP?", "Other findings" | https://www.sophos.com/en-us/blog/2025-sophos-active-adversary-report |
| S2 | Sophos, 2026 Active Adversary Report | 661 cases, Nov 2024 – Oct 2025 | Incident data | Root cause and timing sections (compromised credentials 42.06%, vulnerability 16.04%, brute force 15.58%, phishing 6.35%; AD 3.40 h; 88.10% deployed out of hours; exfiltration ≈ 78.83 h) | https://www.sophos.com/en-us/blog/2026-sophos-active-adversary-report |
| S3 | Mandiant, M-Trends 2025 Executive Edition | Mandiant investigations, 2024 | Incident data | Page 2, "By the Numbers" | https://services.google.com/fh/files/misc/m-trends-2025-executive-edition-en.pdf |
| S4 | Google Cloud blog, "M-Trends 2025" | Same as S3 | Incident data | Dwell time by notification source | https://cloud.google.com/blog/topics/threat-intelligence/m-trends-2025/ |
| S5 | Help Net Security, "Understanding 2024 cyber attack trends" (2025-04-24), repeating M-Trends 2025 full report | Mandiant investigations, 2024, ransomware-related intrusions | Incident data (secondary) | Ransomware initial infection vectors list | https://www.helpnetsecurity.com/2025/04/24/understanding-2024-cyber-attack-trends/ |
| S6 | Mandiant, M-Trends 2026 Executive Edition | Mandiant investigations, 2025 | Incident data | Page 2 (foreword), page 3 "By the Numbers", page 4, page 5 "A Minor Infection Today Can Be a Ransomware Attack Tomorrow" | https://services.google.com/fh/files/misc/m-trends-2026-executive-edition-en.pdf |
| S7 | BankInfoSecurity, "Verizon Reports Surge in Breaches Tied to Edge Devices" (2025-04-23), repeating Verizon DBIR 2025 | Breaches, 2024 | Incident data (secondary) | Credential abuse 22%, exploitation 20%, phishing 16%; ransomware in 44% of breaches | https://www.bankinfosecurity.com/verizon-reports-surge-in-breaches-tied-to-edge-devices-a-28061 |
| S8 | Verizon, 2026 DBIR landing page | Breaches, Nov 2024 – Oct 2025 | Incident data | Exploits 31% of breaches (#1); ransomware in 48% of breaches. Credential-abuse and phishing shares are not on this page; we did not verify them. | https://www.verizon.com/business/resources/reports/dbir/ |
| S9 | Security Magazine (2023-10-05), repeating Secureworks State of the Threat 2023 | Secureworks IR engagements, Jun 2022 – Jul 2023 | Incident data (secondary) | Median 4.5 days → under 1 day; more than half within 1 day; 10% within 5 h | https://securitymagazine.com/articles/99978-report-ransomware-dwell-time-hits-low-of-24-hours |
| S10 | CSO Online (2025-02-17), repeating Huntress 2025 Cyber Threat Report | Huntress ransomware incidents, 2024 | Incident data (secondary; average, not median; case count not given) | Time to ransom about 17 h; some groups 4–6 h | https://www.csoonline.com/article/3825444/ransomware-gangs-extort-victims-17-hours-after-intrusion-on-average.html |
| S11 | CrowdStrike, 2025 Global Threat Report blog | CrowdStrike telemetry and cases, 2024 | Incident data | Average eCrime breakout time 48 min (62 min the year before); fastest 51 s | https://www.crowdstrike.com/en-us/blog/crowdstrike-2025-global-threat-report-findings/ |
| S12 | CISA et al., #StopRansomware: Akira Ransomware, AA24-109A (updated 2025-11-13) | Government investigations, Jun 2023 – Aug 2025 | Incident data | Technical details and ATT&CK tables (T1190, T1133, T1078, T1110, T1566, T1136.001/.002, T1046, T1021.001, T1486) | https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-109a |
| S13 | The DFIR Report, "Cat's Got Your Files: Lynx Ransomware" (2025-12-17) | One intrusion | Incident data (single case) | Timeline: RDP with valid account → admin accounts on the DC in under 1 h → NetScan → ransomware on file and backup servers; time to ransomware just under 178 h | https://thedfirreport.com/2025/12/17/cats-got-your-files-lynx-ransomware/ |
| S14 | The DFIR Report, "Apache ActiveMQ Exploit Leads to LockBit Ransomware" (2026-02-23) | One intrusion | Incident data (single case) | Timeline: exploit → credential dumping → SMB scanning → re-entry on day 18 → Advanced IP Scanner → ransomware on backup and file servers; time to ransomware 419 h | https://thedfirreport.com/2026/02/23/apache-activemq-exploit-leads-to-lockbit-ransomware/ |
| S15 | TechTarget (2024-10-16), repeating Microsoft Digital Defense Report 2024 | Microsoft telemetry, Jul 2023 – Jun 2024 | Incident data (secondary) | More than 90% of attacks reaching ransom stage used unmanaged devices; share reaching encryption down threefold in two years | https://www.techtarget.com/cybersecurity/news/366613799/Microsoft-sees-drop-in-ransomware-reaching-encryption-phase |
| S16 | Sophos, The State of Ransomware in Enterprise 2025 | 1,733 enterprise respondents (of 3,400), Jan – Mar 2025 | Survey | Data encrypted in 49% of attacks (66% in 2024); 47% stopped before encryption (22% in 2023) | https://www.sophos.com/en-us/blog/the-state-of-ransomware-in-enterprise-2025 |
| S17 | Sophos press release, "Hive, LockBit and BlackCat ransomware gangs consecutively attack the same network" (2022-08) | Case studies | Incident data (case studies) | Three gangs, two attacks within 2 hours, third two weeks later | https://www.sophos.com/en-us/press/press-releases/2022/08/hive-lockbit-and-blackcat-ransomware-gangs-consecutively-attack-the-same-network |
| S18 | MITRE ATT&CK Enterprise tactics and techniques | Reference model | Reference (not statistics) | Tactics list; T1136 Create Account; T1046 Network Service Discovery; T1486 Data Encrypted for Impact | https://attack.mitre.org/tactics/enterprise/ · https://attack.mitre.org/techniques/T1136/ · https://attack.mitre.org/techniques/T1046/ · https://attack.mitre.org/techniques/T1486/ |

Not found (searched, nothing public): a ransomware-only root-cause split in the Sophos Active Adversary reports; a public median "time to ransomware" from The DFIR Report across all cases; any data on how many intrusions a SOC handles at once; any percentage split of which machine importance attackers target first; any data linking `cloud_key_new_asn`-style events to ransomware.
