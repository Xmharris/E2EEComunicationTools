import argparse
import requests
from geopy.geocoders import Nominatim
from database import init_db, insert_region
from crawler import crawl_region

def geocode_zipcode(zipcode):
    """Convert a zipcode to latitude and longitude."""
    geolocator = Nominatim(user_agent="na_meeting_scraper_script")
    location = geolocator.geocode(f"{zipcode}, USA")
    if location:
        return location.latitude, location.longitude
    return None, None

def fetch_regional_websites(lat, lng, radius):
    """Query NA World Services API for regional websites."""
    url = "https://na.org/wp-content/plugins/meetings-finder/ajax.php"
    
    # Payload format based on NA website
    payload = {
        'action': 'search',
        'lat': str(lat),
        'lng': str(lng),
        'within': str(radius),
        'country': 'United States',  # Adjust if international needed
        'state': ''
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Referer': 'https://na.org/meetingsearch/find-na/'
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'success':
            return data.get('data', [])
        else:
            print("API returned failure status.")
            return []
    except Exception as e:
        print(f"Error fetching regional websites: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="NA Meetings Scraper")
    parser.add_argument("--zipcode", required=True, help="Zipcode to search from (e.g. 90210)")
    parser.add_argument("--radius", required=True, type=int, help="Search radius in miles (e.g. 10)")
    
    args = parser.parse_args()
    
    # 1. Initialize Database
    init_db()
    
    # 2. Geocode Zipcode
    print(f"Geocoding zipcode {args.zipcode}...")
    lat, lng = geocode_zipcode(args.zipcode)
    
    if not lat or not lng:
        print("Failed to geocode zipcode. Please try a different one.")
        return
        
    print(f"Coordinates: Lat {lat}, Lng {lng}")
    
    # 3. Fetch Regional Websites
    print(f"Fetching NA regions within {args.radius} miles...")
    regions = fetch_regional_websites(lat, lng, args.radius)
    
    if not regions:
        print("No regions found.")
        return
        
    print(f"Found {len(regions)} regions.")
    
    # 4. Process each region
    for region in regions:
        name = region.get('description', 'Unknown')
        website = region.get('website', '').strip()
        distance = region.get('distance', 0)
        
        if not website:
            print(f"Skipping {name}: No website listed.")
            continue
            
        print(f"\nProcessing Region: {name} ({distance:.2f} miles away)")
        print(f"URL: {website}")
        
        # Save region to DB
        region_id = insert_region(name, website, distance)
        
        # Crawl website for meetings
        crawl_region(region_id, website)
        
    print("\nScraping complete!")

if __name__ == "__main__":
    main()
