"""Hand-curated entity-matching data for relevance.py.

No `companies` DB table - main.py's existing FULL_NSE_SYMBOLS already gives
the canonical symbol->company-name mapping for free. What's actually missing
is common short names/abbreviations financial headlines use instead of the
full legal name ("RIL" for Reliance Industries, "HUL" for Hindustan Unilever),
and sector-level keywords for the "whole sector moved" relevance band.

Stated limitation: this only covers the ~80 highest-traffic symbols (the ones
most likely to show up in market-wide RSS roundups or get on-demand detail-
page traffic). The long tail falls back to relevance.py's generic bare-name-
token matching (stripping "Limited/Ltd/Industries/Corp/..." and matching
whatever significant word remains) - cruder, but non-empty coverage for every
symbol, not just these.
"""

COMPANY_ALIASES = {
    "RELIANCE": ["RIL", "Reliance Jio", "Jio", "Reliance Retail"],
    "TCS": ["Tata Consultancy"],
    "HDFCBANK": ["HDFC Bank"],
    "ICICIBANK": ["ICICI"],
    "INFY": ["Infosys"],
    "HINDUNILVR": ["HUL"],
    "SBIN": ["SBI", "State Bank"],
    "BHARTIARTL": ["Airtel", "Bharti Airtel"],
    "KOTAKBANK": ["Kotak", "Kotak Mahindra"],
    "LT": ["L&T", "Larsen & Toubro", "Larsen and Toubro"],
    "AXISBANK": ["Axis Bank"],
    "BAJFINANCE": ["Bajaj Finance"],
    "MARUTI": ["Maruti Suzuki", "Maruti"],
    "HCLTECH": ["HCL", "HCL Tech"],
    "SUNPHARMA": ["Sun Pharma"],
    "ULTRACEMCO": ["UltraTech", "UltraTech Cement"],
    "WIPRO": ["Wipro"],
    "NESTLEIND": ["Nestle India", "Nestle"],
    "ONGC": ["ONGC", "Oil and Natural Gas"],
    "NTPC": ["NTPC"],
    "POWERGRID": ["Power Grid"],
    "M&M": ["Mahindra", "M&M", "Mahindra & Mahindra"],
    "TATAMOTORS": ["Tata Motors"],
    "TATASTEEL": ["Tata Steel"],
    "ADANIENT": ["Adani Enterprises"],
    "ADANIPORTS": ["Adani Ports"],
    "JSWSTEEL": ["JSW Steel"],
    "BAJAJFINSV": ["Bajaj Finserv"],
    "HDFCLIFE": ["HDFC Life"],
    "SBILIFE": ["SBI Life"],
    "DIVISLAB": ["Divi's Labs", "Divis Labs"],
    "DRREDDY": ["Dr Reddy's", "Dr Reddys"],
    "CIPLA": ["Cipla"],
    "EICHERMOT": ["Eicher Motors", "Royal Enfield"],
    "HEROMOTOCO": ["Hero MotoCorp", "Hero Moto"],
    "BAJAJ-AUTO": ["Bajaj Auto"],
    "GRASIM": ["Grasim"],
    "COALINDIA": ["Coal India", "CIL"],
    "BPCL": ["Bharat Petroleum", "BPCL"],
    "IOC": ["Indian Oil", "IOCL"],
    "HINDALCO": ["Hindalco"],
    "TECHM": ["Tech Mahindra"],
    "BRITANNIA": ["Britannia"],
    "APOLLOHOSP": ["Apollo Hospitals"],
    "INDUSINDBK": ["IndusInd Bank", "IndusInd"],
    "TATACONSUM": ["Tata Consumer"],
    "VEDL": ["Vedanta"],
    "PIDILITIND": ["Pidilite"],
    "DABUR": ["Dabur"],
    "GODREJCP": ["Godrej Consumer"],
    "MARICO": ["Marico"],
    "HAVELLS": ["Havells"],
    "DLF": ["DLF"],
    "AMBUJACEM": ["Ambuja Cement", "Ambuja Cements"],
    "BANKBARODA": ["Bank of Baroda", "BoB"],
    "PNB": ["Punjab National Bank", "PNB"],
    "CANBK": ["Canara Bank"],
    "IDFCFIRSTB": ["IDFC First Bank", "IDFC First"],
    "BANDHANBNK": ["Bandhan Bank"],
    "FEDERALBNK": ["Federal Bank"],
    "ZOMATO": ["Zomato", "Eternal"],
    "NYKAA": ["Nykaa", "FSN E-Commerce"],
    "PAYTM": ["Paytm", "One97 Communications"],
    "POLICYBZR": ["Policybazaar", "PB Fintech"],
    "IRCTC": ["IRCTC"],
    "DMART": ["DMart", "Avenue Supermarts"],
    "TRENT": ["Trent", "Westside"],
    "COLPAL": ["Colgate", "Colgate-Palmolive"],
    "MUTHOOTFIN": ["Muthoot Finance", "Muthoot"],
    "LUPIN": ["Lupin"],
    "AUROPHARMA": ["Aurobindo Pharma", "Aurobindo"],
    "BIOCON": ["Biocon"],
    "MPHASIS": ["Mphasis"],
    "LTIM": ["LTIMindtree", "LTI Mindtree"],
    "PERSISTENT": ["Persistent Systems"],
    "COFORGE": ["Coforge"],
    "NAUKRI": ["Naukri", "Info Edge"],
    "INDIGO": ["IndiGo", "InterGlobe Aviation"],
    "SPICEJET": ["SpiceJet"],
    "BEL": ["Bharat Electronics", "BEL"],
    "HAL": ["Hindustan Aeronautics", "HAL"],
    "BHEL": ["Bharat Heavy Electricals", "BHEL"],
    "SAIL": ["Steel Authority", "SAIL"],
    "NMDC": ["NMDC"],
    "JINDALSTEL": ["Jindal Steel"],
    "GAIL": ["GAIL", "GAIL India"],
    "ZEEL": ["Zee Entertainment", "Zee"],
    "SUNTV": ["Sun TV"],
    "YESBANK": ["Yes Bank"],
    "IDEA": ["Vodafone Idea", "Vi"],
    "SUZLON": ["Suzlon"],
    "JIOFIN": ["Jio Financial"],
    "DIXON": ["Dixon Technologies"],
    "VOLTAS": ["Voltas"],
    "TATAPOWER": ["Tata Power"],
    "ADANIGREEN": ["Adani Green"],
    "ADANIPOWER": ["Adani Power"],
}

