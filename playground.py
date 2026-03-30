import json
import time
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import deque
from urllib.parse import urljoin, urlsplit

from blake3 import blake3
from bs4 import BeautifulSoup
import undetected_chromedriver as uc


CPD = Path(__file__).parent.parent.resolve()
data_path = CPD / "data"
raw_data_path = data_path / "raw_data"
raw_data_path.mkdir(exist_ok=True, parents=True)

xml_path = data_path / "sitemap.xml"
with open(xml_path, "r") as f:
    xml_data = f.read()

ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
root = ET.fromstring(xml_data)
initial_urls = [loc.text for loc in root.findall(".//sm:loc", ns)]

def normalize_url(url):
    split = urlsplit(url)
    return f"{split.scheme}://{split.netloc}{split.path}"

def is_useful_url(url):
    split = urlsplit(url)
    if split.netloc != target_domain:
        return False
    if not split.path.startswith("/docs/"):
        return False
    if "api-reference" in split.path:
        path_split = split.path.split("/")
        if len(path_split) > 3:
            return False
    return True


target_domain = "platform.openai.com"

queue = deque([normalize_url(u) for u in initial_urls if is_useful_url(normalize_url(u))])
visited = set(queue)

print(f"Starting crawl with {len(queue)} initial URLs")
chrome = uc.Chrome(use_subprocess=True, options=["--auto-open-devtools-for-tabs"])  # HEADFUL!

try:
    while queue:
        url = queue.popleft()
        url_hash = blake3(url.encode()).hexdigest()
        file_path = raw_data_path / f"{url_hash}.json"

        data: dict | None = None
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                print(f"Skipping Fetch for {url} (already exists)")
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

        if not data:
            print(f"Fetching {url}...")
            chrome.get(url)
            content = BeautifulSoup(chrome.page_source, "html.parser")
            
            if content is None:
                print(f"Failed to fetch {url} (Timeout or Error)")
                continue

            try:
                data = {
                    "url": url,
                    "raw": content.prettify(),
                    "title": content.find("title").text if content.find("title") else "No Title",
                    "body": content.find("body").text if content.find("body") else "No Body",
                    "hash": blake3(content.encode()).hexdigest(),
                }
                with open(file_path, "w") as f:
                    json.dump(data, f)
                print(f"Successfully fetched and saved {url}")
                time.sleep(random.uniform(1.0, 2.5))
            except Exception as e:
                print(f"Error processing content for {url}: {e}")
                continue

        soup = BeautifulSoup(data["raw"], "html.parser")
        for a in soup.find_all('a', href=True):
            full_url = urljoin(url, a['href'])
            norm_url = normalize_url(full_url)
            
            if norm_url not in visited and is_useful_url(norm_url):
                visited.add(norm_url)
                queue.append(norm_url)
                print(f"  Queued new URL: {norm_url}")

finally:
    chrome.quit()
