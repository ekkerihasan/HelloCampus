# Locality draft for the team to correct (NOT product data)

Researched by the monitor on 2026-10-19 from public sources. **Nothing here is verified on the ground.** A team member must check each entry, fill the blanks, and correct it. Only then does the builder copy it into `data/locality.json` with `"placeholder": false` and a fresh `last_checked`. Delete anything that is wrong or closed. Do not fill blanks by guessing.

Campus reference point: OpenStreetMap node 1709841585 "Anjuman Engineering College" (AITM), 13.99727, 74.55753, Anjumanabad, Bhatkal 581320. Distances below are straight-line from that point, not road distance.

Source for OSM rows: OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright). Link format: `https://www.openstreetmap.org/node/<id>`.

## USER-APPROVED (2026-10-19, about 15:10): use these, keep other spots as placeholders
The user chose these two lunch places and gave the links. Facts below were read once from each page (facts only, no review text). Fields marked "not shown" must stay empty, never guessed.

| Field | Layali Arabia Restaurant | Al Khaleej Arabian Restaurant |
|---|---|---|
| source_url | https://www.justdial.com/Uttara-Kannada/Layali-Arabia-Restaurant-Next-Taqwa-Credit-Cooperative-Society-Bhatkal/9999P8382-8382-251203125822-F8V7_BZDET | https://www.tripadvisor.in/Restaurant_Review-g2287549-d14763069-Reviews-Al_Khaleej_Arabian_Restaurant-Bhatkal_Uttara_Kannada_District_Karnataka.html |
| Address | NH 66, Kargedde, Rangikatte, next to Taqwa Credit Cooperative Society, Bhatkal, Uttara Kannada 581320 | Misbah Chambers, Bhatkal 581354 |
| Cuisine | Arabic | Middle Eastern, Arabic |
| Hours | "Open until 11:00 pm" (as shown on 2026-10-19) | not shown |
| Price range | not shown | not shown |
| Veg options | not shown | not shown |
| Rating shown | 121 ratings (value not captured) | 3.4 of 5, 5 reviews |
| Distance from campus | not shown (team: fill by road) | not shown (team: fill by road) |

Notes for the builder:
- `type: food`, `placeholder: false`, `last_checked: 2026-10-19`, `source_url` as above. `veg_options`: unknown, so the schema needs null or "unknown", not false. The host must say veg options are not confirmed rather than claim either way.
- Demo step 2 asks for "something veg": with these two, the honest answer is "here are two places near campus; I don't have confirmed veg options". The team can add a veg place or a veg dish later.
- Keep the other food placeholders (still `placeholder: true`, never indexed) for the team to fill.

## Schedule (user, 2026-10-19)
- Judging today, 2026-10-19, at 16:00 (4:00 PM). Venue: not given (team: fill). Source: the team (curated). The builder adds it to the schedule store so get_schedule can answer "when is judging?".

## Food (OpenStreetMap, within 8 km)
OSM coverage of Bhatkal is thin: only 4 tagged food places were found. Add the places the team actually eats at.

| Name | Type | Straight-line from AITM | What OSM says | Source | To fill / check |
|---|---|---|---|---|---|
| Mamu Chicken Bhatkal | restaurant | 1.4 km | name only | https://www.openstreetmap.org/node/8188054799 | still open? what to order, price range, veg options |
| Cafe Downtown | cafe | 2.1 km | Jali Road; hours "Mo-Th, Sa, Su 11:00-00:00; Fr 05:00-00:00" | https://www.openstreetmap.org/node/8007733599 | two OSM nodes exist (also node 8171395217, 2.2 km, cuisine burger, cake, chicken, coffee, donut, ice cream, hours "Sa-Th 11:00-00:00; Fr 05:00-00:00"). Same place or two branches? Hours disagree. |
| Lazeezo Fast Food & Chinese Cuisines | restaurant | 2.6 km | name only | https://www.openstreetmap.org/node/8188054773 | still open? price, veg |

## Food leads from articles (not places to list yet)
- **Bhatkali biryani** is the signature Navayath dish; rice and meat are served separately and mixed on the plate. Vegetarian Navayath dish: **saakuche** (mixed vegetables with coconut milk). Source: https://oteats.outlooktraveller.com/features/guides/a-closer-look-at-the-bhatkal-cuisine-of-the-navayath-muslims-of-karnataka
- **Bhatkal Super Halwa, Bunder Road**, known for handmade godi halwa (a writer's visit, article may be old). Source: https://www.deccanherald.com/lifestyle/travel/confluence-faiths-677840.html . Check if still there; good "take something home" tip for guests.
- Web search found no confirmed pure-veg restaurant in Bhatkal. **The team must add at least 2 veg options** for demo step 2, or the host will honestly refuse the veg part.
- Rejected: Alibaba Cafe and Big Daddy's Kitchen are Bhatkali restaurants in Bengaluru, not Bhatkal. Biryani Paradise and Royal Oak came only from an auto-generated itinerary site (layla.ai), not trustworthy.

## Travel (OpenStreetMap)
| Name | Straight-line from AITM | Source | To fill |
|---|---|---|---|
| KSRTC Bus Station, Bhatkal | 0.9 km | https://www.openstreetmap.org/node/1722528729 | auto fare, walking time, buses to Murudeshwar, Mangaluru, Udupi |
| Bhatkal railway station (Konkan Railway), NH66, Kokti | 1.0 km (13.98936, 74.56563) | https://www.openstreetmap.org/node/571579127 | auto fare and time, useful trains |

Distances computed from OSM coordinates; the station figure is approximate (about 1 km straight line). Verify by road.

## Not found yet
- ATMs, pharmacy, hospital, places to stay, beaches and sights: the OpenStreetMap query timed out (Overpass server at capacity). Retry later, or the team adds them from local knowledge.
- College phone numbers 08385-227212 and 226554 appear on a third-party listing (https://www.collegebatch.com/2519-anjuman-institute-of-technology-and-management-contact-number-address-map-bhatkal); prefer the official https://aitm.edu.in/contact/ page, which is already scraped.

## Schema reminder (BUILD.md 4.4)
`{"id","type":"food|travel|place|practical","name","what_to_order","price_range","distance_from_campus","veg_options","notes","last_checked","placeholder":false}`. Add `"source_url"` with the OSM link so the host can cite it.
