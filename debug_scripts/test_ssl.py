
import ssl
import certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import urllib.request

response = urllib.request.urlopen("https://www.google.com")
print(f"Success: {len(response.read())} bytes")