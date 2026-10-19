"""Synthetic TEST FIXTURES only. Fictional names and example.org URLs; never written to data/."""
from scraper.normalize import Record

FIXTURE_RECORDS: dict[str, list[Record]] = {
    "campus": [
        Record(id="campus-fx1", collection="campus", title="Fixture Institute library hours",
               text="The Fixture Institute central library is open from 8 am to 10 pm on weekdays and 9 am to 5 pm "
                    "on Saturdays. It is closed on Sundays. Visitors can get a day pass at the front desk.",
               source_url="https://example.org/fixture/library", last_checked="2026-10-19"),
        Record(id="campus-fx2", collection="campus", title="Fixture Institute robotics club",
               text="The robotics club at Fixture Institute meets every Wednesday at 5 pm in Lab 3. "
                    "They build line-following robots and drones and run a yearly workshop for first years.",
               source_url="https://example.org/fixture/robotics", last_checked="2026-10-19"),
    ],
    "achievements": [
        Record(id="ach-fx1", collection="achievements", title="Fixture team wins test hackathon",
               text="A Fixture Institute team won first prize at the Example Hackathon for an app that maps "
                    "wheelchair accessible routes on campus.",
               source_url="https://example.org/fixture/hackathon-win", last_checked="2026-10-19"),
    ],
}
