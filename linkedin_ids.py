"""
LinkedIn internal IDs for filters.
These are used to construct search URLs with pre-applied filters.
IDs are extracted from LinkedIn's URL parameters.

To find new IDs: search LinkedIn with the filter applied, then look at the URL.
- geoUrn IDs are in the geoUrn parameter
- industry IDs are in the industry parameter
- company IDs are in the currentCompany parameter
"""

# Common locations (geoUrn IDs)
LOCATIONS = {
    # UAE & Gulf
    "united arab emirates": "104305776",
    "uae": "104305776",
    "dubai": "106204383",
    "abu dhabi": "106031264",
    "sharjah": "100542498",
    "saudi arabia": "100459316",
    "riyadh": "104898741",
    "jeddah": "105076658",
    "qatar": "104110264",
    "doha": "104982096",
    "bahrain": "101011788",
    "oman": "104558027",
    "kuwait": "101459657",

    # India
    "india": "102713980",
    "mumbai": "103570968",
    "bangalore": "105214831",
    "bengaluru": "105214831",
    "delhi": "102890719",
    "new delhi": "102890719",
    "hyderabad": "105556991",
    "pune": "114806696",
    "chennai": "106228723",
    "kolkata": "107082846",
    "gurgaon": "103457498",
    "noida": "116785002",

    # Other popular
    "united states": "103644278",
    "united kingdom": "101165590",
    "london": "102257491",
    "new york": "102571732",
    "singapore": "102454443",
    "australia": "101452733",
    "canada": "101174742",
    "germany": "101282230",
    "france": "105015875",
    "netherlands": "102890883",
}

# Common industries
INDUSTRIES = {
    "technology": "6",
    "information technology": "6",
    "it": "6",
    "financial services": "43",
    "banking": "41",
    "insurance": "42",
    "accounting": "47",
    "logistics": "114",
    "supply chain": "114",
    "transportation": "114",
    "retail": "27",
    "e-commerce": "111",
    "ecommerce": "111",
    "food & beverages": "34",
    "food and beverages": "34",
    "hospitality": "31",
    "real estate": "44",
    "healthcare": "14",
    "education": "69",
    "marketing": "80",
    "advertising": "80",
    "consulting": "94",
    "management consulting": "94",
    "human resources": "137",
    "hr": "137",
    "oil & gas": "57",
    "oil and gas": "57",
    "construction": "48",
    "telecommunications": "8",
    "media": "110",
    "manufacturing": "53",
    "automotive": "51",
    "pharmaceuticals": "82",
    "aviation": "94",
    "government": "75",
}


def lookup_location_ids(location_str: str) -> list:
    """Look up geoUrn IDs for a location string. Supports comma-separated locations."""
    ids = []
    locations = [l.strip().lower() for l in location_str.split(",")]
    for loc in locations:
        if loc in LOCATIONS:
            ids.append(LOCATIONS[loc])
        else:
            # Try partial match
            for key, val in LOCATIONS.items():
                if loc in key or key in loc:
                    ids.append(val)
                    break
    return ids


def lookup_industry_ids(industry_str: str) -> list:
    """Look up industry IDs. Supports comma-separated."""
    ids = []
    industries = [i.strip().lower() for i in industry_str.split(",")]
    for ind in industries:
        if ind in INDUSTRIES:
            ids.append(INDUSTRIES[ind])
        else:
            for key, val in INDUSTRIES.items():
                if ind in key or key in ind:
                    ids.append(val)
                    break
    return ids
