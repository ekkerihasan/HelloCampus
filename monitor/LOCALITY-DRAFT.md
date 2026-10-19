# Locality draft for the team to correct (NOT product data)

Researched by the monitor on 2026-10-19 from public sources. **Nothing here is verified on the ground.** A team member must check each entry, fill the blanks, and correct it. Only then does the builder copy it into `data/locality.json` with `"placeholder": false` and a fresh `last_checked`. Delete anything that is wrong or closed. Do not fill blanks by guessing.

Campus reference point: OpenStreetMap node 1709841585 "Anjuman Engineering College" (AITM), 13.99727, 74.55753, Anjumanabad, Bhatkal 581320. Distances below are straight-line from that point, not road distance.

Source for OSM rows: OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright). Link format: `https://www.openstreetmap.org/node/<id>`.

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
