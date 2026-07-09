# International Disaster Communications Research
## Off-Grid Mesh + AI Triage Validation Report

**Researcher:** Disaster-communications research agent
**Date:** July 2026
**Purpose:** Evaluate whether international disaster evidence validates an off-grid mesh + edge-AI triage concept, and what professionals actually use as alternatives.

---

## TOP VERDICT (Read This First)

The evidence broadly validates the **problem** — communications blackouts during disasters are real, prolonged, and demonstrably cause deaths. The evidence is **mixed to skeptical** about mesh networks as the solution, with professionals consistently reaching for satellite, mobile base stations (cells on wheels), and the Emergency Telecommunications Cluster (ETC) as primary fixes. Mesh networks have been deployed in several disasters (Haiti 2010, Philippines 2013, Nepal 2015, Puerto Rico 2017) but none at meaningful scale — the documented deployments are small-team/community-level, not city- or region-scale coordination. The one major government-funded mesh deployment (goTenna in Puerto Rico, ~$900k) was a documented failure. Satellite — specifically LEO satellite like Starlink — is the professional preference for restoring backbone connectivity, typically arriving within 48-72 hours. Myanmar 2025 is the strongest narrative for off-grid alternatives because the junta actively confiscated satellite equipment, making satellite itself vulnerable.

**Where the off-grid mesh + AI triage concept has genuine evidence support:** triage coordination within a 72-hour window in areas where satellite can't reach OR is actively blocked by authorities. The Myanmar case is exactly that scenario. The concept's validity depends on the threat model: a regime that actively disrupts connectivity, not just passive infrastructure damage.

---

## Case 1: Nepal Earthquake, April 2015 (M7.8)

### Comms Blackout Reality
- **Magnitude:** 7.8 earthquake, 8,896 deaths, ~22,000 injured
- Nepal Telecom (NT): 95% of BTS towers functioning relatively quickly — however, local connectivity to individual residences and businesses was heavily compromised
- Ncell: 90% of towers in 15 affected districts were up, BUT in hard-hit Dolakha only 57% functioning, Sindhupalchowk 78% functioning after aftershocks
- Key damage pattern: 80%+ of BTS towers in Kathmandu were rooftop-installed — 5 NT buildings with towers and several Ncell buildings collapsed
- Fiber backhaul was severed in remote districts; local last-mile connectivity failed even when BTS towers were intact
- Estimated total telecoms losses: >$45.5 million USD
- **Who was cut off:** Most severely the 14 earthquake-affected districts in remote mountain areas; Kathmandu urban core recovered faster

