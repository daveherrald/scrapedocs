#!/usr/bin/env python3
# Copyright 2025 Dave Herrald
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import requests
from bs4 import BeautifulSoup
import argparse
import html2text
import os
from urllib.parse import urljoin, urlparse
import time
import re
import hashlib

# --- Configuration ---
BASE_URL = "https://docs.sl.antimatter.io/"
timestamp = time.strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = "output"
OUTPUT_FILE = f"scrapedocs_{timestamp}.md"
IMAGES_DIR = "images"
TIMEOUT = 15
DELAY = 0.5

# IMPORTANT: This selector tells the script which part of the HTML to convert to Markdown.
# Modern documentation sites often wrap the main content in a <main> tag or a specific class.
# If the output files include the sidebar, header, or footer, you may need to inspect the
# site's HTML (using your browser's developer tools) and change this selector.
# Common alternatives: 'article', 'div.doc-content', 'div#main-content'
CONTENT_SELECTOR = "main" 

# --- Setup ---
session = requests.Session()
visited_urls = set()
urls_to_visit = [BASE_URL]

def is_valid(url):
    """Checks whether 'url' is a valid URL."""
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)

def is_internal_link(url):
    """Checks if the URL is part of the same domain and is a documentation path."""
    # 1. Check if the domain matches the base URL
    if urlparse(url).netloc != urlparse(BASE_URL).netloc:
        return False
        
    path = urlparse(url).path
    
    # 2. Filter out common file extensions that are not HTML pages
    if path.endswith(('.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.xml', '.rss', '.pdf', '.zip')):
        return False
        
    return True

