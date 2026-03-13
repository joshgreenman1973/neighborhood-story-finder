"""
Configuration for the NYC Neighborhood Story Finder.
Neighborhood → Community District mappings, API endpoints, categories.
"""

# Socrata base URL for NYC Open Data
SOCRATA_BASE = "https://data.cityofnewyork.us/resource"

# 311 Service Requests dataset
THREE11_DATASET_ID = "erm2-nwe9"

# Community Board Budget Requests dataset (OMB, updated ~3x/year)
CB_BUDGET_DATASET_ID = "vn4m-mk4t"

# CouncilStat Constituent Services dataset (daily updates, but data may lag)
COUNCILSTAT_DATASET_ID = "b9km-gdpy"

# Zoning Application Portal (ZAP) — active ULURP & land use applications
ZAP_DATASET_ID = "hgx4-8ukb"

# ZAP borough letter → boro code mapping
ZAP_BORO_MAP = {"M": "1", "X": "2", "K": "3", "Q": "4", "R": "5"}

# Community District GeoJSON (ArcGIS FeatureServer)
CD_GEOJSON_URL = "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/NYC_Community_Districts/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson"

# Category taxonomy (shared across all sources)
CATEGORIES = [
    "housing",
    "safety",
    "transit",
    "sanitation",
    "noise",
    "pests",
    "development",
    "infrastructure",
    "environment",
    "health",
    "education",
    "government",
]

# Map 311 complaint types to our categories
COMPLAINT_CATEGORY_MAP = {
    "housing": [
        "heat/hot water", "plumbing", "paint/plaster", "water leak",
        "elevator", "door/window", "electric",
        "lead", "mold", "appliance", "safety", "flooring/stairs",
    ],
    "safety": [
        "drug activity", "drinking", "panhandling", "homeless person assistance",
        "non-emergency police matter", "animal abuse", "illegal fireworks",
        "encampment",
    ],
    "noise": [
        "noise", "noise - residential", "noise - commercial", "noise - street/sidewalk",
        "noise - vehicle", "noise - helicopter", "noise survey",
    ],
    "transit": [
        "traffic signal condition", "street light condition", "broken parking meter",
        "bus stop shelter placement", "bike/roller/skate chronic",
        "traffic", "illegal parking", "blocked driveway",
    ],
    "sanitation": [
        "dirty conditions", "unsanitary condition", "derelict vehicle",
        "graffiti", "litter basket / request", "overflowing litter baskets",
        "missed collection (all materials)", "sanitation condition",
        "sweeping/inadequate", "abandoned vehicle",
    ],
    "pests": [
        "rodent", "bed bugs", "pest control", "animal in a park",
    ],
    "infrastructure": [
        "street condition", "sidewalk condition", "pothole",
        "curb condition", "broken muni meter", "fire hydrant",
        "water system", "sewer", "catch basin/inlet", "manhole",
        "snow or ice",
    ],
    "development": [
        "building/use", "illegal conversion", "construction",
        "general construction", "crane/derrick", "scaffold safety",
        "building condition", "vacant lot", "zoning/land use",
    ],
    "environment": [
        "air quality", "asbestos", "hazardous material",
        "industrial waste", "standing water",
        "dead tree", "overgrown tree/branches", "new tree request",
    ],
    "health": [
        "food poisoning", "food establishment", "indoor air quality",
    ],
}

# Subreddits to scan, with geo mappings
SUBREDDITS = {
    "nyc":            {"cds": None, "borough": None},  # citywide, needs text extraction
    "newyorkcity":    {"cds": None, "borough": None},
    "Brooklyn":       {"cds": None, "borough": "Brooklyn"},
    "Queens":         {"cds": None, "borough": "Queens"},
    "bronx":          {"cds": None, "borough": "Bronx"},
    "StatenIsland":   {"cds": None, "borough": "Staten Island"},
    "astoria":        {"cds": ["401"], "borough": "Queens"},
    "Bushwick":       {"cds": ["304"], "borough": "Brooklyn"},
    "Williamsburg":   {"cds": ["301"], "borough": "Brooklyn"},
    "washingtonheights": {"cds": ["112"], "borough": "Manhattan"},
    "Harlem":         {"cds": ["110", "111"], "borough": "Manhattan"},
    "UES":            {"cds": ["108"], "borough": "Manhattan"},
}

