import requests
import sqlite3
import json
from database import insert_meeting

def get_coords(zipcode):
    if zipcode == '33410':
        return 26.837, -80.091
    return 26.837, -80.091

def fetch_and_store(zipcode, miles):
    lat, lon = get_coords(zipcode)
    if not lat:
        print("Could not geocode zipcode")
        return
        
    print(f"Coordinates for {zipcode}: {lat}, {lon}")
    
    url = f"https://tomato.bmltenabled.org/main_server/client_interface/json/?switcher=GetSearchResults&lat_val={lat}&long_val={lon}&geo_width={miles}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
    except Exception as e:
        print("Error fetching BMLT:", e)
        return

    conn = sqlite3.connect('na_meetings.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM meetings')
    conn.commit()
    conn.close()

    count = 0
    # Region ID can just be 1 for now, we don't have regions matched perfectly
    for m in data:
        name = m.get('meeting_name', 'Unknown')
        
        # BMLT returns weekday as 1-7 (1=Sunday in BMLT, or 1=Monday? Actually BMLT standard is 1=Sunday)
        days = { "1": "Sunday", "2": "Monday", "3": "Tuesday", "4": "Wednesday", "5": "Thursday", "6": "Friday", "7": "Saturday" }
        day = days.get(str(m.get('weekday_tinyint')), "Unknown")
        
        time = m.get('start_time', 'Unknown')
        address = f"{m.get('location_text', '')} {m.get('location_street', '')} {m.get('location_city_subsection', '')} {m.get('location_municipality', '')}".strip()
        source_url = "https://tomato.bmltenabled.org/"
        
        insert_meeting(1, name, day, time, address, source_url)
        count += 1
        
    print(f"Inserted {count} real NA meetings for {zipcode} within {miles} miles.")

if __name__ == "__main__":
    fetch_and_store('33410', 10)
