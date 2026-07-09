# India Disaster After-Action Research: Communications, Coordination & Triage

**Compiled:** July 2026  
**Focus:** Does the Indian evidence support the premise that off-grid comms + AI triage would have genuinely helped?

---

## VERDICT (Read This First)

**The evidence partially supports the premise, but with important nuance:**

**What IS well-documented:**
- Cell networks fail in Indian disasters — but the mechanism is almost always **power failure** (diesel runs out, generators flood), not physical tower destruction. This means failures typically set in **4–24 hours after the disaster**, not instantly.
- Coordination and triage failures are real, severe, and documented: duplicated effort, victims not found, migrant workers actively deprioritized and linguistically excluded, information chaos at command centers.
- Ham radio operators filled genuine gaps: in Kerala 2018, ~300 operators at a single control center located 15,000+ stranded people and facilitated 1,800+ rescues when official systems were overwhelmed.
- Early warning failure is a separate but linked problem — in Wayanad 2024, a warning issued 16 hours in advance was ignored because it came from outside the official system.

**What UNDERCUTS the premise or needs honest qualification:**
- Wayanad 2024 — often cited as a "communications failure" case — had telecom restored within ~24 hours by BSNL (4G in affected areas by afternoon of July 31). Jio added a second dedicated tower. The real chokepoint was **road/bridge access and search area**, not comms.
- The claim that "first 36 hours of Wayanad were defined by communication silence" (from a vendor promoting MeshVani LoRa hardware) **has no primary source citation** and contradicts the documented telecom restoration timeline.
- Kedarnath 2013: telecoms were destroyed or washed away at specific locations (Kedarnath, Dharchula, Narayan Bagar), but the bigger failures were **command chaos** (no DM in Rudraprayag for 4 days, NDMA "failed miserably in its first major challenge"), and **lack of satellite phones** — the government had to import 25 sat phones from Hong Kong mid-operation, showing the gap was in preparedness, not in the technology concept.
- Himachal Pradesh 2023 and Sikkim 2023: telecom disruption documented, but restoration efforts (ICR facility, drone-based fibre repair) were underway within days. Root problems were fragmented agency coordination and lack of early warning, not absence of mesh networking.
- Joshimath 2023: a slow-onset subsidence event, not an acute comms failure scenario. The key story here is **information suppression** (ISRO report pulled from public access by NDMA) rather than network failure.

**The most honest framing:** Off-grid comms would help in the first 4–48 hours of acute disasters in remote Himalayan/Western Ghats terrain. AI triage would help the chronic, ongoing problem of information chaos at EOCs and migrant-worker exclusion. But neither is a silver bullet — the deeper failures are governance (ignored warnings, underprepared NDMA, silo-ed agencies) and physical access (road/bridge destruction). Any pitch must acknowledge this.

---

## Event 1: Kedarnath / Uttarakhand Floods, June 2013

**Scale:** 300,000 trapped; 580 confirmed dead, 5,748 missing (later revised to 4,120 missing); 110,000+ evacuated over Operation Surya Hope.

### 1. Communication Breakdown

**CONFIRMED — Infrastructure destroyed, sat phones imported mid-crisis:**

- All telecom equipment at Kedarnath, Dharchula, and Narayan Bagar was "washed away in the devastating floods." BSNL subsequently restored 272 mobile towers and 44 telephone exchanges across four districts (Uttarkashi, Rudraprayag, Chamoli, Tehri Garhwal).
- The government "imported 25 satellite phones from Hong Kong for the ill-prepared NDMA and NDRF" mid-operation — demonstrating that no sat phone stockpile existed beforehand. [Source: Operation Surya Hope Wikipedia; telecomlead.com]
- Military communication channels were provided to stranded civilians to call families, indicating civilian networks were non-functional in the affected areas.
- Telecom operators deployed portable base stations (Vodafone "Instant Network"), mobile charging stations, and free PCO booths at relief camps.
- Specific duration of outage not documented in open sources.

**Key quote:** Home Minister Sushil Kumar Shinde "admitted that there was no coordination among government agencies, which was hampering rescue operations." [Source: Down to Earth]

### 2. Relief/Recovery Camp Setup