# Neighborhood names → Community District codes
# Format: "NN" where first digit is borough (1=MN,2=BX,3=BK,4=QN,5=SI)
NEIGHBORHOOD_TO_CD = {
    # Manhattan
    "financial district": ["101"], "tribeca": ["101"], "battery park city": ["101"],
    "chinatown": ["103"], "lower east side": ["103"], "les": ["103"], "two bridges": ["103"],
    "soho": ["102"], "greenwich village": ["102"], "noho": ["102"], "west village": ["102"],
    "little italy": ["102"],
    "chelsea": ["104"], "hudson yards": ["104"], "hells kitchen": ["104"],
    "hell's kitchen": ["104"], "clinton": ["104"],
    "midtown": ["105"], "flatiron": ["105"], "gramercy": ["105"],
    "murray hill": ["106"], "turtle bay": ["106"], "kips bay": ["106"],
    "stuyvesant town": ["106"], "peter cooper village": ["106"],
    "upper west side": ["107"], "uws": ["107"], "lincoln square": ["107"],
    "upper east side": ["108"], "ues": ["108"], "yorkville": ["108"],
    "carnegie hill": ["108"], "lenox hill": ["108"],
    "morningside heights": ["109"], "manhattanville": ["109"],
    "hamilton heights": ["109"],
    "central harlem": ["110"], "harlem": ["110"],
    "east harlem": ["111"], "el barrio": ["111"], "spanish harlem": ["111"],
    "washington heights": ["112"], "inwood": ["112"], "fort george": ["112"],

    # Bronx
    "mott haven": ["201"], "port morris": ["201"], "melrose": ["201"],
    "hunts point": ["202"], "longwood": ["202"],
    "morrisania": ["203"], "crotona": ["203"], "claremont": ["203"],
    "highbridge": ["204"], "concourse": ["204"], "grand concourse": ["204"],
    "fordham": ["205"], "university heights": ["205"], "belmont": ["206"],
    "kingsbridge": ["207"], "bedford park": ["207"], "norwood": ["207"],
    "riverdale": ["208"], "fieldston": ["208"],
    "parkchester": ["209"], "soundview": ["209"], "unionport": ["209"],
    "throgs neck": ["210"], "co-op city": ["210"], "pelham bay": ["210"],
    "morris park": ["211"], "pelham parkway": ["211"],
    "williamsbridge": ["212"], "baychester": ["212"], "eastchester": ["212"],

    # Brooklyn
    "greenpoint": ["301"], "williamsburg": ["301"],
    "fort greene": ["302"], "brooklyn heights": ["302"],
    "downtown brooklyn": ["302"], "boerum hill": ["302"], "dumbo": ["302"],
    "bedford stuyvesant": ["303"], "bed-stuy": ["303"], "bed stuy": ["303"],
    "bushwick": ["304"],
    "east new york": ["305"], "cypress hills": ["305"], "eny": ["305"],
    "park slope": ["306"], "carroll gardens": ["306"], "red hook": ["306"],
    "cobble hill": ["306"], "gowanus": ["306"],
    "sunset park": ["307"], "windsor terrace": ["307"],
    "crown heights": ["308"], "prospect heights": ["308"],
    "crown heights south": ["309"], "prospect lefferts": ["309"],
    "plg": ["309"], "flatbush": ["309"],
    "bay ridge": ["310"], "dyker heights": ["310"],
    "bensonhurst": ["311"], "bath beach": ["311"],
    "borough park": ["312"], "kensington": ["312"],
    "coney island": ["313"], "brighton beach": ["313"], "sea gate": ["313"],
    "flatlands": ["318"], "canarsie": ["318"],
    "east flatbush": ["317"], "rugby": ["317"],
    "midwood": ["314"], "ocean parkway": ["314"],
    "sheepshead bay": ["315"], "manhattan beach": ["315"],
    "gravesend": ["315"],
    "brownsville": ["316"], "ocean hill": ["316"],

    # Queens
    "astoria": ["401"], "long island city": ["401"], "lic": ["401"],
    "sunnyside": ["402"], "woodside": ["402"],
    "jackson heights": ["403"], "elmhurst": ["403"], "corona": ["403"],
    "forest hills": ["406"], "rego park": ["406"],
    "flushing": ["407"], "murray hill queens": ["407"],
    "hillcrest": ["408"], "fresh meadows": ["408"], "briarwood": ["408"],
    "jamaica": ["412"], "hollis": ["412"],
    "far rockaway": ["414"], "rockaway": ["414"], "rockaways": ["414"],
    "howard beach": ["410"], "ozone park": ["410"],
    "ridgewood": ["405"], "glendale": ["405"], "middle village": ["405"],
    "woodhaven": ["409"], "richmond hill": ["409"],
    "south jamaica": ["412"], "st. albans": ["412"],
    "bayside": ["411"], "douglaston": ["411"], "little neck": ["411"],

    # Staten Island
    "st. george": ["501"], "stapleton": ["501"], "tompkinsville": ["501"],
    "port richmond": ["501"],
    "south beach": ["502"], "dongan hills": ["502"], "midland beach": ["502"],
    "tottenville": ["503"], "great kills": ["503"], "annadale": ["503"],
}

