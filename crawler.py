import requests
from bs4 import BeautifulSoup
import re
import urllib.parse
from database import insert_meeting

def check_bmlt_api(base_url):
    """
    Check if the site uses BMLT by trying the standard JSON endpoint.
    """
    if not base_url.startswith('http'):
        base_url = 'https://' + base_url
        
    api_url = urllib.parse.urljoin(base_url, '/client_interface/json/?switcher=GetSearchResults')
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0 and 'meeting_name' in data[0]:
                return data
    except Exception as e:
        pass
    
    return None

from google import genai
from google.genai import types
from pydantic import BaseModel
import json
import os

class Meeting(BaseModel):
    meeting_name: str
    day: str
    time: str
    address: str

class MeetingList(BaseModel):
    meetings: list[Meeting]

def extract_from_html(html, base_url):
    """
    Use Gemini 2.5 Flash to extract meeting data from the HTML text.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY environment variable not set. Skipping Gemini extraction.")
        return []
        
    client = genai.Client()
    soup = BeautifulSoup(html, 'html.parser')
    # Extract text to save tokens and remove noise, NA pages can be large
    text_content = soup.get_text(separator=' ', strip=True)
    
    prompt = f"You are a web scraper. Extract all Narcotics Anonymous (NA) meeting times, days, names, and locations from the following webpage text. Return it as a structured list of meetings. If you find no meetings, return an empty list."
    
    print("Calling Gemini to parse meetings...")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"{prompt}\n\nWebpage Text:\n{text_content[:100000]}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MeetingList,
                temperature=0.0
            ),
        )
        data = json.loads(response.text)
        # Gemini returns a dict matching the MeetingList schema
        meetings = data.get('meetings', [])
        # Format the output to match what the DB expects
        formatted_meetings = []
        for m in meetings:
            formatted_meetings.append({
                'meeting_name': m.get('meeting_name', 'Unknown'),
                'day': m.get('day', 'Unknown'),
                'time': m.get('time', 'Unknown'),
                'address': m.get('address', 'Unknown')
            })
        return formatted_meetings
    except Exception as e:
        print(f"Error during Gemini extraction: {e}")
        return []

def crawl_region(region_id, website_url):
    print(f"Crawling {website_url}...")
    
    # 1. Check BMLT first (Very common for NA websites)
    bmlt_data = check_bmlt_api(website_url)
    
    if bmlt_data:
        print(f"Found BMLT API data for {website_url}!")
        count = 0
        for m in bmlt_data:
            name = m.get('meeting_name', 'Unknown')
            day = m.get('weekday_tinyint', 'Unknown')
            time = m.get('start_time', 'Unknown')
            address = f"{m.get('location_text', '')} {m.get('location_street', '')} {m.get('location_city', '')}".strip()
            
            insert_meeting(region_id, name, day, time, address, website_url)
            count += 1
        print(f"Inserted {count} meetings via BMLT.")
        return
        
    # 2. If not BMLT, attempt to fetch homepage and find a meeting link
    if not website_url.startswith('http'):
        website_url = 'https://' + website_url
        
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'}
        
    try:
        response = requests.get(website_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for meeting links
        meeting_links = soup.find_all('a', href=re.compile(r'meeting|schedule|find', re.IGNORECASE))
        
        target_url = website_url
        for link in meeting_links:
            href = link.get('href')
            if href:
                target_url = urllib.parse.urljoin(website_url, href)
                break
                
        print(f"Extracting HTML from {target_url}...")
        res = requests.get(target_url, headers=headers, timeout=10)
        html_meetings = extract_from_html(res.text, target_url)
        
        count = 0
        for m in html_meetings:
            insert_meeting(region_id, m['meeting_name'], m['day'], m['time'], m['address'], target_url)
            count += 1
            
        print(f"Inserted {count} meetings via generic HTML fallback.")
        
    except Exception as e:
        print(f"Error crawling {website_url}: {e}")

if __name__ == '__main__':
    # Test
    # crawl_region(1, 'https://greaterlosangelesna.org')
    pass