- Army created bridges and linked routes between upper hills and towns before vehicles could move.
- First batch of people from Badrinath, Govindghat, Pandukeshwar, and Gaurikund came out on June 19 — three days after disaster onset.
- Survivors reported severe hardship: families trekked to Rudraprayag having run out of money; private taxis charged inflated rates; helicopter operators demanded Rs 50,000 per person.
- 29 medical posts established by June 25. [Source: Operation Surya Hope Wikipedia]

### 3. Coordination & Triage Problems

- Rudraprayag was without a district magistrate for **four days**. "No system in place to get information."
- "Multiple information flowlines and command structures only rendered the response entities confounded and aid agencies disoriented." [UCL IRDR blog]
- "Squandering of initial golden hours of search-rescue owed itself substantially to this fallacy."
- IMD predicted heavy rainfall on June 13; governments ignored warnings and issued no evacuation advisories.
- NDMA and NDRF criticized for "tardy, sloppy response" and "failing miserably in its first major challenge."
- Mock drills in 2011 identified communication gaps between agencies; problems were not fixed before the disaster. [Source: Down to Earth]

### 4. Tools Actually Used

- **Helicopters dominant:** 83 aircraft by June 23 (45 IAF, 13 Army, 25 civil); 2,137 sorties, 18,424 airlifted by June 30.
- **Military ground teams:** 10,000+ troops; ITBP rescued 33,009 pilgrims alone.
- **Satellite phones:** 25 imported mid-crisis from Hong Kong.
- **Physical lists:** Stranded people gave soldiers lists of contact names and phone numbers to deliver to families — essentially physical messaging when all networks were down.
- **Website:** Central Command launched a website June 26 for minute-by-minute updates.
- **Ham radio:** No specific documentation found for Kedarnath 2013 (vs. documented use in 2015 Chennai and 2018 Kerala).

### 5. Quotable Narrative Gold

