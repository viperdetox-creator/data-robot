"""The data robot: record the daily views of a few Wikipedia pages.

It reads page titles from pages.txt (one per line) and asks the Wikimedia
page-views API how many people read each page every day.

- First run (no pageviews.csv yet): it fetches the last 30 complete days.
  Three pages give 90 rows.
- Every later run: it adds only the days that are not in the file yet, up to
  yesterday (UTC). If the robot missed a day, the next run catches up.

The answer is saved in pageviews.csv, with the header date,page,views.

Run it in this folder:   python collect.py
GitHub Actions runs it every morning with daily.yml.

It uses only Python's standard library, so there is nothing to install.
Page-view data: Wikimedia Foundation, released under CC0 1.0.
"""

import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# ---- Settings ------------------------------------------------------------
# Change CONTACT to the address of YOUR data-robot repository.
# The script sends it with every request, so Wikimedia knows who is asking.
CONTACT = "github.com/viperdetox-creator/data-robot"
PROJECT = "en.wikipedia.org"     # English Wikipedia
PAGES_FILE = "pages.txt"         # the pages to follow, one title per line
OUTPUT_FILE = "pageviews.csv"    # where the views are saved
FIRST_RUN_DAYS = 30              # how many days a new page starts with

API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
HERE = Path(__file__).parent     # the folder this script is in
USER_AGENT = f"data-robot/1.0 ({CONTACT}) python-urllib/{sys.version_info.major}.{sys.version_info.minor}"


def read_pages():
    """Return the titles in pages.txt, skipping blank lines and repeated titles."""
    pages = []
    for line in open(HERE / PAGES_FILE, encoding="utf-8"):
        title = line.strip()
        if title and title not in pages:
            pages.append(title)
    return pages


def read_last_days():
    """Return {page: the last date saved for it} from pageviews.csv."""
    last_days = {}
    path = HERE / OUTPUT_FILE
    if not path.exists():
        return last_days
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            day = date.fromisoformat(row["date"])
            if row["page"] not in last_days or day > last_days[row["page"]]:
                last_days[row["page"]] = day
    return last_days


def fetch_views(title, first_day, last_day):
    """Ask the API for one page's daily views. Returns a list of (date, views).

    Returns None when the API answers 404: no data for this title and these dates.
    """
    address = (f"{API}/{PROJECT}/all-access/user/{urllib.parse.quote(title, safe='')}"
               f"/daily/{first_day:%Y%m%d}/{last_day:%Y%m%d}")
    request = urllib.request.Request(address, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    views = []
    for item in answer["items"]:
        # "timestamp" looks like 2026100100: year, month, day, then the hour 00.
        day = datetime.strptime(item["timestamp"][:8], "%Y%m%d").date()
        views.append((day, item["views"]))
    return views


def main():
    # Print titles in any alphabet without crashing on a Windows terminal.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if "your-username" in CONTACT:
        print("Please set CONTACT at the top of collect.py to your own repository, "
              "for example github.com/<username>/data-robot.")
        return 1

    pages = read_pages()
    if not pages:
        print(f"{PAGES_FILE} is empty. Add one Wikipedia title per line, such as Cricket_World_Cup.")
        return 1

    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    last_days = read_last_days()
    new_rows = []
    failed = False

    for title in pages:
        if "," in title:
            print(f"Note: {title} contains a comma. Week 1's chart code splits lines on commas, "
                  "so it will not read this page. Choose a title without a comma.")
        if title in last_days:
            first_day = last_days[title] + timedelta(days=1)   # the day after the last saved day
        else:
            first_day = yesterday - timedelta(days=FIRST_RUN_DAYS - 1)  # a new page: 30 days
        if first_day > yesterday:
            print(f"{title}: already up to date (last day {last_days[title]})")
            continue

        views = fetch_views(title, first_day, yesterday)
        if views is None and title not in last_days:
            print(f"No data for {title}: check the spelling in {PAGES_FILE}")
            failed = True
        elif not views:
            print(f"{title}: no new days published yet. Wikimedia adds a day's views "
                  "the day after; the next run will catch up.")
        else:
            for day, count in views:
                new_rows.append((day.isoformat(), title, count))
            print(f"{title}: {len(views)} days ({views[0][0]} to {views[-1][0]})")

        # (one request at a time: each request finishes before the next starts)

    # Save the new rows, oldest day first, after the rows already in the file.
    new_rows.sort(key=lambda row: (row[0], pages.index(row[1])))
    path = HERE / OUTPUT_FILE
    is_new_file = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if is_new_file:
            writer.writerow(["date", "page", "views"])
        writer.writerows(new_rows)
    print(f"Wrote {len(new_rows)} new rows to {OUTPUT_FILE}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
