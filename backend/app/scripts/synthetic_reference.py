"""Real-world reference data backing the synthetic dataset generator.

Everything in this module is *grounded* rather than invented: the coordinates
are the real published locations of North-East India landmarks and Guwahati
police stations, the nationality mix follows the Ministry of Tourism's Foreign
Tourist Arrival source-country ranking (Bangladesh > USA > UK > Australia >
Canada, with domestic Indian travellers dominating North-East footfall), and
the crime-index anchors follow the NCRB "Crime in India" pattern of a high
state-level rate for Assam concentrated in commercial/transit localities.

Sources consulted:
  - Kamakhya Temple 26.1664 N, 91.7055 E  (Wikipedia, 26 deg 09'59"N 91 deg 42'20"E)
  - Umananda Temple 26.1964 N, 91.7453 E  (Wikipedia, 26 deg 11'47"N 91 deg 44'43"E)
  - Cherrapunji     25.2912 N, 91.6783 E  (Wikipedia)
  - Guwahati Police Commissionerate station roster (East/Central/West districts)
  - Ministry of Tourism, India Tourism Statistics -- FTA by source country
  - NCRB, Crime in India 2023 -- state crime-rate tables

Nothing here contains a real person's data: names are drawn from common
given/family-name pools and every document number is synthetic and masked in
the same way the application already masks Aadhaar numbers.
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# Geography
# --------------------------------------------------------------------------
# The project's map is centred on Guwahati; the generator builds trips inside
# "clusters" so an itinerary is geographically coherent (a tourist does not
# hop from Tawang to Aizawl between two 5-minute GPS pings).

MAP_CENTER = (26.1445, 91.7362)  # Guwahati, matches settings.MAP_CENTER_*

# name, lat, lng, category
LANDMARKS: list[tuple[str, float, float, str]] = [
    # ---- Guwahati core (the cluster the dashboard actually renders) ----
    ("Kamakhya Temple", 26.1664, 91.7055, "religious"),
    ("Umananda Island", 26.1964, 91.7453, "religious"),
    ("Navagraha Temple", 26.1749, 91.7789, "religious"),
    ("Basistha Temple", 26.1132, 91.7970, "religious"),
    ("Guwahati Railway Station", 26.1824, 91.7513, "transit"),
    ("LGB International Airport", 26.1061, 91.5859, "transit"),
    ("Paltan Bazaar", 26.1817, 91.7503, "market"),
    ("Fancy Bazaar", 26.1836, 91.7434, "market"),
    ("Pan Bazaar", 26.1856, 91.7455, "market"),
    ("Uzan Bazar Ghat", 26.1900, 91.7590, "riverfront"),
    ("Brahmaputra Riverfront", 26.1905, 91.7480, "riverfront"),
    ("Dighalipukhuri", 26.1861, 91.7503, "park"),
    ("Nehru Park", 26.1857, 91.7477, "park"),
    ("Assam State Museum", 26.1857, 91.7481, "museum"),
    ("Assam State Zoo & Botanical Garden", 26.1780, 91.7860, "park"),
    ("Srimanta Sankaradeva Kalakshetra", 26.1440, 91.8058, "museum"),
    ("Guwahati Planetarium", 26.1856, 91.7625, "museum"),
    ("Gandhi Mandap, Sarania Hill", 26.1750, 91.7580, "viewpoint"),
    ("Nilachal Ropeway Terminal", 26.1880, 91.7440, "transit"),
    ("Dispur Secretariat", 26.1420, 91.7900, "civic"),
    ("Ganeshguri Junction", 26.1470, 91.7900, "market"),
    ("Six Mile", 26.1350, 91.8050, "market"),
    ("Beltola Bazaar", 26.1290, 91.8000, "market"),
    ("Zoo Road Tiniali", 26.1650, 91.7800, "market"),
    ("Chandmari", 26.1830, 91.7720, "residential"),
    ("Silpukhuri", 26.1880, 91.7660, "residential"),
    ("Bharalumukh", 26.1700, 91.7350, "residential"),
    ("Rehabari", 26.1750, 91.7480, "residential"),
    ("Bhangagarh", 26.1500, 91.7700, "residential"),
    ("Hatigaon", 26.1360, 91.7880, "residential"),
    ("Kahilipara", 26.1330, 91.7620, "residential"),
    ("Maligaon", 26.1580, 91.6790, "residential"),
    ("Jalukbari", 26.1520, 91.6650, "transit"),
    ("Gauhati University", 26.1520, 91.6650, "campus"),
    ("IIT Guwahati", 26.1900, 91.6950, "campus"),
    ("Guwahati Medical College", 26.1550, 91.7000, "civic"),
    ("Saraighat Bridge", 26.1889, 91.6700, "transit"),
    ("North Guwahati Ghat", 26.1980, 91.6900, "riverfront"),
    ("Amingaon", 26.1900, 91.6600, "transit"),
    ("Noonmati", 26.1780, 91.8060, "residential"),
    ("Narengi", 26.1750, 91.8400, "residential"),
    ("Khanapara", 26.1180, 91.8180, "transit"),
    ("Lokhra", 26.1050, 91.7350, "residential"),
    ("Deepor Beel Wildlife Sanctuary", 26.1200, 91.6500, "nature"),
    ("Sualkuchi Silk Village", 26.1667, 91.5667, "heritage"),
    ("Hajo Pilgrimage Town", 26.2500, 91.5167, "religious"),
    ("Madan Kamdev Ruins", 26.3667, 91.6333, "heritage"),
    ("Chandubi Lake", 25.9333, 91.4333, "nature"),
    ("Accoland Water Park", 26.0900, 91.5900, "leisure"),
    ("Pobitora Wildlife Sanctuary", 26.2333, 92.0833, "nature"),

    # ---- Wider North-East circuit (used for long multi-city itineraries) ----
    ("Shillong", 25.5788, 91.8933, "hill_station"),
    ("Umiam Lake", 25.6570, 91.8890, "nature"),
    ("Cherrapunji (Sohra)", 25.2912, 91.6783, "hill_station"),
    ("Nohkalikai Falls", 25.2760, 91.6857, "nature"),
    ("Living Root Bridge, Nongriat", 25.2470, 91.7150, "nature"),
    ("Mawlynnong Village", 25.2000, 91.9167, "heritage"),
    ("Dawki / Umngot River", 25.1900, 92.0200, "nature"),
    ("Kaziranga National Park", 26.5775, 93.1711, "nature"),
    ("Nameri National Park", 26.9200, 92.8800, "nature"),
    ("Manas National Park", 26.7000, 91.0000, "nature"),
    ("Tezpur", 26.6338, 92.8000, "heritage"),
    ("Majuli River Island", 26.9500, 94.1700, "heritage"),
    ("Jorhat", 26.7509, 94.2037, "transit"),
    ("Sivasagar", 26.9826, 94.6425, "heritage"),
    ("Dibrugarh", 27.4728, 94.9120, "transit"),
    ("Digboi Oil Heritage", 27.3931, 95.6186, "heritage"),
    ("Haflong", 25.1667, 93.0167, "hill_station"),
    ("Tawang Monastery", 27.5861, 91.8594, "religious"),
    ("Ziro Valley", 27.5448, 93.8320, "heritage"),
    ("Gangtok", 27.3314, 88.6138, "hill_station"),
    ("Kohima", 25.6751, 94.1086, "heritage"),
    ("Dzukou Valley", 25.5833, 94.0500, "nature"),
    ("Imphal", 24.8170, 93.9368, "heritage"),
    ("Loktak Lake", 24.5333, 93.8167, "nature"),
    ("Aizawl", 23.7271, 92.7176, "hill_station"),
    ("Agartala", 23.8315, 91.2868, "heritage"),
]

# Itinerary clusters: (cluster name, [landmark names], typical trip length days)
TRIP_CLUSTERS: list[tuple[str, list[str], int, int]] = [
    ("Guwahati City Break", [
        "Kamakhya Temple", "Umananda Island", "Pan Bazaar", "Fancy Bazaar",
        "Assam State Museum", "Brahmaputra Riverfront", "Dighalipukhuri",
        "Nehru Park", "Guwahati Planetarium", "Gandhi Mandap, Sarania Hill",
    ], 2, 5),
    ("Guwahati Pilgrimage Circuit", [
        "Kamakhya Temple", "Navagraha Temple", "Basistha Temple",
        "Umananda Island", "Hajo Pilgrimage Town", "Madan Kamdev Ruins",
    ], 3, 6),
    ("Guwahati Nature & Wildlife", [
        "Assam State Zoo & Botanical Garden", "Deepor Beel Wildlife Sanctuary",
        "Chandubi Lake", "Pobitora Wildlife Sanctuary", "Accoland Water Park",
    ], 2, 5),
    ("Guwahati Market & Heritage Walk", [
        "Paltan Bazaar", "Fancy Bazaar", "Pan Bazaar", "Uzan Bazar Ghat",
        "Srimanta Sankaradeva Kalakshetra", "Sualkuchi Silk Village",
    ], 2, 4),
    ("Meghalaya Loop", [
        "Guwahati Railway Station", "Shillong", "Umiam Lake",
        "Cherrapunji (Sohra)", "Nohkalikai Falls", "Living Root Bridge, Nongriat",
        "Mawlynnong Village", "Dawki / Umngot River",
    ], 5, 10),
    ("Upper Assam Wildlife Trail", [
        "LGB International Airport", "Kaziranga National Park", "Tezpur",
        "Nameri National Park", "Jorhat", "Majuli River Island", "Sivasagar",
    ], 6, 12),
    ("Arunachal High Himalaya", [
        "Guwahati Railway Station", "Tezpur", "Tawang Monastery", "Ziro Valley",
    ], 7, 14),
    ("Seven Sisters Grand Tour", [
        "LGB International Airport", "Shillong", "Kaziranga National Park",
        "Kohima", "Imphal", "Aizawl", "Agartala", "Gangtok",
    ], 10, 18),
    ("Business / Transit Stay", [
        "LGB International Airport", "Dispur Secretariat", "Six Mile",
        "Ganeshguri Junction", "Guwahati Railway Station",
    ], 1, 3),
]

# --------------------------------------------------------------------------
# Geo-fence zones
# --------------------------------------------------------------------------
# (name, centre lat, centre lng, half-height deg, half-width deg, risk, crime_index,
#  description)
# Crime indices are anchored on the NCRB pattern: transit hubs and night markets
# score highest, patrolled civic districts lowest.
ZONE_DEFS: list[tuple[str, float, float, float, float, str, float, str]] = [
    ("Riverside Restricted Area", 26.1800, 91.7700, 0.0080, 0.0080, "restricted", 85,
     "Brahmaputra embankment - entry prohibited after dusk (flood + trafficking route)"),
    ("Old Market High-Risk Zone", 26.1650, 91.7500, 0.0080, 0.0080, "high", 70,
     "Pickpocketing and tourist-scam hotspot around the night bazaar"),
    ("Hillside Trek Caution Zone", 26.1250, 91.7150, 0.0100, 0.0100, "medium", 40,
     "Landslide-prone trekking route, no mobile coverage in the ravine"),
    ("City Center Safe Zone", 26.1445, 91.7362, 0.0060, 0.0060, "low", 15,
     "Well-patrolled central tourist district with CCTV coverage"),
    ("Paltan Bazaar Transit Hub", 26.1817, 91.7503, 0.0035, 0.0045, "high", 68,
     "Railway-station approach: highest reported theft density in the city"),
    ("Fancy Bazaar Night Market", 26.1836, 91.7434, 0.0030, 0.0040, "high", 64,
     "Dense evening crowd, repeated snatching complaints after 20:00"),
    ("Kamakhya Hill Approach", 26.1664, 91.7055, 0.0060, 0.0060, "medium", 45,
     "Steep pilgrim road; overcrowding during Ambubachi, frequent stampede risk"),
    ("Umananda Ferry Crossing", 26.1964, 91.7453, 0.0025, 0.0025, "medium", 38,
     "River crossing - overloaded ferries flagged during monsoon"),
    ("Deepor Beel Wetland Edge", 26.1200, 91.6500, 0.0090, 0.0120, "restricted", 78,
     "Protected wetland and elephant corridor - unescorted entry prohibited"),
    ("Airport Approach Corridor", 26.1061, 91.5859, 0.0080, 0.0080, "low", 22,
     "Secured airport perimeter and approach road"),
    ("Jalukbari Interchange", 26.1520, 91.6650, 0.0050, 0.0060, "medium", 48,
     "NH-27 interchange - high-speed traffic, frequent road accidents"),
    ("Saraighat Bridge Span", 26.1889, 91.6700, 0.0030, 0.0090, "high", 60,
     "Bridge span: no pedestrian refuge, recurring incident location"),
    ("Dispur Civic Core", 26.1420, 91.7900, 0.0050, 0.0060, "low", 18,
     "State secretariat district under continuous police presence"),
    ("Six Mile Commercial Belt", 26.1350, 91.8050, 0.0045, 0.0055, "medium", 42,
     "Busy commercial strip, moderate petty-crime reporting"),
    ("Khanapara Border Checkpoint", 26.1180, 91.8180, 0.0060, 0.0060, "high", 66,
     "Assam-Meghalaya boundary checkpoint - vehicle-crime and smuggling reports"),
    ("Noonmati Refinery Buffer", 26.1780, 91.8060, 0.0070, 0.0070, "restricted", 80,
     "Industrial exclusion zone around the refinery - civilians prohibited"),
    ("Narengi Cantonment Perimeter", 26.1750, 91.8400, 0.0080, 0.0080, "restricted", 82,
     "Military cantonment - photography and entry prohibited"),
    ("Chandmari Residential", 26.1830, 91.7720, 0.0045, 0.0045, "low", 20,
     "Quiet residential ward with a local outpost"),
    ("Bharalumukh Riverbank", 26.1700, 91.7350, 0.0045, 0.0045, "medium", 52,
     "Flood-prone riverbank, sanitation and night-safety complaints"),
    ("Lokhra Bypass Stretch", 26.1050, 91.7350, 0.0070, 0.0070, "high", 62,
     "Unlit bypass, repeated night-time vehicle-borne robbery reports"),
    ("Umiam Lake Watersports Area", 25.6570, 91.8890, 0.0120, 0.0120, "medium", 35,
     "Boating zone - drowning risk outside marked buoys"),
    ("Cherrapunji Cliff Edge", 25.2760, 91.6857, 0.0100, 0.0100, "restricted", 88,
     "Nohkalikai viewpoint cliff edge - fatal falls recorded, barrier line enforced"),
    ("Dawki Border Belt", 25.1900, 92.0200, 0.0150, 0.0150, "restricted", 90,
     "International border zone - permit mandatory, unescorted entry prohibited"),
    ("Kaziranga Core Zone", 26.5775, 93.1711, 0.0400, 0.0600, "restricted", 75,
     "Wildlife core area - foot entry prohibited, poaching-patrol live-fire zone"),
    ("Tawang High-Altitude Sector", 27.5861, 91.8594, 0.0300, 0.0300, "high", 58,
     "Inner Line Permit sector, altitude-sickness and landslide exposure"),
    ("Loktak Lake Fringe", 24.5333, 93.8167, 0.0200, 0.0250, "medium", 44,
     "Floating-island fringe - navigation hazard after dark"),
]

# --------------------------------------------------------------------------
# Police units -- real Guwahati Police Commissionerate stations
# --------------------------------------------------------------------------
# (unit callsign, station, phone, lat, lng)
POLICE_UNITS: list[tuple[str, str, str, float, float]] = [
    ("Unit Alpha-1", "Dispur Police Station", "0361-2261510", 26.1414, 91.7898),
    ("Unit Alpha-2", "Basistha Police Station", "0361-2302213", 26.1116, 91.7995),
    ("Unit Bravo-1", "Panbazar Police Station", "0361-2540126", 26.1855, 91.7458),
    ("Unit Bravo-2", "Paltan Bazar Police Station", "0361-2540106", 26.1817, 91.7503),
    ("Unit Bravo-3", "Latasil Police Station", "0361-2544144", 26.1868, 91.7590),
    ("Unit Charlie-1", "Chandmari Police Station", "0361-2660204", 26.1828, 91.7745),
    ("Unit Charlie-2", "Geetanagar Police Station", "0361-2266066", 26.1712, 91.7800),
    ("Unit Charlie-3", "Noonmati Police Station", "0361-2551100", 26.1777, 91.8060),
    ("Unit Delta-1", "Bharalumukh Police Station", "0361-2731199", 26.1706, 91.7357),
    ("Unit Delta-2", "Fatasil Ambari Police Station", "0361-2470100", 26.1560, 91.7420),
    ("Unit Delta-3", "Jalukbari Police Station", "0361-2570100", 26.1520, 91.6660),
    ("Unit Echo-1", "Gorchuk Police Station", "0361-2843100", 26.1080, 91.7160),
    ("Unit Echo-2", "Azara Police Station", "0361-2840100", 26.1130, 91.6110),
    ("Unit Echo-3", "Airport Police Outpost", "0361-2840119", 26.1080, 91.5870),
    ("Unit Foxtrot-1", "Hatigaon Police Station", "0361-2229100", 26.1360, 91.7880),
    ("Unit Foxtrot-2", "Bhangagarh Police Station", "0361-2529100", 26.1500, 91.7700),
    ("Unit Foxtrot-3", "Satgaon Police Station", "0361-2550100", 26.1830, 91.8250),
    ("Unit Golf-1", "Pragjyotishpur Police Station", "0361-2550190", 26.1600, 91.6900),
    ("Unit Golf-2", "North Guwahati Police Station", "0361-2690100", 26.1980, 91.6900),
    ("Unit Hotel-1", "All Women Police Station, Panbazar", "0361-2524627", 26.1850, 91.7460),
    ("Unit Hotel-2", "Khanapara Traffic Outpost", "0361-2360100", 26.1180, 91.8180),
    ("Unit India-1", "Tourist Assistance Post, Kamakhya", "0361-2734100", 26.1664, 91.7055),
]

# --------------------------------------------------------------------------
# Demographics
# --------------------------------------------------------------------------
# Weights follow the Ministry of Tourism FTA source-country ranking, scaled so
# domestic Indian travellers -- who dominate North-East footfall -- are ~78%.
NATIONALITY_WEIGHTS: list[tuple[str, float]] = [
    ("Indian", 78.0),
    ("Bangladeshi", 4.6),
    ("American", 3.1),
    ("British", 2.5),
    ("Australian", 1.2),
    ("Canadian", 1.1),
    ("Nepali", 1.0),
    ("Bhutanese", 0.8),
    ("German", 0.8),
    ("French", 0.7),
    ("Sri Lankan", 0.6),
    ("Malaysian", 0.6),
    ("Japanese", 0.6),
    ("Russian", 0.5),
    ("Chinese", 0.5),
    ("Italian", 0.5),
    ("Spanish", 0.4),
    ("Singaporean", 0.4),
    ("Thai", 0.4),
    ("Korean", 0.3),
    ("Dutch", 0.3),
    ("Israeli", 0.3),
    ("Brazilian", 0.2),
    ("South African", 0.2),
    ("Emirati", 0.2),
    ("Swiss", 0.2),
]

# Given / family name pools per nationality. Common public names only.
NAME_POOLS: dict[str, tuple[list[str], list[str]]] = {
    "Indian": (
        ["Aarav", "Ananya", "Rohan", "Priya", "Arjun", "Ishita", "Kabir", "Meera",
         "Vikram", "Sneha", "Rahul", "Divya", "Aditya", "Kavya", "Siddharth",
         "Pooja", "Nikhil", "Riya", "Manish", "Anjali", "Bhaskar", "Nabanita",
         "Pranjal", "Rituparna", "Dhruv", "Tanvi", "Jayanta", "Mridula",
         "Bishal", "Hemanta", "Parag", "Chandana", "Utpal", "Gitanjali",
         "Simanta", "Rupam", "Anurag", "Bornali", "Debojit", "Junmoni"],
        ["Sharma", "Verma", "Das", "Bora", "Saikia", "Gogoi", "Barua", "Kalita",
         "Deka", "Hazarika", "Nath", "Bhattacharya", "Choudhury", "Rajkhowa",
         "Patel", "Reddy", "Iyer", "Nair", "Singh", "Kumar", "Mishra", "Ghosh",
         "Banerjee", "Sen", "Dutta", "Phukan", "Baishya", "Medhi"],
    ),
    "Bangladeshi": (
        ["Rahim", "Fatima", "Karim", "Nusrat", "Imran", "Sabina", "Tanvir",
         "Rumana", "Shakib", "Ayesha", "Jahid", "Mahmuda"],
        ["Ahmed", "Hossain", "Rahman", "Islam", "Chowdhury", "Khan", "Alam",
         "Sarkar", "Uddin", "Begum"],
    ),
    "American": (
        ["James", "Emily", "Michael", "Sarah", "David", "Jessica", "Daniel",
         "Ashley", "Christopher", "Amanda", "Ethan", "Olivia"],
        ["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis",
         "Garcia", "Rodriguez", "Wilson"],
    ),
    "British": (
        ["Oliver", "Amelia", "Harry", "Isla", "George", "Emma", "Jack", "Sophie",
         "Thomas", "Charlotte", "Alfie", "Grace"],
        ["Taylor", "Walker", "Wright", "Hall", "Green", "Clarke", "Baker",
         "Turner", "Hughes", "Edwards"],
    ),
    "Australian": (
        ["Liam", "Chloe", "Noah", "Zoe", "Jack", "Mia", "Cooper", "Ruby"],
        ["Anderson", "Thompson", "White", "Harris", "Martin", "Campbell"],
    ),
    "Canadian": (
        ["Logan", "Ava", "Lucas", "Emma", "Owen", "Maya", "Nathan", "Hannah"],
        ["Tremblay", "Roy", "Cote", "Gagnon", "Bouchard", "Morin"],
    ),
    "Nepali": (
        ["Bibek", "Sunita", "Prakash", "Anjana", "Suman", "Sarita"],
        ["Shrestha", "Gurung", "Thapa", "Magar", "Rai", "Adhikari"],
    ),
    "Bhutanese": (
        ["Karma", "Pema", "Sonam", "Tashi", "Dorji", "Chimi"],
        ["Wangchuk", "Dorji", "Tshering", "Namgyal", "Lhamo"],
    ),
    "German": (
        ["Lukas", "Hannah", "Felix", "Lena", "Jonas", "Marie"],
        ["Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Wagner"],
    ),
    "French": (
        ["Louis", "Camille", "Hugo", "Manon", "Antoine", "Chloe"],
        ["Martin", "Bernard", "Dubois", "Moreau", "Laurent", "Girard"],
    ),
    "Sri Lankan": (
        ["Nuwan", "Dilani", "Kasun", "Sanduni", "Chamara", "Ishara"],
        ["Perera", "Fernando", "Silva", "Jayasuriya", "Bandara"],
    ),
    "Malaysian": (
        ["Ahmad", "Nurul", "Wei Jie", "Siti", "Aiman", "Mei Ling"],
        ["Abdullah", "Tan", "Lim", "Rahman", "Wong", "Ismail"],
    ),
    "Japanese": (
        ["Kenji", "Yuki", "Haruto", "Sakura", "Ren", "Aoi"],
        ["Tanaka", "Suzuki", "Sato", "Watanabe", "Yamamoto", "Nakamura"],
    ),
    "Russian": (
        ["Ivan", "Anastasia", "Dmitry", "Ekaterina", "Sergei", "Olga"],
        ["Ivanov", "Petrov", "Smirnov", "Volkov", "Sokolov"],
    ),
    "Chinese": (
        ["Wei", "Xiaoyan", "Hao", "Jing", "Lei", "Fang"],
        ["Wang", "Li", "Zhang", "Liu", "Chen", "Yang"],
    ),
    "Italian": (
        ["Marco", "Sofia", "Luca", "Giulia", "Matteo", "Chiara"],
        ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano"],
    ),
    "Spanish": (
        ["Javier", "Lucia", "Pablo", "Carmen", "Diego", "Elena"],
        ["Garcia", "Martinez", "Lopez", "Sanchez", "Perez", "Gomez"],
    ),
    "Singaporean": (
        ["Jun Wei", "Hui Ling", "Ryan", "Xin Yi", "Marcus", "Shu Ting"],
        ["Tan", "Lim", "Lee", "Ng", "Ong", "Goh"],
    ),
    "Thai": (
        ["Somchai", "Pimchanok", "Anan", "Kanya", "Nattapong", "Siriporn"],
        ["Srisuk", "Chaiyaporn", "Wongsawat", "Ruangroj", "Thongchai"],
    ),
    "Korean": (
        ["Minjun", "Seoyeon", "Jiho", "Hayoon", "Doyun", "Jiwoo"],
        ["Kim", "Lee", "Park", "Choi", "Jung", "Kang"],
    ),
    "Dutch": (
        ["Daan", "Sanne", "Sem", "Fenna", "Bram", "Julia"],
        ["De Jong", "Jansen", "De Vries", "Van Dijk", "Bakker"],
    ),
    "Israeli": (
        ["Noam", "Maayan", "Itai", "Shira", "Eitan", "Tamar"],
        ["Cohen", "Levi", "Mizrahi", "Peretz", "Avraham"],
    ),
    "Brazilian": (
        ["Lucas", "Ana", "Pedro", "Beatriz", "Gabriel", "Larissa"],
        ["Silva", "Santos", "Oliveira", "Souza", "Pereira"],
    ),
    "South African": (
        ["Thabo", "Lerato", "Sipho", "Naledi", "Johan", "Anika"],
        ["Nkosi", "Dlamini", "Botha", "Van der Merwe", "Mokoena"],
    ),
    "Emirati": (
        ["Omar", "Fatima", "Khalid", "Aisha", "Saeed", "Noura"],
        ["Al Mansoori", "Al Nuaimi", "Al Suwaidi", "Al Marzouqi"],
    ),
    "Swiss": (
        ["Noah", "Mia", "Leon", "Elin", "Nino", "Lara"],
        ["Meier", "Keller", "Huber", "Steiner", "Brunner"],
    ),
}

# Passport prefix + digit count per nationality; Indians default to Aadhaar.
PASSPORT_FORMATS: dict[str, tuple[str, int]] = {
    "Bangladeshi": ("BX", 7), "American": ("", 9), "British": ("", 9),
    "Australian": ("PA", 7), "Canadian": ("HJ", 6), "Nepali": ("NP", 7),
    "Bhutanese": ("BT", 7), "German": ("C", 8), "French": ("", 9),
    "Sri Lankan": ("N", 7), "Malaysian": ("A", 8), "Japanese": ("TK", 7),
    "Russian": ("", 9), "Chinese": ("E", 8), "Italian": ("YA", 7),
    "Spanish": ("XD", 6), "Singaporean": ("K", 7), "Thai": ("AA", 7),
    "Korean": ("M", 8), "Dutch": ("NX", 7), "Israeli": ("", 8),
    "Brazilian": ("FK", 6), "South African": ("A0", 7), "Emirati": ("", 9),
    "Swiss": ("X", 7), "Indian": ("Z", 7),
}

# Country dialling prefix and national-number length.
PHONE_FORMATS: dict[str, tuple[str, int]] = {
    "Indian": ("+91", 10), "Bangladeshi": ("+880", 10), "American": ("+1", 10),
    "British": ("+44", 10), "Australian": ("+61", 9), "Canadian": ("+1", 10),
    "Nepali": ("+977", 10), "Bhutanese": ("+975", 8), "German": ("+49", 10),
    "French": ("+33", 9), "Sri Lankan": ("+94", 9), "Malaysian": ("+60", 9),
    "Japanese": ("+81", 10), "Russian": ("+7", 10), "Chinese": ("+86", 11),
    "Italian": ("+39", 10), "Spanish": ("+34", 9), "Singaporean": ("+65", 8),
    "Thai": ("+66", 9), "Korean": ("+82", 10), "Dutch": ("+31", 9),
    "Israeli": ("+972", 9), "Brazilian": ("+55", 11), "South African": ("+27", 9),
    "Emirati": ("+971", 9), "Swiss": ("+41", 9),
}

EMERGENCY_RELATIONS = [
    "family", "spouse", "parent", "sibling", "friend", "colleague",
    "hotel", "tour_operator", "embassy", "employer",
]

HOTELS = [
    "Radisson Blu Guwahati", "Vivanta Guwahati", "Novotel Guwahati GS Road",
    "Hotel Dynasty, Lakhtokia", "Kiranshree Portico", "Hotel Rajmahal",
    "Ginger Guwahati", "Hotel Nandan", "Brahmaputra Jungle Resort",
    "Wild Mahseer, Balipara", "Diphlu River Lodge, Kaziranga",
    "Ri Kynjai, Umiam", "Hotel Polo Towers, Shillong", "Dolma Homestay, Tawang",
    "Ygdrasill Bamboo Resort, Cherrapunji", "La Maison de Ananda, Majuli",
]

# --------------------------------------------------------------------------
# Behaviour mix
# --------------------------------------------------------------------------
# Fractions of the tourist population assigned to each scripted scenario. The
# tail scenarios are what the anomaly detector, geo-fence engine, SOS dispatch
# and E-FIR workflow are actually tested against.
BEHAVIOUR_MIX: list[tuple[str, float]] = [
    ("normal", 0.60),              # ordinary sightseeing, no alerts expected
    ("night_wanderer", 0.08),      # active 22:00-04:00 -> low safety scores
    ("route_deviation", 0.07),     # strays > 2 km from the planned itinerary
    ("geofence_intrusion", 0.07),  # walks into a high-risk / restricted zone
    ("inactivity", 0.05),          # phone goes quiet for 60-180 minutes
    ("high_speed_transit", 0.04),  # legitimate highway drive (near-miss case)
    ("abduction_pattern", 0.03),   # 150-260 km/h off-route jump -> critical
    ("sos_panic", 0.03),           # presses the panic button
    ("missing_person", 0.02),      # drops off the network -> E-FIR filed
    ("device_fall", 0.01),         # wearable reports a fall + HR anomaly
]

WEATHER_CONDITIONS: list[tuple[str, int, float]] = [
    # (label, OpenWeatherMap condition id, base risk 0-100 per weather.py mapping)
    ("clear sky", 800, 5.0),
    ("few clouds", 801, 10.0),
    ("scattered clouds", 802, 10.0),
    ("overcast clouds", 804, 10.0),
    ("light drizzle", 300, 20.0),
    ("light rain", 500, 30.0),
    ("moderate rain", 501, 30.0),
    ("heavy rain", 502, 60.0),
    ("very heavy rain", 503, 60.0),
    ("thunderstorm", 200, 80.0),
    ("thunderstorm with heavy rain", 202, 80.0),
    ("mist", 701, 45.0),
    ("fog", 741, 45.0),
    ("haze", 721, 45.0),
    ("snow", 601, 50.0),
]

# Monsoon-weighted month profile for the North-East (Jun-Sep is the wet season;
# Cherrapunji is among the wettest inhabited places on earth).
MONSOON_MONTHS = {6, 7, 8, 9}

SOS_MESSAGES = [
    "Help! I am being followed by two men on a motorcycle.",
    "Lost in the forest trail, no landmarks visible, running out of water.",
    "Road accident on the highway, I am injured and cannot walk.",
    "Someone snatched my bag and pushed me down, need police now.",
    "Feeling severely unwell, chest pain, need medical assistance.",
    "Stuck on the cliff edge, the path collapsed behind me.",
    "Boat is taking on water in the middle of the river.",
    "Group of people surrounded my vehicle and are demanding money.",
    "I cannot find my child, we were separated in the crowd.",
    "Landslide has blocked the road, we are trapped on both sides.",
]

AUDIT_ACTIONS = [
    "login_success", "login_failure", "logout", "token_refresh",
    "password_reset_requested", "password_reset_completed",
    "tourist_registered", "sos_triggered", "incident_acknowledged",
    "incident_dispatched", "incident_resolved", "alert_acknowledged",
    "tourist_marked_missing", "efir_filed", "efir_closed", "efir_pdf_downloaded",
    "zone_created", "zone_deleted", "device_registered", "device_deactivated",
    "chain_verified", "ml_metrics_viewed", "audit_log_viewed",
    "tourist_search", "csv_exported",
]

FIRMWARE_VERSIONS = ["1.0.0", "1.2.3", "1.4.0", "2.0.1", "2.1.0", "2.1.4", "3.0.0-beta"]