- "At the Rudraprayag police control room, no one knew what action to take." [Down to Earth, https://www.downtoearth.org.in/natural-disasters/heavens-rage-41497]
- Government importing 25 sat phones from Hong Kong mid-crisis is a vivid symbol of preparedness failure.
- IAF Mi-17 crashed on June 25, killing 20 rescue personnel — showing the extreme conditions responders faced.

**Supports premise?** Yes for comms (sat phones needed, telecoms washed away) and yes strongly for coordination/triage. The "command chaos" is very well documented.

---

## Event 2: Chennai Floods, December 2015

**Scale:** India's fourth-largest city; city cut off for over a week; 3,500+ stranded at airport alone.

### 1. Communication Breakdown

**CONFIRMED — Network collapse, power failure root cause:**

- Mobile telephone service was "temporarily unavailable" during the disaster. Three main bridges closed, restricting ground movement. [ARRL ham radio report]
- Network failed for multiple reasons: physical damage to towers, power outages draining battery backups, fuel shortages preventing generator operation, flooding of premises containing base transceiver station (BTS) equipment.
- Network congestion compounded failure: surge in voice call volumes overwhelmed capacity even where towers survived. Experts called for priority-based systems where emergency calls override civilian traffic. [Business Standard, flood lessons for telecom]
- Residents' helpline numbers "were of no use as there was no network connection."
- WhatsApp and internet proved more resilient than voice calls in some areas: "The value of Wi-Fi access cannot be underestimated." Citizens created crowdsourcing site chennairains.org for locating food and shelter.

### 2. Relief/Recovery Camp Setup

- Outskirts and suburbs in "complete neglect" — no medical attention reached peripheral camps.
- Relief within metropolitan limits was more organized than at the fringes.

### 3. Coordination & Triage Problems

- Telecom firms' failure to maintain power for towers during extended outages identified as systemic gap.
- No priority-based emergency communication system for responders vs. civilians.

### 4. Tools Actually Used

- **Ham radio:** Indian Institute of Hams set up a station at Karnataka Urban Water Supply and Drainage Board office; activated 7.070 MHz emergency net and repeaters. Described as first responders to fill communication void. [ARRL, https://www.arrl.org/news/radio-amateurs-respond-to-grim-flood-situation-in-southern-india]
- **Crowdsourcing:** chennairains.org for shelter/food location.
- **Social media:** coordination through Twitter and WhatsApp where internet was available.
- **Indian Navy:** evacuation by watercraft.

### 5. Quotable Narrative Gold

- Distress messages: people wrote "Please save me", "help me", "send me a boat sir" — unable to make calls. [Dr. Venu blog]
- ARSI president describing the situation as "grim" with "power outages across most areas draining portable radio batteries."

**Supports premise?** Yes for comms failure (documented power-driven collapse). The crowdsourcing approach and ham radio fill-in show the demand for off-grid last-mile comms was real.

---

## Event 3: Kerala Floods, August 2018

**Scale:** Worst in 100 years; 5.4 million displaced; 1.24 million in 3,274 relief camps; 483 dead.

### 1. Communication Breakdown

**CONFIRMED — All 14 districts affected, power failure root cause:**

- "All 14 districts in Kerala faced breakdown in the communications system impacting rescue efforts." [TelecomLead, https://www.telecomlead.com/telecom-services/kerala-floods-mobile-operators-fail-to-connect-during-disaster-85906]
- Networks were unavailable for "several days" in most areas.
- Root cause: diesel fuel shortages for generator backup; batteries discharged. Not primarily physical tower destruction.
- Chalakudy town had **absolutely no connectivity** — "couldn't even send an SMS" — all five major providers (Jio, BSNL, Vodafone, Airtel, Reliance) failed simultaneously.
- State government official: "Instead of offering free calls, mobile providers should ensure we can connect with people via voice and data services." [TelecomLead]
- Airtel deployed VSAT at five relief centers for free Wi-Fi as backup.
- Toll-free number 1948 provided missing person location via SMS.

**Total subscribers affected:** Idea (12.4M), BSNL (10.7M), Vodafone (7.9M), Jio (5.8M), Airtel (5M).

### 2. Relief/Recovery Camp Setup

- 3,274 relief camps established; 1,247,496 people sheltered.
- Central government deployed: 40 helicopters, 31 aircraft, 500 boats, 182 rescue teams, 18 medical teams, 58 NDRF teams.
- Fishermen rescued 65,000+ people: 4,537 fishermen from Kollam and Thiruvananthapuram used 669 fishing boats; worked through the night with headlamps when official teams had to stop at sundown.
- Kerala Rescue app (built by student volunteers, quickly adopted by government) coordinated requests and offers of help. [Wikipedia]

### 3. Coordination & Triage Problems

**MAJOR — Migrant workers systematically deprioritized:**

- "Migrant workers were seen to be the last priority in rescue missions and were rescued and rehabilitated at the very end."
- Migrants "discriminated against in rescue, relief and rehabilitation."
- Non-Malayalee workers could not follow warnings and instructions given in Malayalam — missed evacuation alerts entirely.
- Fake news circulated in migrant WhatsApp networks claiming dams had collapsed, causing mass rush to railway stations and further chaos.
- Migrants missed out on drug administration to prevent leptospirosis; excluded from damage and loss assessments; lost compensation eligibility.
- Some employers refused to lend plywood factories for shelter to rescued workers.
- [Source: Insight Turkey / Irudaya Rajan study; UCL blog]

**Dam mismanagement as coordination failure:**
- "Uncoordinated dam releases worsened impacts" — various alerts issued "not in accordance with EAP guidelines."
- "No proper follow-up action and effective precautionary steps after issuance of Red Alert." [Wikipedia, citing CWC advisor]
- 61 dams lacked operation-and-maintenance manuals. [UCL blog]

### 4. Tools Actually Used

- **Ham radio (most documented case in India):** ~120–300 amateur radio operators assembled at Thiruvananthapuram District Administration office without formal organization.
  - Located 15,000+ stranded victims by tracing last mobile phone locations, relaying coordinates to District Emergency Operations Centre.
  - Facilitated 1,800+ rescues directly; 1,650 rescues between August 16–19 alone from Thiruvananthapuram centre.
  - [ARRL, http://www.arrl.org/news/kerala-india-flooding-radio-amateurs-assist-rescue-operations]
- **WhatsApp:** "Sprung up as control centers"; ward councillor used WhatsApp to summon fishermen who rescued 500+ people in Alappuzha.
- **Fishermen coordination:** organized in units under leaders, operated through the night when official rescues halted.
- **Kerala Rescue app:** student-built crowdsourcing tool that became official state support.

### 5. Quotable Narrative Gold

- Ham radio coordinator Suwil Wilson (VU2IT): "hams have reported the location and other details of more than 15,000 victims stranded on roofs." [ARRL]
- "Fishermen filled the vacuum, rescuing more than 65,000 people" using personal boats — "social capital, skills, and solidarity can transform disaster outcomes." [UCL blog]
- 70% of households included elderly, pregnant women, or bedridden individuals — "complicating evacuation." [UCL blog]

**Supports premise?** Strongly yes for comms failure and triage (migrant worker exclusion is exactly the kind of problem AI triage addresses). The ham radio success story is the closest real-world analog to what off-grid + triage tech could do — and it was improvised, underpowered, and yet still rescued 1,800 people.

---

## Event 4: Wayanad Landslides, July 30, 2024

**Scale:** 254 confirmed dead, 397 injured, 118 missing; Mundakkai area completely cut off; 93 relief camps.

### 1. Communication Breakdown

**PARTIAL — Short-lived disruption, not multi-day blackout:**

- Landslide occurred ~1:00 AM July 30. Punapuzha Bridge (sole access route to Mundakkai) collapsed, creating physical isolation.
- BSNL restored 4G services in Chooralmala and Mundakkai by the **afternoon of July 31** — approximately 24–36 hours after disaster. Used diesel engines to keep towers operational without grid power.
- Jio installed an additional dedicated tower; Airtel provided free data (1GB/day) and unlimited calls.
- K-FON provided high-speed internet to rescue teams.
- Jio Infocomm set up additional towers and increased network strength within days. [Wikipedia; Deccan Herald; TelecomTalk]

**Important caveat:** The claim that "first 36 hours were defined by communication silence" comes from an industry vendor (Autoabode/MeshVani) with no primary source citation, and the documented telecom restoration timeline contradicts it. What IS true is that the Mundakkai area was physically inaccessible by road, which is a different problem than network failure.

### 2. Relief/Recovery Camp Setup

- 93 relief camps across Wayanad; 45 set up by Kerala government initially sheltering 4,000+.
- Bailey bridge (190 feet) constructed in 31 hours to restore physical access.
- By August 26, all families relocated from camps to relief housing.

### 3. Coordination & Triage Problems

**Early warning not acted upon:**
- Hume Centre for Ecology & Wildlife issued a warning **16 hours before** the landslide. District administration did not act because "it was not integrated with the official warning system."
- Meteorological authorities issued multiple rainfall warnings; local governments "failed to organize timely evacuations."
- Victims were primarily tea and cardamom plantation workers "with limited educational backgrounds and lacking disaster awareness, resulting in indifference to early warning notifications." [ScienceDirect preliminary analysis]

**Victim identification crisis:**
- Bodies so damaged that visual identification was impossible; DNA testing required for 118 missing.
- Kannur Regional Forensic Lab ran cross-matching on 401 DNA samples; advanced next-generation sequencing deployed.
- Unique grave numbering system introduced to track unidentified remains.
- Migrant workers from West Bengal, Assam, Bihar, Madhya Pradesh, Jharkhand among victims; Tamil Nadu sent medical and NDRF teams.

### 4. Tools Actually Used

- **Advanced search technology:** breathing-signal radar, Buried Object Detection Systems, K9 units, UAV-based sub-soil scanners, DNA sequencing.
- **Physical infrastructure:** Bailey bridge in 31 hours; helicopters; earth movers.
- **Telecom augmentation:** BSNL 4G, Jio additional tower, K-FON for rescue teams.
- **Coordination:** GO-NGO desk at District Emergency Operations Center (DEOC).

### 5. Quotable Narrative Gold

- 254 dead; 118 still unidentified by DNA as of December 2024; graves numbered with plastic bottles — "names to replace numbers in mass graves." [Onmanorama]
- Warning system failure: private scientific warning existed 16 hours early, but wasn't "integrated with the official warning system." [Onmanorama lessons-learnt article]
- Plantation workers — "most of whom had limited educational backgrounds and lacked disaster awareness" — were resting in cottages when hit. They had no access to warnings even when warnings existed.

**Supports premise?** Partially. The comms disruption was real but brief (24–36 hours, not multi-day). The AI triage angle is strong: victim identification took months, early warnings didn't reach the right people, and vulnerable workers were the ones who died. The "last-mile warning delivery" problem is where tech would genuinely help.

---

## Event 5: Sikkim GLOF (South Lhonak Lake), October 3–4, 2023

**Scale:** 55 dead, 74+ missing; 92+ confirmed dead by October 18; 25,900+ buildings damaged; 31 bridges destroyed; Teesta III Dam destroyed.

### 1. Communication Breakdown

**CONFIRMED — No EWS, fibre network failed, north Sikkim isolated:**

- **No Early Warning System at South Lhonak Lake** when it breached. Scientists had been working on installation but it wasn't complete. Scientists had raised GLOF concerns since 2005.
- Authorities only learned of the disaster from Indo-Tibetan Border Police alerts downstream — after the flood was already moving.
- North Sikkim (including capital Gangtok) was **cut off from the rest of India** as parts of National Highway 10 collapsed.
- **Airtel's fibre optic network suffered a "major breakdown."** Airtel partnered with IG Drones to deploy drones for aerial survey and fibre repair — restored "within an exceptionally short timeframe." [Mobility India]
- Communication network around Chungthang, Mangan District, "affected" but specific duration not documented.
- Chungthang completely cut off due to collapse of Toong Bridge and Phidang Bridge.

### 2. Relief/Recovery Camp Setup

- Relief camps at Namphing Sai Mandir and Pranami Mandir in Namchi District (500 people).
- SDRF rescued 25 people in Gangtok district; NDRF deployed in Pakyong.
- 60-strong NDRF team including scuba divers rescued 14 people trapped in dam tunnels.
- 7,600 in relief camps in Sikkim; 10,000+ more in West Bengal (downstream flooding).

### 3. Coordination & Triage Problems

**Governance failures dominant:**
- Dam operators at Teesta III Dam "could not open gates in time"; reservoir was reportedly full when floodwaters arrived, magnifying downstream devastation.
- Central Water Commission 2015 report had identified dam vulnerabilities; dam's spillway capacity had been **reduced** from 7,000 to 3,000 cumecs — insufficient for the actual event.
- Glaciologist Anil Kulkarni: "deeply disappointing" that EWS installation efforts "had not been consistent." Scientists ignored since 2005.
- [Source: Mongabay India, https://india.mongabay.com/2023/10/no-early-warning-system-and-insufficient-dam-safety-turned-sikkim-flood-deadly/]

### 4. Tools Actually Used

- NDRF scuba divers for tunnel rescues.
- Indian Army relief operations.
- Drone-based fibre optic repair (Airtel + IG Drones) — novel use.
- Emergency helpline numbers for multiple districts.
- Bangladesh coordination: soldier's body repatriated from Nilphamari — cross-border impact.

### 5. Quotable Narrative Gold

- SSDMA Vice Chairman Vinod Sharma: "We were in discussions with the SDC about how to set up a sustainable monitoring system, given the terrain and past attempts." — installation never completed before the flood. [Mongabay]
- 23 Indian Army personnel missing; Teesta III Dam (a major infrastructure project) entirely destroyed.
- "Scientists raised GLOF concerns since 2005, but authorities systematically overlooked them."

**Supports premise?** Yes for the early warning angle (no EWS despite years of warnings). Partially for comms (fibre failed, road/bridge destroyed, north Sikkim isolated). The problem was more governance than technology gap.

---

## Event 6: Himachal Pradesh / Punjab Floods, 2023 Monsoon

**Scale:** 428 dead, 50,000+ displaced, Rs 8,665 crore damage; 5,748 landslides; 1,000+ roads blocked.

### 1. Communication Breakdown

**DOCUMENTED — Towers and fibre damaged, specific districts affected:**

- Chamba, Kullu, and Lahaul-Spiti worst affected for telecom.
- Optical fiber cable routes damaged; mobile towers damaged.
- DoT activated **Intra-Circle Roaming (ICR)** — allowing subscribers of any operator to use any available network. [DoT / dgtelecom.gov.in]
- Telecom restored described as providing "much-needed relief to residents, tourists, and emergency responders" but specific outage duration and tower count not published.
- NDMA found: "Himachal Pradesh's weather prediction and early warning capabilities are limited" — only 31 weather stations operational statewide. [Tribune India]

### 2. Relief/Recovery Camp Setup

- 70,000 tourists evacuated from the state per Chief Minister Sukhu.
- Delhi government provided shelter in relief tents for 16,000 individuals (from Yamuna flooding component).

### 3. Coordination & Triage Problems

**Fragmented agency coordination confirmed:**
- "Delays in inter-agency coordination, fragmented decision-making, and insufficient preparedness at district and panchayat levels severely hampered relief efforts."
- District Disaster Management Authorities (DDMAs) lacked "current disaster response protocols, robust communication infrastructure, and trained personnel."
- "Lack of coordination between organizations and authorities led to duplication of response efforts during the response phase." [Sphere India assessment; Tribune]
- NDMA recommended: install automatic weather stations in each gram panchayat.

### 4. Tools Actually Used

- Indian Army and NDRF ground teams.
- ICR facility for telecom continuity.
- Ground teams for fibre cable repair.

### 5. Quotable Narrative Gold

- "Only 31 weather stations currently operational" in all of Himachal Pradesh — an entire mountain state with 5,748 landslide events in one monsoon season.
- Duplication of relief effort due to coordination failures is the exact gap AI triage would address.

**Supports premise?** Yes for coordination/triage (agency fragmentation, duplication). Moderately for comms (towers damaged, ICR needed). Less so than Kerala or Kedarnath for the "network died completely" narrative.

---

## Event 7: Joshimath Subsidence, January 2023

**Scale:** 863 houses cracked; 278 families displaced to relief camps (930 people); slow-onset event over weeks.

### 1. Communication Breakdown

**NOT a comms failure — an information suppression case:**

- This is a slow-onset subsidence event, not an acute disaster. Mobile networks were not disrupted.
- Key communication issue: ISRO released a preliminary subsidence report January 13 showing 5.4 cm subsidence in 12 days. Two days later, the report was **removed from National Remote Sensing Centre's website** after NDMA prohibited government research bodies from publicizing information on Joshimath.
- PMO directed eight central organizations to study causes and report in two weeks.
- Continuous community dialogue recommended but the information suppression undermined trust.

### 2. Relief/Recovery Camp Setup

- 930 people from 278 families placed in temporary relief camps.

### 3. Coordination & Triage Problems

- Information suppression represents the inverse of the disaster comms problem: comms worked, but authorities chose to suppress data.
- Multiple government bodies studying causes with fragmented reporting.

**Relevance to premise:** Limited for network failure angle. Relevant for AI/data transparency angle — when the government has data (satellite subsidence measurements) but buries it, technology alone can't fix governance.

---

## Cross-Cutting Findings

### The Real Telecom Failure Pattern

Across all events, the dominant failure mode is NOT physical tower destruction — it is **power loss triggering battery/diesel exhaustion within 4–24 hours**. The implication: the first hours after a disaster may have working networks; the critical gap opens 4–12 hours in. Mesh/LoRa solutions that come in with rescue teams after 6+ hours would hit the window correctly.

### The Ham Radio Track Record in India

| Disaster | Ham Radio Role | Impact |
|----------|----------------|--------|
| Orissa Cyclone, Gujarat Earthquake | Coordination | Documented by IIH |
| Uttarakhand 2013 | ARRL reports operators active | No specific rescue count found |
| Chennai 2015 | 7.070 MHz net, repeaters activated | Coordination; "grim" conditions |
| Kerala 2018 | 15,000+ located, 1,800 rescued | Best documented case |
| Western India 2019 | 15 WHAMS operators monitoring | Supplementary role |

Ham radio has a genuine, documented track record. The Kerala 2018 case — 300 operators, 15,000 victims located, 1,800 rescued from a single control center — is the best evidence that **low-tech off-grid mesh communication has massive impact** when cellular fails.

### The Migrant Worker / Last-Mile Warning Gap

Kerala 2018 and Wayanad 2024 both show the same problem:
- Warnings issued in Malayalam (or only through official channels) miss non-Malayalee migrant workers.
- Migrant workers are last to be rescued, first to be forgotten in loss assessments.
- Workers in remote plantations have "limited educational backgrounds and lacked disaster awareness."

This is an AI triage / multilingual alerting problem that technology is well-positioned to address.

### NDMA's Own Acknowledgment of Comms Gap

NDMA has implemented a satellite-based National Management Communication Network covering 81 vulnerable districts with VSAT terminals and ISAT satellite phones — explicitly to provide "failsafe communication" when terrestrial networks fail. This is an official acknowledgment from India's apex disaster authority that terrestrial networks cannot be relied upon. [NDMA IT Communications Projects page]

---

## Sources (All Cited in Sections Above)

- Operation Surya Hope: https://en.wikipedia.org/wiki/Operation_Surya_Hope
- 2013 North India Floods: https://en.wikipedia.org/wiki/2013_North_India_floods
- Kedarnath UCL IRDR: https://blogs.ucl.ac.uk/irdr/2022/04/01/the-kedarnath-tragedy-breakdown-or-breakthrough/
- Kedarnath Down to Earth: https://www.downtoearth.org.in/natural-disasters/heavens-rage-41497
- Uttarakhand Telecom: https://www.telecomlead.com/telecom-services/telecom-operators-gear-up-to-restore-operations-in-flood-hit-uttarakhand-74168-32341
- Kerala Floods Wikipedia: https://en.wikipedia.org/wiki/2018_Kerala_floods
- Kerala Telecom Failure: https://www.telecomlead.com/telecom-services/kerala-floods-mobile-operators-fail-to-connect-during-disaster-85906
- Kerala Ham Radio: http://www.arrl.org/news/kerala-india-flooding-radio-amateurs-assist-rescue-operations
- Kerala UCL Vulnerabilities: https://www.ucl.ac.uk/mathematical-physical-sciences/blogs/2026/feb/beyond-deluge-how-2018-kerala-floods-revealed-deep-community-vulnerabilities
- Kerala Migrant Workers: https://www.insightturkey.com/commentaries/footloose-workers-in-times-of-calamities-a-case-study-of-the-2018-kerala-floods (paywalled; content via search snippet)
- Kerala PDNA: https://www.undp.org/sites/g/files/zskgke326/files/publications/PDNA_Kerala_India.pdf
- Kerala Fishermen: https://www.onmanorama.com/news/kerala/2018/08/26/kerala-flood-fishermen-rescue.html
- Wayanad 2024 Wikipedia: https://en.wikipedia.org/wiki/2024_Wayanad_landslides
- Wayanad 2024 Telecom Restoration: https://www.deccanherald.com/india/kerala/telecom-operators-restore-augment-telecom-connectivity-in-landslide-hit-wayanad-3133367
- Wayanad 2024 Early Warning: https://www.onmanorama.com/news/kerala/2024/12/10/wayanad-landslide-kerala-lessons-learnt-warning-systems-rehabilitation.html
- Wayanad 2024 DNA Identification: https://www.onmanorama.com/news/kerala/2024/08/28/names-replace-numbers-mass-grave-wayand-landslide-victims-identified-based-dna-released.html
- Wayanad 2024 Preliminary Analysis: https://www.sciencedirect.com/science/article/pii/S2666592125000472
- MeshVani/LoRa vendor claim (UNVERIFIED): https://www.autoabode.com/blog/lora-mesh-networking-disaster-relief-india
- Sikkim GLOF Wikipedia: https://en.wikipedia.org/wiki/2023_Sikkim_flash_floods
- Sikkim GLOF EWS Failure: https://india.mongabay.com/2023/10/no-early-warning-system-and-insufficient-dam-safety-turned-sikkim-flood-deadly/
- Sikkim Airtel Drone Repair: https://www.mobilityindia.com/how-airtel-is-leveraging-innovative-solutions-in-sikkim-to-restore-connectivity-affected-by-natural-calamities/
- Himachal Pradesh Telecom: https://dgtelecom.gov.in/heavy-rains-and-landslides-disrupt-telecom-in-himachal-dot-steps-up-restoration-efforts/
- Himachal Pradesh NDMA: https://www.tribuneindia.com/news/himachal/himachal-pradesh-floods-climate-change-illegal-construction-greenery-loss-increasing-disaster-risk-in-himalayas-says-ndma-report-586698
- 2023 North India Floods: https://en.wikipedia.org/wiki/2023_North_India_floods
- Joshimath: https://www.theindiaforum.in/environment/joshimath-avoidable-disaster
- Ham Radio India History: https://www.arrl.org/news/radio-amateurs-in-india-support-rescue-and-relief-operations-in-wake-of-flooding
- Chennai Ham Radio: https://www.arrl.org/news/radio-amateurs-respond-to-grim-flood-situation-in-southern-india
- NDMA VSAT Network: https://ndma.gov.in/Capacity_Building/Ops_Comm/IT_Comm_Project
- LoRa research paper citing Wayanad/Uttarakhand: https://ajse.aiub.edu/index.php/ajse/article/view/1055