# yfinance's `.info["sector"]` values -> phrases a market-roundup headline
# uses for that sector. Matched case-insensitively against title+description.
SECTOR_KEYWORDS = {
    "Financial Services": ["bank stocks", "banking stocks", "banking sector", "nbfc", "lenders", "private banks", "psu banks"],
    "Energy": ["oil companies", "oil stocks", "crude prices", "refiners", "energy stocks", "oil marketing companies", "oil-to-chemical"],
    "Technology": ["it stocks", "it sector", "software exporters", "tech stocks", "it companies"],
    "Basic Materials": ["metal stocks", "steel stocks", "cement stocks", "mining stocks", "commodity stocks"],
    "Healthcare": ["pharma stocks", "pharma sector", "drugmakers", "healthcare stocks"],
    "Consumer Cyclical": ["auto stocks", "automakers", "auto sector", "realty stocks"],
    "Consumer Defensive": ["fmcg stocks", "fmcg sector", "consumer goods stocks"],
    "Utilities": ["power stocks", "power sector", "utility stocks"],
    "Industrials": ["infra stocks", "capital goods stocks", "engineering stocks"],
    "Communication Services": ["telecom stocks", "telecom sector", "telcos"],
    "Real Estate": ["realty stocks", "real estate stocks", "property developers"],
}


def get_aliases(symbol: str) -> list[str]:
    return COMPANY_ALIASES.get(symbol.upper(), [])


def get_sector_keywords(sector: str | None) -> list[str]:
    if not sector:
        return []
    return SECTOR_KEYWORDS.get(sector, [])
