# Curated news draft (NOT product data)

Prepared by the monitor on 2026-10-19 at the builder's request, after the user asked about AITM's LinkedIn page (https://www.linkedin.com/school/anjumanitm/).

## Position on LinkedIn
- **No automated scraping of LinkedIn.** It is ruled out three times over: CLAUDE.md ("Do not scrape LinkedIn, Instagram, login-walled pages"), BUILD.md section 7 non-goal ("LinkedIn or social scraping"), and LinkedIn's terms. The page is also login-walled, so a judge clicking a LinkedIn citation may hit a sign-in wall.
- **Allowed:** a team member reads AITM's public LinkedIn posts and copies **facts** by hand into a curated file, the same way as locality. **Prefer a public, no-login URL** for each fact (aitm.edu.in first). Use the LinkedIn post URL only when no public source exists.
- The monitor agrees with the builder; the non-goal does not need to change. See REVIEW.md.

## Step 1 (no human work needed): official AITM news pages, not yet scraped
`https://aitm.edu.in/news/` lists 9 public articles; `scraper/sources.yaml` has only the cricket one. robots.txt allows `/news/`. These should be **scraped** (builder, add to `achievements` or `campus` in sources.yaml), not curated:

| URL | Title on page | Date on page | Suggested collection |
|---|---|---|---|
| https://aitm.edu.in/news/aitm-cricket/ | AITM Cricket | September 06, 2025 | achievements (already scraped) |
| https://aitm.edu.in/news/stem-2024/ | STEM 2024 | September 06, 2025 | campus (event) |
| https://aitm.edu.in/news/mba-background/ | MBA-Background | November 17, 2024 | campus |
| https://aitm.edu.in/news/human-chain-program/ | Participation in Todays Human Chain Program | September 17, 2024 | campus (event) |
| https://aitm.edu.in/news/aitm-placements/ | AITM PLACEMENTS 2024 | August 24, 2024 | achievements |
| https://aitm.edu.in/news/aitms-ihab-ruknuddin-clinches-first-place-in-national-karate-championship/ | Ihab Ruknuddin Wins National Karate Championship | August 24, 2024 | achievements, **see privacy note** |
| https://aitm.edu.in/news/aitm-celebrates-78th-independence-day/ | AITM Celebrates 78th Independence Day | August 15, 2024 | campus (event) |
| https://aitm.edu.in/news/kea-unfilled-vacant-seats-2023-24/ | KEA Unfilled Vacant Seats 2023-24 | October 27, 2023 | skip (stale admissions notice) |
| https://aitm.edu.in/news/news/ | News | August 15, 2024 | skip (index-like page, check content first) |

Titles and dates were read from each page's `<title>` and first date string on 2026-10-19.

**Privacy note (team decision):** the karate article names a student. CLAUDE.md says "Only opt-in students reachable through any endpoint", meaning student data in hiring. A public college news item about a sports win is institutional news, but to stay safe either (a) the team confirms the student is fine being mentioned, or (b) ingest it into `achievements` only and make sure hiring never surfaces non-opt-in names. Same rule for any LinkedIn post that names students.

## Step 2: independent public coverage (searched, little found)
- Web searches for AITM Bhatkal awards, hackathons and events (2025 and 2026) found only admission and profile listings (Collegedunia, Careers360), no news coverage. Local outlets (Sahil Online, Daijiworld, Coastal Digest) returned nothing specific.
- **Acronym trap:** many "AITM" achievement results belong to **Angadi Institute of Technology and Management, Belagavi** (aitmbgm.ac.in), for example Techathon 3.0 Top 25 (Feb 2026), Ideathon 2025 first prize, Buildathon-2K25 5th place. **None of these are about AITM Bhatkal. Do not curate them.** Anything copied from LinkedIn must be from the `anjumanitm` page itself.

## Step 3: template for facts copied by hand from AITM's public LinkedIn posts
Fill one row per fact. Leave the row out if you cannot verify it. The builder ingests only rows with `placeholder: false`.

```json
{"id": "news-001", "collection": "achievements", "title": "", "date": "YYYY-MM-DD",
 "fact": "one or two plain sentences, no adjectives the post does not use",
 "source_url": "public URL if one exists, else the LinkedIn post URL",
 "names_students": false, "student_consent_checked": false,
 "last_checked": "2026-10-19", "placeholder": true}
```

Good candidates to look for in the LinkedIn feed: hackathon or competition wins, industry visits, MoUs with companies, guest lectures by named organisations, placement drives (company and number placed), fests and their dates. Skip anything about individual students unless they are opt-in or the team confirms consent.