def get_markdown_content(url, html_content):
    """Extracts main content and converts to markdown string."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Attempt to find the specified content area
        content_element = soup.select_one(CONTENT_SELECTOR)
        
        # Fallback if the specific selector yields nothing
        if not content_element:
             print(f"Warning: Selector '{CONTENT_SELECTOR}' not found for {url}. Falling back to 'body'.")
             content_element = soup.select_one("body")
             if not content_element:
                 print(f"Error: Could not find any content element for {url}.")
                 return
        
        # Resolve all relative links to absolute URLs (so they work in the offline doc)
        for a in content_element.find_all('a', href=True):
            a['href'] = urljoin(url, a['href'])

        images_fs_path = os.path.join(OUTPUT_DIR, IMAGES_DIR)
        # Create images directory if it doesn't exist
        if not os.path.exists(images_fs_path):
            os.makedirs(images_fs_path)

        # Download images and update src to local path
        for img in content_element.find_all('img', src=True):
            img_url = urljoin(url, img['src'])
            
            # Generate unique filename based on hash of URL
            img_hash = hashlib.md5(img_url.encode('utf-8')).hexdigest()
            path_parts = os.path.splitext(urlparse(img_url).path)
            ext = path_parts[1] if path_parts[1] else ".png"
            # Sanitize extension
            ext = re.sub(r'[^a-zA-Z0-9.]', '', ext)
            img_filename = f"{img_hash}{ext}"
            img_fs_path = os.path.join(images_fs_path, img_filename)
            img_rel_path = os.path.join(IMAGES_DIR, img_filename)

            # Download image if not already present
            if not os.path.exists(img_fs_path):
                try:
                    print(f"Downloading image: {img_url}")
                    r = session.get(img_url, stream=True, timeout=TIMEOUT)
                    if r.status_code == 200:
                        with open(img_fs_path, 'wb') as f:
                            for chunk in r.iter_content(1024):
                                f.write(chunk)
                except Exception as e:
                    print(f"Error downloading image {img_url}: {e}")
            
            # Update src to point to local file
            img['src'] = img_rel_path

        # Get a title for the filename
        title_tag = soup.find('title')
        page_title = title_tag.text if title_tag else "index"
        # Clean up the title by removing the site-wide suffix
        if '|' in page_title:
            page_title = page_title.split('|')[0].strip()
        
        # Convert the content to Markdown
        h = html2text.HTML2Text()
        h.body_width = 0  # Disable line wrapping

        # Remove zero-width space characters (U+200B) that render as 'â<80><8b>'
        # Also remove the mojibake sequence if encoding was guessed incorrectly
        cleaned_html = str(content_element).replace('\u200b', '').replace('\u00e2\u0080\u008b', '')
        markdown_content = h.handle(cleaned_html)
        
        # Add the original URL and title to the top
        return (f"# {page_title}\n\n[Original URL: {url}]\n\n---\n\n{markdown_content}\n\n", page_title)

    except Exception as e:
        print(f"An error occurred while processing {url}: {e}")
        return None

def scrape_docs():
    """Main scraping loop."""
    print(f"Starting crawl of {BASE_URL}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Output file: {OUTPUT_FILE}\n")
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    all_markdown_content = []
    toc_entries = []
    
    while urls_to_visit:
        url = urls_to_visit.pop(0)
        
        # Clean the URL to ignore fragments (like #section-anchor)
        base_url_only = urljoin(url, urlparse(url).path)
        
        if base_url_only in visited_urls:
            continue
        
        print(f"Processing link: {base_url_only}")
        visited_urls.add(base_url_only)
        
        try:
            # Use a User-Agent to mimic a browser
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = session.get(url, headers=headers, timeout=TIMEOUT)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            response.encoding = 'utf-8' # Force UTF-8 encoding
            
            # Save the current page content
            content_data = get_markdown_content(base_url_only, response.text)
            if content_data:
                content, title = content_data
                all_markdown_content.append(content)
                toc_entries.append(title)
            
            # Find new internal links to visit
            soup = BeautifulSoup(response.text, 'html.parser')
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                
                # Resolve relative URLs
                full_url = urljoin(BASE_URL, href)
                
                # Clean the URL for comparison (remove fragments)
                full_url_base = urljoin(full_url, urlparse(full_url).path)

                if is_internal_link(full_url_base) and full_url_base not in visited_urls:
                    if full_url_base not in urls_to_visit:
                        urls_to_visit.append(full_url_base)
                    
            # Be polite to the server by waiting briefly between requests
            time.sleep(DELAY) 

        except requests.exceptions.RequestException as e:
            print(f"Error fetching {base_url_only}: {e}")
            
    # Generate Table of Contents
    toc_lines = ["# Table of Contents\n"]
    for title in toc_entries:
        slug = re.sub(r'[^\w\s-]', '', title.lower()).strip().replace(' ', '-')
        toc_lines.append(f"* [{title}](#{slug})")

    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(toc_lines) + "\n\n---\n\n" + "\n".join(all_markdown_content))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape documentation sites to Markdown.")
    parser.add_argument("--url", default=BASE_URL, help="Base URL to scrape")
    parser.add_argument("--selector", default=CONTENT_SELECTOR, help="CSS selector for content")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Output Markdown filename")
    parser.add_argument("--images-dir", default=IMAGES_DIR, help="Images subdirectory name")
    parser.add_argument("--run-name", help="Custom name for the output subdirectory (overrides timestamp)")
    parser.add_argument("--append-to-timestamp", action="store_true", help="Append run-name to timestamp instead of replacing it")
    parser.add_argument("--timeout", type=int, default=TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--delay", type=float, default=DELAY, help="Delay between requests in seconds")
    
    args = parser.parse_args()
    
    BASE_URL = args.url
    CONTENT_SELECTOR = args.selector
    
    if args.run_name:
        if args.append_to_timestamp:
            subdir_name = f"{timestamp}_{args.run_name}"
        else:
            subdir_name = args.run_name
    else:
        subdir_name = timestamp

    OUTPUT_DIR = os.path.join(args.output_dir, subdir_name)
    OUTPUT_FILE = args.output
    IMAGES_DIR = args.images_dir
    TIMEOUT = args.timeout
    DELAY = args.delay
    
    # Reset urls_to_visit with the (possibly new) BASE_URL
    urls_to_visit = [BASE_URL]

    scrape_docs()
    print("\n--- Download complete ---")
    print(f"Documentation saved to '{OUTPUT_FILE}'.")