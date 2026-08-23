import urllib.request
import urllib.robotparser
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime

url = "https://itatonline.org/digest/youth-bar-association-of-india-v-uoi-air-2016-sc-4136-2016-9-scc-473-manu-sc-1339-2016-2/"

# Build the robots.txt URL from the target site itself, not hardcoded
parsed = urlparse(url)
robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

rp = urllib.robotparser.RobotFileParser()
rp.set_url(robots_url)
rp.read()

if not rp.can_fetch("*", url):
    print("BLOCKED by robots.txt — do not fetch this URL.")
else:
    print("Allowed by robots.txt — proceeding to fetch.")

    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    response = urllib.request.urlopen(req)
    html = response.read().decode('utf-8')

    print(f"Fetched {len(html)} characters.")

    # --- Parse HTML and extract the judgment text FIRST ---
    soup = BeautifulSoup(html, 'html.parser')
    content_div = soup.find('div', class_='post-entry')

    if content_div is None:
        print("Could not find the post-entry div — page structure may differ from expected.")
    else:
        judgment_text = content_div.get_text(separator='\n', strip=True)
        print(f"Extracted {len(judgment_text)} characters of judgment text (before cleaning).")

        # --- NOW strip boilerplate, since judgment_text actually exists at this point ---
        BOILERPLATE_STRINGS = [
            "\u201cWe want education by which character is formed, strength of mind is increased, "
            "the intellect is expanded and by which one can stand on one\u2019s feet.\u201d\nSWAMI VIVEKANANDA"
        ]

        def strip_boilerplate(text, boilerplate_list):
            for junk in boilerplate_list:
                text = text.replace(junk, "").strip()
            return text

        judgment_text = strip_boilerplate(judgment_text, BOILERPLATE_STRINGS)
        print(f"After stripping boilerplate: {len(judgment_text)} characters.")
        print(judgment_text)

        # --- Save with metadata ---
        def save_document(text, case_name, citation, court, source_url, source_type, output_dir="corpus"):
            """Save a retrieved document with metadata as a JSON record."""
            os.makedirs(output_dir, exist_ok=True)

            record = {
                "case_name": case_name,
                "citation": citation,
                "court": court,
                "source_url": source_url,
                "source_type": source_type,  # "primary" or "secondary"
                "retrieved_date": datetime.now().strftime("%Y-%m-%d"),
                "text": text
            }

            safe_filename = case_name.lower().replace(" ", "_").replace(".", "") + ".json"
            filepath = os.path.join(output_dir, safe_filename)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)

            print(f"Saved to {filepath}")
            return filepath

        save_document(
            text=judgment_text,
            case_name="Youth Bar Association v Union of India",
            citation="AIR 2016 SC 4136",
            court="Supreme Court of India",
            source_url=url,
            source_type="secondary"  # itatonline digest, not the primary transcript
        )