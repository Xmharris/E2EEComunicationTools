import sqlite3
from crawler import crawl_region

def main():
    conn = sqlite3.connect('na_meetings.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, website FROM regions')
    regions = cursor.fetchall()
    conn.close()

    print(f"Found {len(regions)} regions to crawl.")
    for r_id, website in regions:
        print(f"Starting crawl for {website} (Region ID: {r_id})")
        crawl_region(r_id, website)
    
    conn = sqlite3.connect('na_meetings.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM meetings')
    count = cursor.fetchone()[0]
    conn.close()
    print(f"Crawl complete. The database now contains {count} meetings.")

if __name__ == '__main__':
    main()