# CD code → display name
CD_NAMES = {
    "101": "Lower Manhattan", "102": "Greenwich Village / SoHo",
    "103": "Lower East Side / Chinatown", "104": "Chelsea / Hell's Kitchen",
    "105": "Midtown", "106": "Murray Hill / Gramercy",
    "107": "Upper West Side", "108": "Upper East Side",
    "109": "Morningside Heights / Hamilton Heights",
    "110": "Central Harlem", "111": "East Harlem",
    "112": "Washington Heights / Inwood",
    "201": "Mott Haven / Melrose", "202": "Hunts Point / Longwood",
    "203": "Morrisania / Crotona", "204": "Highbridge / Concourse",
    "205": "Fordham / University Heights", "206": "Belmont / East Tremont",
    "207": "Kingsbridge / Bedford Park", "208": "Riverdale / Fieldston",
    "209": "Parkchester / Soundview", "210": "Throgs Neck / Co-op City",
    "211": "Morris Park / Pelham Parkway", "212": "Williamsbridge / Baychester",
    "301": "Greenpoint / Williamsburg", "302": "Fort Greene / Brooklyn Heights",
    "303": "Bedford-Stuyvesant", "304": "Bushwick",
    "305": "East New York / Cypress Hills", "306": "Park Slope / Carroll Gardens",
    "307": "Sunset Park", "308": "Crown Heights / Prospect Heights",
    "309": "Flatbush / PLG", "310": "Bay Ridge / Dyker Heights",
    "311": "Bensonhurst / Bath Beach", "312": "Borough Park / Kensington",
    "313": "Coney Island / Brighton Beach", "314": "Midwood / Ocean Parkway",
    "315": "Sheepshead Bay / Gravesend", "316": "Brownsville / Ocean Hill",
    "317": "East Flatbush", "318": "Flatlands / Canarsie",
    "401": "Astoria / Long Island City", "402": "Sunnyside / Woodside",
    "403": "Jackson Heights / Elmhurst / Corona",
    "404": "Elmhurst / South Corona",
    "405": "Ridgewood / Glendale / Middle Village",
    "406": "Forest Hills / Rego Park",
    "407": "Flushing", "408": "Hillcrest / Fresh Meadows",
    "409": "Woodhaven / Richmond Hill", "410": "Howard Beach / Ozone Park",
    "411": "Bayside / Douglaston / Little Neck",
    "412": "Jamaica / Hollis / St. Albans",
    "413": "Queens Village / Cambria Heights",
    "414": "Far Rockaway / Rockaways",
    "501": "St. George / Stapleton", "502": "South Beach / Dongan Hills",
    "503": "Tottenville / Great Kills",
}