**Sources:**
- [Kathmandu Post telecom damage](https://kathmandupost.com/money/2015/05/17/telecom-operators-may-face-problems-in-setting-up-towers)
- [ETC Nepal Cluster Brief OCHA](https://www.unocha.org/publications/report/nepal/emergency-telecommunications-etc-nepal-earthquake-cluster-brief-july-2015)
- [ScienceDirect spatial assessment](https://www.sciencedirect.com/article/pii/S1757780223004791)

### How Responders Coordinated Without the Network
- **Satellite phones and VSAT were the primary early-response tool.** One responder (Steve Birnbaum/NetHope) brought 25 IP+ terminals and 35+ satphones on the first flight in
- VSATs deployed by NetHope, UN, Luxembourg government in follow-on cargo
- ETC activated and at peak provided internet to **1,550+ humanitarians from 250+ organizations across 24 sites**
- HAM radio operators from India set up on the Nepal border, providing backup voice/text
- Disaster Tech Lab deployed small mesh network in remote communities — but this was supplementary, not primary
- **What after-action reports said was MISSING:** Portable equipment that could reach remote mountain villages; the ETC served the coordination hub in Kathmandu well but the last-mile to distant affected districts remained broken

**Sources:**
- [Via Satellite Nepal satellite response](https://www.satellitetoday.com/connectivity/2015/12/02/how-satellite-made-a-difference-in-nepal-part-one/)
- [Ham radio Nepal Network World](https://www.networkworld.com/article/938418/ham-radio-attempts-to-fill-communication-gaps-in-nepal-rescue-effort.html)
- [ETC ReliefWeb cluster brief](https://reliefweb.int/report/nepal/emergency-telecommunications-etc-nepal-earthquake-cluster-brief-july-2015)

### Recovery Camp/Shelter Setup
- ETC set up shared internet at 24 coordination sites; humanitarian orgs registered to use the network
- Coordination was Kathmandu-centric; remote assessment teams operated on satellite phones
- Remote survivor triage relied on physical assessment teams reaching villages on foot/helicopter, not communications

### What After-Action Reports Recommended
- Better pre-positioned satellite communications equipment in country
- Portable solutions that can operate in remote mountain terrain
- The LIRNEASIA report (2016) specifically called for improved last-mile resilience — not mesh explicitly, but highlighted that infrastructure backhaul failure cut off otherwise-functional BTS towers

---

## Case 2: Turkey–Syria Earthquake, February 6, 2023 (M7.8 + M7.5)

### Comms Blackout Reality
- **Magnitude:** 7.8 + 7.5 within hours, ~60,000 deaths, 1.5 million homeless, 15+ million affected across 11 provinces
- Internet traffic collapses documented by network analytics:
  - **Kahramanmaraş (epicenter province):** 94% traffic reduction after the second earthquake
  - **Gaziantep:** 57% traffic drop vs prior week baseline
  - Additional provinces affected: Şanlıurfa, Kilis, Hatay, Osmaniye, Adiyaman, Diyarbakır, Malatya, Mardin, Adana
- Mobile networks had widespread outages for "extended periods" — calls and SMS failed
- Turkey initially **refused Starlink** (not licensed in-country); later 163 VSAT sites were set up by TÜRKSAT
- **Government-imposed restriction:** Twitter/X was blocked for ~8-12 hours on Feb 9 (3 days post-quake) when it was being actively used for rescue coordination

**Sources:**
- [Data Centre Dynamics Turkey internet disruption](https://www.datacenterdynamics.com/en/news/turkish-internet-disrupted-by-devastating-earthquakes-telcos-deploy-mobile-base-stations/)
- [Wikipedia 2023 Turkey-Syria earthquakes](https://en.wikipedia.org/wiki/2023_Turkey%E2%80%93Syria_earthquakes)
- [Washington Post Twitter restrictions](https://www.washingtonpost.com/technology/2023/02/08/twitter-restrictions-turkey-earthquake-aftermath/)

### How Responders Coordinated and Twitter Block Impact
- Within hours of the earthquake, Turkish tech volunteers built a **real-time crowdsourced survivor location map** scraping Twitter for addresses + geocoordinate data, used by rescue teams
- Hundreds of trapped survivors were actively tweeting their locations from under rubble
- When Twitter was blocked on Feb 9, this coordination channel broke — VPN workarounds "drained phone batteries" (critical energy issue for trapped victims)
- **TÜRKSAT deployed 163 VSAT sites** plus Wi-Fi access points
- Operators deployed **190+ mobile base stations** in the first wave; total ~500 COW-type units and 3,500 generators
- Within 48 hours: ~40% of damaged network capacity restored; by end of week 1: ~80% restored
- Luxembourg deployed the "emergency.lu" satellite comms system; Télécoms Sans Frontières deployed in Turkey
- HAM radio operators activated through ARRL/international networks
- **Twitter block verdict:** Multiple sources assert it "harmed rescue operations" but none provide quantified death toll attributable to the block. The circumstantial evidence (survivors tweeting locations; volunteer map being used by rescue teams during the same period) is credible but not causally proven.

**Sources:**
- [Scientific American Twitter cutoff harmed operations](https://www.scientificamerican.com/article/turkeys-twitter-cutoff-harmed-earthquake-rescue-operations/)
- [The Conversation Twitter disaster expert](https://theconversation.com/twitter-cutoff-in-turkey-amid-earthquake-rescue-operations-a-social-media-expert-explains-the-danger-of-losing-the-microblogging-service-in-times-of-disaster-199580)
- [Inmarsat TSF deployment](https://www.inmarsat.com/en/news/latest-news/corporate/2023/telecoms-sans-frontieres-deploys-in-turkey-following-earthquake.html)
- [WEF satellite imagery Turkey](https://www.weforum.org/stories/2023/02/earthquake-turkey-syria-satellites-help-rescue-efforts/)

### Recovery and What Was MISSING
- INSARAG conducted its largest-ever international urban search and rescue operation here
- After-action reports noted: need for clearer situational picture in early hours; communication between staging areas and command was fragmented
- The Twitter coordination effort by volunteers was not integrated with official AFAD systems — it was ad hoc and technically brilliant but not institutionalized
- No mesh network deployment documented at meaningful scale

---

## Case 3: Myanmar Earthquake, March 28, 2025 (M7.7) — STRONGEST NARRATIVE

### Comms Blackout Reality — Compound Crisis
This is the unique case: a disaster on top of a pre-existing intentional communications blackout, plus active confiscation of satellite equipment.

- **Magnitude:** 7.7 — strongest ever recorded in Myanmar, epicenter in Sagaing near Mandalay
- **Deaths:** 3,600+ confirmed; estimates ranged to 10,000
- **Affected area:** 67+ townships
- **Pre-existing shutdown:** Myanmar military junta had been running internet shutdowns since 2021 coup; by 2024, 85 documented shutdown cases (most of any country globally per Access Now)
- **Post-earthquake shutdown:** "More than 100 townships, representing almost a third of the country" had no internet access, including the areas worst hit by the earthquake
- Facebook Messenger, WhatsApp, and Signal were throttled or blocked as of 31 March 2025
- Power outages from the earthquake combined with deliberate blocking created unprecedented communications collapse

**Sources:**
- [Rest of World Myanmar internet blackout blocking aid](https://restofworld.org/2025/myanmar-earthquake-internet-shutdown/)
- [Context/TRF Myanmar shutdowns hinder response](https://www.context.news/digital-rights/in-myanmar-internet-shutdowns-hinder-earthquake-aid-response)
- [Access Now joint statement](https://www.accessnow.org/press-release/call-for-lifting-of-internet-restrictions-myanmar/)
- [APC joint statement](https://www.apc.org/en/pubs/joint-statement-myanmar-must-lift-internet-restrictions-following-devastating-earthquake-1)
- [Japan Times Myanmar coverage](https://www.japantimes.co.jp/news/2025/04/10/asia-pacific/myanmar-internet-earthquake-aid/)

### Documented Impact on Rescue Operations
Specific documented cases (verified from multiple sources):
1. **"Three days passed before help reached one town"** in Sagaing due to communication blackouts preventing residents from calling in needs to aid groups (humanitarian worker testimony, Context/TRF)
2. **Residents had to travel several days** to find connectivity and communicate needs to aid organizations — in areas with complete blackouts (same source)
3. **One activist took 24+ hours** to learn the earthquake's full scope, only accessing details through a clandestine Starlink connection
4. **The critical 72-hour survivor window closed** before proper coordination reached many areas (CSIS analysis)
5. **Dispersing funds was impossible** without internet access in most affected areas

### Satellite Response — And Why It Also Failed
- Starlink could provide connectivity but at $389+ startup + $0.48/two-hour session — expensive for affected communities
- Richard Horsey (International Crisis Group): "Starlink can provide vital connectivity...but Starlink is expensive, and there are not that many units"
- **Military confiscated Starlink devices:** When people tried to use Starlink in the Sagaing battleground region, "military or soldiers came to confiscate the kits." At least one documented village raid for Starlink equipment
- EU Copernicus and Planet Labs satellite imagery used for remote damage assessment by outsiders, not by local responders
- Chinese rescue teams used DeepSeek AI translation tool for English-Burmese communication

**Sources:**
- [CSIS compounding devastation Myanmar](https://www.csis.org/analysis/compounding-devastation-myanmar-earthquake)
- [Foreign Policy civilians bear Starlink cuts](https://foreignpolicy.com/2026/01/13/myanmar-starlink-scam-centers-elon-musk-civilians-military-elections/)
- [Internet Society Myanmar crisis](https://pulse.internetsociety.org/blog/myanmar-earthquake-a-crisis-within-a-crisis)

### Why Myanmar is the Strongest Case for the Concept
This is the one documented case where:
- Satellite was actively defeated by authorities (confiscation + licensing restrictions)
- Cell towers were both physically destroyed AND deliberately blocked
- Social media was throttled by the state
- The 72-hour survivor window passed before coordination could be established in the worst-hit areas
- An **off-grid system that doesn't route through any centralized infrastructure** and can't be confiscated via a single point of control would have been uniquely valuable here

**What was MISSING per responders:** Any communication solution that does not depend on (a) commercial satellite providers subject to government licensing, (b) mobile networks, or (c) internet platforms that can be throttled. Short-range off-grid mesh + local coordination AI fits this gap precisely.

---

## Case 4: Hurricane Maria, Puerto Rico, September 2017

### Comms Blackout Reality
- **Category 4 hurricane,** 3.3 million U.S. citizens affected
- **95% of cell sites out of service** immediately post-landfall (FCC/GAO data)
- 48 of 78 municipios: 100% of cell sites offline
- 85% of above-ground telephone and internet cables destroyed
- By October 20 (one month later): only 49.1% of cell towers operational
- Full restoration took **six months**; 4% of sites still offline at 6-month mark
- **Power outage:** 181+ days for substantial portions of the island — the actual restoration blocker was power, not just tower damage
- Estimated deaths: 800-8,500 (Harvard study range); communications failures directly contributed

**Sources:**
- [GAO FCC Hurricane Maria report](https://www.gao.gov/products/gao-21-297)
- [PBS Nova Puerto Rico internet](https://www.pbs.org/wgbh/nova/article/puerto-rico-hurricane-maria-internet/)
- [Washington Post 181 days dark](https://www.washingtonpost.com/graphics/2017/national/puerto-rico-hurricane-recovery/)

### The goTenna Mesh Deployment — The Cautionary Tale
This is the most important case study on mesh network real-world failure:
- DHS/DOD spent approximately **$900,000 in taxpayer funds** on goTenna units for Puerto Rico emergency communications
- **~300 devices donated directly to the island**
- **Result five months later:** Only 6 nodes active (in San Juan only), accessible on the imeshyou.com tracking map
- Devices allegedly concentrated in affluent San Juan administrative areas rather than remote mountainous regions (Utuado etc.) where they were needed
- GoTenna explicitly told investigators they were "most decidedly NOT a disaster or a humanitarian company" and operated limited business hours (M-F, 11am-4pm)
- The company prioritized commercially-viable areas (near administrators) over hard-hit communities

**What actually helped in Puerto Rico:**
- AM radio was the primary emergency communication channel in early days
- Puerto Rican diaspora organized coordination via chat rooms outside the island
- Small-scale volunteer goTenna deployments by individual community organizers (3 solar-powered relay nodes covering one community) did work — but only at hyper-local scale, not regionally
- Eventual cell tower restoration and power restoration (COW + generators) was the actual backbone recovery

**Sources:**
- [Frank Bryan Medium — missing mesh network mystery](https://medium.com/@frankbryan/mystery-solved-the-case-of-the-missing-emergency-communications-mesh-network-in-puerto-rico-344c55c913d8)
- [Ushahidi mesh networking lessons Puerto Rico](https://medium.com/ushahidi/mesh-networking-and-crisis-response-learning-from-puerto-rico-d1343c581eda)
- [TechCrunch Puerto Rico mesh network spontaneous](https://techcrunch.com/2017/11/14/a-mesh-network-spontaneously-erupts-in-the-us-and-helps-connect-puerto-rico/)

---

## Case 5: Japan Tohoku, March 11, 2011 (M9.0)

### Comms Blackout Reality
- **Magnitude 9.0, 15,894 killed, 2,500+ missing**, 6 prefectures devastated
- NTT damage assessment:
  - ~6,700 pieces of mobile BTS equipment damaged
  - ~1.5 million circuits for fixed-line services disrupted
  - ~15,000 corporate data circuits disrupted
  - 90 transmission routes disconnected
  - 18 exchange office buildings destroyed; 23 submerged
  - ~65,000 telephone poles destroyed
  - ~6,300 km of aerial cables damaged
- Mobile services: 5%-30% of normal capacity in first 2 days; peaked at worst 2-3 days post-quake
- Undersea cables damaged: APCN-2, Pacific Crossing West/North, East Asia Crossing, Japan-U.S. Cable Network, PC-1
- NTT Docomo: had 530 base stations with disrupted services in Iwate, Miyagi, Fukushima; formulated restoration plan for 375 base stations

**Sources:**
- [NTT press release March 2011 damage](https://www.ntt.com/en/about-us/press-releases/news/article/2011/20110330.html)
- [PMC Japan 2011 communications problems](https://pmc.ncbi.nlm.nih.gov/articles/PMC4301195/)
- [IEEE Spectrum why internet didn't cripple](https://spectrum.ieee.org/why-the-japan-earthquake-didnt-cripple-the-countrys-internet)

### How Responders Coordinated
- Satellite phones were the best-performing alternative: "satisfaction rated good to moderate (50%) during first four days" by DMAT medical teams
- Social media (Twitter, Facebook) via mobile phone was rated useful by many DMATs for early coordination
- Japan's existing disaster prevention administrative radio system was used but had gaps (35% of tsunami-zone residents did not hear evacuation audio)
- Key coordination failure documented in academic literature: "problems of inadequate information acquisition and exchange between rescue staging care units and the control task force result in confusion of tasks" — partial information picture led to "operational and tactical errors"

### Lessons and Recommendations
- Japanese DMAT teams' top recommendation: **"A new battery-powered satellite communication device that can transmit high volumes of data, is portable, and offers stable communication"**
- Easy-to-connect and good battery life were rated top priorities
- Japan's backbone internet survived better than expected due to ring topology design — the lesson was about redundancy in design, not replacement technology
- However: local last-mile and mobile base station damage was extensive enough that individual responders couldn't coordinate without satellite

---

## Case 6: Tonga Hunga Tonga Eruption, January 15, 2022

### Comms Blackout Reality
- Volcanic eruption destroyed the **only undersea fiber-optic cable** connecting Tonga to the global internet
- **105,000 residents** almost completely isolated from external communications
- Domestic cable (closer to eruption) took up to **9 months** to fully replace
- International cable (92 km section) restored in approximately **5 weeks**

### Satellite Response
- Elon Musk offered Starlink; SpaceX set up a gateway station in Fiji
- Technical limitation: Fiji is ~500 miles from Tonga — exceeds optimal 180-250 mile range, degrading service quality
- 50 VSAT terminals donated by SpaceX on February 15, 2022 (30 days post-disaster)
- Tonga government received the terminals and distributed to outlying islands
- Starlink operated under a temporary 6-month emergency telecom license

**Key lesson from Scientific American analysis:**
- Starlink is useful but not charity — "If they're suddenly not making a profit from Tonga, they will pull out"
- Experts recommend **backup undersea cables along different routes** as the real resilience solution; satellite as supplementary, not primary
- Tonga later ordered Starlink to cease service to customers (regulatory/licensing dispute) — demonstrating government control over satellite connectivity

**Sources:**
- [Communications.gov.to Starlink restoration Tonga](https://www.communications.gov.to/index.php/blog-show/98-restoration-of-internet-connectivity-in-tonga-by-starx-starlink-company)
- [Scientific American Starlink PR stunt question](https://www.scientificamerican.com/article/starlink-offers-internet-access-in-times-of-crisis-but-is-it-just-a-pr-stunt/)
- [Claims Journal Starlink villages Tonga](https://www.claimsjournal.com/news/international/2022/02/23/308837.htm)

---

## Section: Mesh Networks — Honest Evidence Review

### Documented Real Deployments

| Disaster | Organization | Scale | Documented Outcome |
|---|---|---|---|
| Haiti 2010 | Serval Project | Small (exact nodes unknown) | Voice/text within hours; no metrics on coverage or scale |
| Philippines Haiyan 2013 | Commotion Project | Small (Wi-Fi routers + laptops) | "Communities regained internet access"; no coverage/user numbers |
| Nepal 2015 | Disaster Tech Lab | Small/supplementary | Supported rescue in remote areas; satellite remained primary for ETC |
| Puerto Rico 2017 | goTenna (government) | Regional (~300 units, $900k) | **Failed** — 6 nodes active 5 months later, misallocated to San Juan |
| Puerto Rico 2017 | Volunteer community | Micro (3 solar nodes) | Covered single community; worked but not replicable at scale |
| Indonesia Sulawesi 2018 | Local orgs | Unknown | Coordination for relief distribution; no scale metrics |

### Honest Assessment

**What works:** Hyper-local mesh (3-10 nodes, one community, set up by motivated volunteers) can restore voice/text communications in hours without infrastructure. This is genuinely demonstrated.

**What doesn't scale:** City-level or regional mesh has never been demonstrated at meaningful scale in a real disaster. The Puerto Rico $900k government deployment is the largest documented attempt and was a complete failure due to:
- Corporate incentives misaligned with disaster relief
- No pre-deployment community integration
- Node density problem (too few nodes spread over too large an area)
- No pre-installed app on affected residents' phones

**The node density problem:** Mesh networks require nodes close enough together for multi-hop routing. In an earthquake where buildings collapse and people are displaced, achieving sufficient density is harder than in peacetime. Academic research confirms this — prior designs have not demonstrated scalability beyond a few hundred to a few thousand nodes reliably.

**Sources:**
- [Meshmerize emergency network deployment](https://meshmerize.net/emergency-network-deployment-mesh-in-disaster-management/)
- [LinkedIn benefits/challenges mesh disaster](https://www.linkedin.com/advice/0/what-benefits-challenges-using-mesh-networks-disaster)
- [WiMesh academic paper on mesh in poor regions](https://arxiv.org/pdf/2101.00573)

---

## Section: What the Professional Ecosystem Actually Does

### The Standard Response Stack (based on ETC, INSARAG, OCHA after-action reports)

1. **First 0-48 hours:** Satellite phones and portable VSATs are flown in by first responders (ETC activation protocol). This is the international standard.
2. **48-72 hours:** Cells on Wheels (COW) — mobile base stations on trucks — deployed by telecoms. In Turkey 2023, 190 mobile base stations were deployed in the first wave, with ~500 total COW units.
3. **Week 1-2:** Generator-powered temporary base stations restore 40-80% of network (Turkey achieved 80% in week 1).
4. **Supplementary:** HAM radio for interagency comms; satellite imagery for damage assessment; ETC shared internet hubs for coordination centers.

### Who Calls the Shots

The **Emergency Telecommunications Cluster (ETC)**, led by WFP, is the UN-coordinated body for disaster telecoms. It activates in major disasters and deploys VSAT + shared internet for humanitarian coordination. It reached 1,550 humanitarians in Nepal, 6,500+ in Philippines Haiyan (record number at that time).

The **Crisis Connectivity Charter (CCC)** — a satellite industry coalition — provides emergency satellite connectivity to humanitarian orgs. Activated for Turkey 2023 and Mozambique 2024.

### What Professionals Recommend for Future Resilience

From WIPO Green Technology analysis and ITU guidance:
- **Multi-channel approach:** Cell Broadcast (doesn't require app or subscription) as primary alert, satellite as fallback backbone
- Galileo Emergency Warning Satellite Service (EWSS) was scheduled to launch in 2025
- ITU recommends pre-designating satellite frequency bands for disaster use in national planning
- **NOT mesh as primary:** mesh is mentioned as having "self-healing" properties and being "rapidly deployable" but satellite and COW are the primary professional recommendation

**The COW/satellite story for hackathon purposes:** The real competition for an off-grid mesh concept isn't "another mesh app" — it's that within 24-72 hours, professional responders deploy COW and satellite. The concept is most defensible as a **first 72-hour bridge** in scenarios where:
(a) The disaster occurs in a conflict zone where authorities actively block satellite
(b) COW deployment is physically prevented (destroyed roads, active conflict)
(c) The population is pre-equipped with the mesh devices before disaster strikes

**Sources:**
- [WIPO Green Technology disaster communications](https://www.wipo.int/web-publications/green-technology-book-solutions-for-confronting-climate-disasters/en/communications-and-digital-coordination.html)
- [INSARAG AAR OCHA Turkey 2023](https://www.unocha.org/publications/report/turkiye/insarag-after-action-review-2023-turkiye-and-syria-earthquakes-comprehensive-report-insarags-largest-international-search-and-rescue-operation)

---

## Section: AI Triage in Disaster Response

### What Exists / What's Recommended

**Survivor detection AI:** Documented research using deep learning for post-earthquake survivor detection:
- YOLOv10 achieving 98.4% mAP@0.5 accuracy for survivor detection, 15ms inference time
- YOLOv10-Nano with MobileNet backbone: 80.5 FPS with edge deployment constraints
- Snake robots with object-detection AI for debris search
- SOS Drone project: YOLOv6 fine-tuned for disaster scenarios combined with MSNet for building damage assessment

**Edge computing for off-grid scenarios:**
- Research explicitly makes the case for "pre-positioned edge computing resources at hospitals, shelters, and emergency coordination centers loaded with disaster-tuned models maintaining capability during grid and network failure"
- This is a recommendation in the literature, not yet a deployed standard

**In-field AI use documented in Myanmar 2025:**
- Chinese rescue teams used DeepSeek AI for real-time English-Burmese translation — this is documented and operational

**What's NOT documented:**
- No after-action report from ETC, INSARAG, OCHA, or IFRC mentions AI triage as a recommended tool yet
- The professional community is not yet calling for edge-AI triage — they are still focused on getting basic connectivity back via satellite/COW

**Conclusion on AI triage:** The technology exists (edge-deployable YOLO variants, lightweight LLMs for translation/coordination). The professional community is not yet requesting it explicitly, but there's no contrary evidence either. The gap between "what professionals deploy" and "what AI could enable" is real and unaddressed in current after-action reports.

**Sources:**
- [Nature Scientific Reports survivor detection AI](https://www.nature.com/articles/s41598-024-75156-z)
- [PMC survivor detection deep learning](https://pmc.ncbi.nlm.nih.gov/articles/PMC11500390/)
- [arXiv Moroccan earthquake AI disaster management](https://arxiv.org/html/2311.08999v2)

---

## Final Honest Verdict

### Does International Evidence Validate Off-Grid Mesh + AI Triage?

**The problem is real and validated:**
- Communications blackouts in disasters are documented, prolonged (days to months), and demonstrably cause deaths
- Nepal: remote districts cut off for days; ETC served only the coordination hub
- Turkey: 94% traffic reduction; government deliberately blocked rescue-critical social media
- Puerto Rico: 95% cell sites down for months; 181 days without power
- Japan: 1.5 million circuits disrupted; 6,700 BTS damaged; responders operating at 5-30% capacity
- Myanmar: compound crisis of physical damage + deliberate shutdown + satellite confiscation

**The professional solution to this problem is NOT mesh:**
- Professionals fly in satellite phones and VSATs within 24-48 hours
- Telecoms deploy COW (mobile base stations) within 24-72 hours
- ETC coordinates shared internet hubs for humanitarian orgs within days
- This usually works reasonably well in infrastructure-damaged-but-not-politically-blocked scenarios

**Where mesh + edge-AI has a genuine gap to fill:**
1. **The first 0-72 hours** before satellite and COW arrive — this window is real and critical for survivor detection
2. **Conflict zones where satellite is actively blocked or confiscated** (Myanmar is the archetype)
3. **Highly dispersed populations in non-urban terrain** where COW coverage is sparse
4. **Scenarios where node pre-deployment is feasible** (pre-positioned in shelters, hospitals, government buildings) — the key adoption barrier for mesh is that it requires people to have the device/app before the disaster

**The killer caveat for mesh:** The Puerto Rico case demonstrates that mesh works at community scale when deployed by motivated volunteers with 3-node coverage, but fails catastrophically at government/institutional scale due to adoption, incentive, and node-density problems. The $900k goTenna deployment is the cautionary tale every mesh proposal must address.

**The strongest narrative for hackathon:**
Myanmar 2025 + the first-72-hour window. A pre-positioned, off-grid, peer-to-peer mesh layer running edge AI for survivor triage that doesn't depend on any centralized infrastructure and can't be disabled by confiscating a single gateway is a genuinely unaddressed gap that no current professional solution solves. The narrative is not "mesh instead of satellite" — it's "mesh + edge AI for the critical window before satellite arrives and in regimes where satellite itself is weaponized against survivors."

---

## Key Sources Index

- [LIRNEASIA Nepal comms evaluation 2016](https://lirneasia.net/wp-content/uploads/2016/04/Nepal_Report_on_Emergency_Communications_v1.0.pdf) *(PDF — key academic primary source)*
- [ETC Emergency Telecommunications Cluster Nepal](https://www.etcluster.org/emergencies/nepal-earthquake)
- [GAO FCC Maria report](https://www.gao.gov/products/gao-21-297)
- [FCC 2017 Atlantic Hurricane Season communications report](https://docs.fcc.gov/public/attachments/doc-353805a1.pdf) *(PDF)*
- [INSARAG Turkey 2023 AAR](https://insarag.org/wp-content/uploads/2024/04/After-Action-Analysis-and-Recommendations-for-INSARAG-Turkiye-2023.pdf) *(PDF)*
- [PMC Japan 2011 communications problems](https://pmc.ncbi.nlm.nih.gov/articles/PMC4301195/)
- [Rest of World Myanmar internet blackout](https://restofworld.org/2025/myanmar-earthquake-internet-shutdown/)
- [Access Now Myanmar joint statement](https://www.accessnow.org/press-release/call-for-lifting-of-internet-restrictions-myanmar/)
- [Scientific American Starlink crisis](https://www.scientificamerican.com/article/starlink-offers-internet-access-in-times-of-crisis-but-is-it-just-a-pr-stunt/)
- [Frank Bryan goTenna Puerto Rico investigation](https://medium.com/@frankbryan/mystery-solved-the-case-of-the-missing-emergency-communications-mesh-network-in-puerto-rico-344c55c913d8)
- [WIPO Green Technology disaster comms](https://www.wipo.int/web-publications/green-technology-book-solutions-for-confronting-climate-disasters/en/communications-and-digital-coordination.html)
- [arXiv Moroccan earthquake AI](https://arxiv.org/html/2311.08999v2)
