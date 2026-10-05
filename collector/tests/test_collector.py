"""Run with:  python -m unittest discover -s collector/tests -t ."""
import json
import os
import tempfile
import unittest

from collector.classify import classify, experience_min, sponsorship, skills
from collector.normalize import dup_key, employment_type, us_location

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def w2(text, emp="Not stated", direct=False):
    return classify("Data Engineer", text, emp, direct)["w2_status"]


class W2Rules(unittest.TestCase):
    def test_explicit_w2(self):
        self.assertEqual(w2("This is a W2 contract role"), "W2_CONFIRMED")
        self.assertEqual(w2("Candidates on W-2 only"), "W2_CONFIRMED")

    def test_w2_only_blocks_c2c(self):
        r = classify("Data Engineer", "W2 only, no C2C please", "Contract", False)
        self.assertEqual((r["w2_status"], r["c2c_status"]), ("W2_CONFIRMED", "NOT_ACCEPTED"))

    def test_c2c_only(self):
        self.assertEqual(w2("C2C only. 10 years experience"), "C2C_1099")
        self.assertEqual(w2("Open to corp-to-corp candidates"), "C2C_1099")
        self.assertEqual(w2("1099 independent contractor"), "C2C_1099")

    def test_c2c_negated_is_not_c2c(self):
        self.assertEqual(w2("No C2C. Contract role."), "UNKNOWN")
        self.assertEqual(w2("C2C is not accepted for this role"), "UNKNOWN")

    def test_w2_and_c2c_both(self):
        r = classify("Data Engineer", "W2 or C2C both fine", "Contract", False)
        self.assertEqual((r["w2_status"], r["c2c_status"]), ("W2_CONFIRMED", "ACCEPTED"))

    def test_contract_word_is_not_w2(self):
        self.assertEqual(w2("12 month contract in Dallas", "Contract"), "UNKNOWN")

    def test_direct_full_time(self):
        self.assertEqual(w2("Join our team.", "Full-time", direct=True), "DIRECT_FT")
        # same text from an aggregator must stay unknown
        self.assertEqual(w2("Join our team.", "Full-time", direct=False), "UNKNOWN")
        # contract wording on employer board is not Direct FT
        self.assertEqual(w2("Contractor position", "Full-time", direct=True), "UNKNOWN")

    def test_third_party_alone_is_not_c2c(self):
        self.assertEqual(w2("No third parties please"), "UNKNOWN")


class OtherFields(unittest.TestCase):
    def test_sponsorship(self):
        self.assertEqual(sponsorship("We are unable to sponsor visas")[0], "NOT_AVAILABLE")
        self.assertEqual(sponsorship("authorized to work without sponsorship now or in the future")[0], "NOT_AVAILABLE")
        self.assertEqual(sponsorship("USC/GC only")[0], "NOT_AVAILABLE")
        self.assertEqual(sponsorship("H-1B sponsorship available")[0], "AVAILABLE")
        self.assertEqual(sponsorship("Great benefits")[0], "UNKNOWN")

    def test_experience(self):
        self.assertEqual(experience_min("5+ years of experience with Spark"), 5)
        self.assertEqual(experience_min("Minimum of 3 years experience"), 3)
        self.assertEqual(experience_min("3-5 years of professional experience"), 3)
        self.assertEqual(experience_min("Five years of relevant experience"), 5)
        self.assertIsNone(experience_min("Founded 10 years ago"))

    def test_skills(self):
        s = skills("PySpark, NoSQL and Azure Data Factory; JavaScript")
        self.assertIn("PySpark", s)
        self.assertIn("ADF", s)
        self.assertNotIn("SQL", s)
        self.assertNotIn("Spark", s)
        self.assertNotIn("Java", s)

    def test_us_location(self):
        self.assertTrue(us_location("Dallas, TX"))
        self.assertTrue(us_location("Remote - US"))
        self.assertTrue(us_location("New York, NY; London"))
        self.assertFalse(us_location("Toronto, Canada"))
        self.assertIsNone(us_location("Remote"))

    def test_employment(self):
        self.assertEqual(employment_type("Contract", "Data Engineer", ""), "Contract")
        self.assertEqual(employment_type("", "Data Engineer", "contract to hire after 6 months"), "Contract-to-hire")
        self.assertEqual(employment_type("FullTime", "Data Engineer", ""), "Full-time")

    def test_dedupe_key(self):
        a = dup_key("Acme Analytics Inc.", "Sr. Data Engineer", "New York, NY", "On-site")
        b = dup_key("Acme Analytics", "Senior Data Engineer (Hybrid)", "Manhattan, NY", "Hybrid")
        self.assertEqual(a, b)
        c = dup_key("Acme Analytics", "Senior Data Engineer", "Austin, TX", "On-site")
        self.assertNotEqual(a, c)


class EndToEnd(unittest.TestCase):
    def test_fixture_run(self):
        from collector.run import main
        with tempfile.TemporaryDirectory() as d:
            main(["--fixtures", FIX, "--companies", os.path.join(FIX, "companies.csv"),
                  "--db", os.path.join(d, "jobs.db"), "--out", d])
            data = json.load(open(os.path.join(d, "jobs.json")))
            src = json.load(open(os.path.join(d, "sources.json")))["sources"]
            titles = [j["title"] for j in data["jobs"]]
            self.assertNotIn("Account Executive", titles)                 # not a DE title
            self.assertEqual(sum("Manager" in t for t in titles), 0)       # excluded title
            self.assertFalse(any("London" in j["location"] for j in data["jobs"]))
            acme = [j for j in data["jobs"] if j["title"] == "Senior Data Engineer"]
            self.assertEqual(len(acme), 1)                                 # deduped
            self.assertEqual(acme[0]["foundOn"], ["Adzuna", "Greenhouse"])
            self.assertIn("greenhouse.io", acme[0]["applyUrl"])           # employer link preferred
            self.assertTrue(src["SmartRecruiters"]["robotsBlocked"])
            self.assertIn("notarealboard", src["Greenhouse"]["failed"])
            # second run must not duplicate anything
            main(["--fixtures", FIX, "--companies", os.path.join(FIX, "companies.csv"),
                  "--db", os.path.join(d, "jobs.db"), "--out", d])
            again = json.load(open(os.path.join(d, "jobs.json")))
            self.assertEqual(len(again["jobs"]), len(data["jobs"]))


if __name__ == "__main__":
    unittest.main()
