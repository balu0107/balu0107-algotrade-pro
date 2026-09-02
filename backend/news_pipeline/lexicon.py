"""Word-level data for the Tier-0 financial-sentiment classifier.

Hand-curated and Loughran-McDonald-*style* (categorized into strong/mild
positive/negative, tuned for financial-news phrasing) - NOT the literal
published LM academic word list, which isn't available offline here. This is
still a keyword lexicon, not real NLP, but it's the data half of what lets
sentiment.py do materially better than plain word-counting: every entry below
carries a weight and a category, and sentiment.py adds negation scope,
contrast-clause splitting, and magnitude scaling on top of it.
"""

# weight: how strongly one occurrence of the word should move the score.
STRONG_POSITIVE = {
    "surge", "surges", "surged", "soar", "soars", "soared", "record", "beats", "beat",
    "outperform", "outperforms", "upgrade", "upgraded", "upgrades", "rally", "rallies",
    "rallied", "bullish", "wins", "won", "bags", "secures", "raises guidance",
    "raised guidance", "raises outlook", "strong demand", "robust growth",
    "multi-year high", "all-time high", "blockbuster", "windfall", "breakthrough",
}
POSITIVE = {
    "profit", "profits", "profitable", "gain", "gains", "gainer", "growth",
    "grows", "grew", "expansion", "expands", "approval", "approved", "approves",
    "deal", "win", "boost", "boosts", "rise", "rises", "rose", "up", "higher",
    "positive", "optimistic", "rebound", "recovers", "recovery", "improve",
    "improves", "improved", "improvement", "dividend", "buyback", "order book",
    "contract", "stake sale", "expand capacity", "capacity expansion",
    "credit rating upgrade", "strong order", "healthy", "steady growth",
}
MILD_POSITIVE = {
    "stable", "maintains", "maintained", "in line", "steady", "resilient",
    "modest growth", "gradual improvement",
}
STRONG_NEGATIVE = {
    "plunge", "plunges", "plunged", "crash", "crashes", "crashed", "fraud",
    "scam", "bankruptcy", "insolvency", "default", "defaults", "defaulted",
    "collapse", "collapses", "collapsed", "downgrade", "downgraded",
    "downgrades", "probe", "investigation", "raid", "raided", "penalty",
    "fined", "fine", "lawsuit", "litigation", "resign", "resigns", "resigned",
    "resignation", "steps down", "stepped down", "profit warning",
    "guidance cut", "cuts guidance", "cut guidance", "recall", "recalled",
    "data breach", "cyberattack", "hacked", "shutdown", "halted",
    "production halt", "layoff", "layoffs", "sacked", "fired", "insider trading",
}
NEGATIVE = {
    "plunge", "fall", "falls", "falling", "fell", "drop", "drops", "dropped",
    "decline", "declines", "declined", "loss", "losses", "miss", "misses",
    "missed", "bearish", "underperform", "underperforms", "weak", "cut",
    "cuts", "ban", "banned", "down", "lower", "negative", "pessimistic",
    "slump", "slumps", "warning", "concerns", "concern", "delay", "delayed",
    "impairment", "writedown", "write-down", "restructuring", "strike",
    "regulatory action", "compliance issue", "margin pressure", "margins collapse",
    "margins fall", "shrinks", "shrinking", "contraction", "called off",
    "scrapped", "shelved", "abandoned", "terminated", "withdrawn",
}
MILD_NEGATIVE = {
    "cautious", "subdued", "sluggish", "soft demand", "marginal decline",
    "slight dip", "under pressure",
}

WEIGHTS = {
    "strong_positive": 2.0, "positive": 1.0, "mild_positive": 0.4,
    "strong_negative": -2.0, "negative": -1.0, "mild_negative": -0.4,
}
CATEGORY_WORDS = {
    "strong_positive": STRONG_POSITIVE, "positive": POSITIVE, "mild_positive": MILD_POSITIVE,
    "strong_negative": STRONG_NEGATIVE, "negative": NEGATIVE, "mild_negative": MILD_NEGATIVE,
}

# Negation flips (and dampens) the polarity of whatever follows within a small
# token window - "not profitable" should not read as positive just because
# "profitable" appears.
NEGATION_WORDS = {"not", "no", "never", "fails", "failed", "failing", "unable", "cannot", "without", "n't", "denies", "denied"}
NEGATION_WINDOW = 3  # tokens of look-back before a polarity hit

# Splitting on these turns one headline/sentence into independently-scored
# clauses - the direct mechanism behind detecting "profit rises but guidance
# is cut" as MIXED instead of averaging the two signals away.
CONTRAST_CONNECTORS = {"but", "however", "although", "though", "despite", "yet", "while", "whereas"}

# Scale the local weight of nearby polarity hits.
MAGNITUDE_UP = {"sharply": 1.5, "significantly": 1.4, "massive": 1.5, "substantially": 1.4, "steeply": 1.5, "dramatically": 1.5}
MAGNITUDE_DOWN = {"slightly": 0.6, "marginally": 0.5, "modestly": 0.6, "mildly": 0.6, "somewhat": 0.7}
MAGNITUDE_WINDOW = 2  # tokens of look-back before a polarity hit

# Phrases signaling a whole-market roundup rather than a company-specific
# story - used by relevance.py, not sentiment, but kept alongside the rest of
# the pipeline's hand-curated word data for one place to look.
MARKET_ROUNDUP_PHRASES = {
    "market rises", "market falls", "sensex", "nifty", "top gainers", "top losers",
    "among gainers", "among losers", "broader market", "benchmark index",
    "market today", "closing bell", "opening bell", "market wrap",
}