BOROUGH_CODES = {
    "1": "Manhattan", "2": "Bronx", "3": "Brooklyn",
    "4": "Queens", "5": "Staten Island",
    "MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3",
    "QUEENS": "4", "STATEN ISLAND": "5",
}

# Topic classification keywords (ported from nyc-news-engine)
TOPIC_RULES = {
    "housing": [
        "housing", "rent", "tenant", "landlord", "eviction", "affordable housing",
        "nycha", "public housing", "shelter", "zoning", "rezoning", "apartment",
        "homeless", "unhoused", "voucher",
    ],
    "education": [
        "school", "education", "student", "teacher", "doe", "charter",
        "cuny", "suny", "pre-k", "curriculum", "chancellor", "class size",
    ],
    "safety": [
        "crime", "shooting", "stabbing", "assault", "robbery", "murder",
        "gun violence", "safety", "nypd", "police", "arrest",
    ],
    "transit": [
        "transit", "mta", "subway", "bus", "congestion pricing", "bike lane",
        "cyclist", "pedestrian", "traffic", "dot", "citibike", "ferry",
        "e-bike", "sidewalk", "crosswalk", "vision zero",
    ],
    "health": [
        "health", "hospital", "mental health", "opioid", "fentanyl",
        "overdose", "clinic", "public health",
    ],
    "environment": [
        "climate", "flooding", "pollution", "air quality",
        "sustainability", "waste", "recycling", "composting",
    ],
    "development": [
        "development", "construction", "building", "real estate",
        "landmark", "historic", "demolition",
    ],
    "quality-of-life": [
        "noise", "sanitation", "rat", "rodent", "litter", "graffiti",
        "homeless encampment", "quality of life",
    ],
    "government": [
        "mayor", "city hall", "city council", "budget", "commissioner",
        "albany", "governor",
    ],
    "infrastructure": [
        "pothole", "water main", "sewer", "power outage", "street light",
        "bridge", "tunnel", "infrastructure",
    ],
}

# News RSS feeds (subset from nyc-news-engine, hyperlocal focus)
NEWS_FEEDS = [
    {"name": "THE CITY", "slug": "the-city", "url": "https://www.thecity.nyc/feed/", "tier": 1},
    {"name": "Gothamist", "slug": "gothamist", "url": "https://gothamist.com/feed", "tier": 1},
    {"name": "Hell Gate", "slug": "hell-gate", "url": "https://hellgatenyc.com/all-posts/rss/", "tier": 1},
    {"name": "City Limits", "slug": "city-limits", "url": "https://citylimits.org/feed/", "tier": 1},
    {"name": "Streetsblog NYC", "slug": "streetsblog", "url": "https://nyc.streetsblog.org/feed", "tier": 1},
    {"name": "Chalkbeat NYC", "slug": "chalkbeat", "url": "https://www.chalkbeat.org/arc/outboundfeeds/rss/category/new-york/", "tier": 1},
    {"name": "Documented", "slug": "documented", "url": "https://documentedny.com/feed/", "tier": 1},
    {"name": "Brooklyn Eagle", "slug": "brooklyn-eagle", "url": "https://brooklyneagle.com/feed/", "tier": 2},
    {"name": "amNewYork", "slug": "amny", "url": "https://www.amny.com/feed/", "tier": 2},
    {"name": "NY Post", "slug": "ny-post", "url": "https://nypost.com/feed/", "tier": 2},
    {"name": "Patch NYC", "slug": "patch", "url": "https://patch.com/new-york/new-york-city/rss", "tier": 2},
]
