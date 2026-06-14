import sqlite3
from database import insert_meeting

meetings = [
    # Hollywood Region (1)
    (1, "Hollywood Recovery Group", "Monday", "19:00", "123 Sunset Blvd, Hollywood, CA", "https://hollywoodna.org/"),
    (1, "Morning Serenity", "Tuesday", "07:00", "456 Vine St, Hollywood, CA", "https://hollywoodna.org/"),
    (1, "Steps to Freedom", "Wednesday", "20:00", "789 Santa Monica Blvd, Hollywood, CA", "https://hollywoodna.org/"),
    (1, "Hollywood Newcomers", "Thursday", "18:30", "101 Cahuenga Blvd, Hollywood, CA", "https://hollywoodna.org/"),
    (1, "Friday Night Lights", "Friday", "21:00", "202 Melrose Ave, Hollywood, CA", "https://hollywoodna.org/"),
    
    # Westside Region (2)
    (2, "Westside Miracles", "Monday", "12:00", "300 Ocean Ave, Santa Monica, CA", "https://westsidena.org/"),
    (2, "Santa Monica Serenity", "Wednesday", "19:30", "400 Wilshire Blvd, Santa Monica, CA", "https://westsidena.org/"),
    (2, "Venice Beach Recovery", "Friday", "18:00", "500 Boardwalk, Venice, CA", "https://westsidena.org/"),
    (2, "Weekend Warriors", "Saturday", "10:00", "600 Lincoln Blvd, Santa Monica, CA", "https://westsidena.org/"),
    (2, "Sunday Spiritual", "Sunday", "09:00", "700 Pico Blvd, Santa Monica, CA", "https://westsidena.org/"),

    # San Fernando Valley Region (3)
    (3, "Valley Hope", "Tuesday", "19:00", "800 Ventura Blvd, Sherman Oaks, CA", "https://www.nasfv.com/"),
    (3, "SFV Steps and Traditions", "Thursday", "20:00", "900 Sepulveda Blvd, Van Nuys, CA", "https://www.nasfv.com/"),
    (3, "Burbank Basics", "Friday", "18:30", "1000 Magnolia Blvd, Burbank, CA", "https://www.nasfv.com/"),
    (3, "Northridge Nooners", "Monday", "12:00", "1100 Reseda Blvd, Northridge, CA", "https://www.nasfv.com/"),
    (3, "Glendale Gratitude", "Sunday", "17:00", "1200 Brand Blvd, Glendale, CA", "https://www.nasfv.com/")
]

def main():
    conn = sqlite3.connect('na_meetings.db')
    cursor = conn.cursor()
    # Clear existing meetings
    cursor.execute('DELETE FROM meetings')
    conn.commit()
    conn.close()

    count = 0
    for m in meetings:
        insert_meeting(*m)
        count += 1
    
    print(f"Successfully populated database with {count} NA meetings.")

if __name__ == "__main__":
    main()
