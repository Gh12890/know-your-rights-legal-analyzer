import ssl
import certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import requests
from urllib.parse import urlparse
import urllib.robotparser
import os
import fitz

url = "https://egazette.gov.in/WriteReadData/2023/250883.pdf"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

parsed = urlparse(url)
robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

try:
    robots_response = requests.get(robots_url, headers=headers, timeout=15)
except requests.exceptions.SSLError:
    robots_response = requests.get(robots_url, headers=headers, timeout=15, verify=False)

rp = urllib.robotparser.RobotFileParser()

if robots_response.status_code == 404:
    print("No robots.txt found on this domain — treated as no restrictions declared.")
    rp.parse([])
else:
    rp.parse(robots_response.text.splitlines())

if not rp.can_fetch("*", url):
    print("BLOCKED by robots.txt — do not fetch this URL.")
else:
    print("Allowed by robots.txt — proceeding to fetch.")

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        pdf_bytes = response.content
    except requests.exceptions.SSLError:
        print("requests also hit an SSL error on the PDF itself — retrying with verification disabled.")
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        response.raise_for_status()
        pdf_bytes = response.content

    print(f"Downloaded {len(pdf_bytes)} bytes.")

    os.makedirs("raw_pdfs", exist_ok=True)
    pdf_path = os.path.join("raw_pdfs", "bns_2023_gazette.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Saved raw PDF to {pdf_path}")

    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()

    print(f"Extracted {len(text)} characters from {pdf_path}.")
    print(text[:1000])