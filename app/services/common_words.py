"""Word lists used purely as *guard signals* in the decision layer.

COMMON_WORDS      - everyday English. When a candidate span is one of these,
                    used in an ordinary sentence, Kivi demands stronger evidence
                    before rewriting it.

FOOD_CONTEXT_CUES - words that indicate a sentence is about eating/food. Used to
                    stop a product name like "Kivi" from overwriting the fruit
                    "kiwi" in "I ate a kiwi for breakfast".
"""

COMMON_WORDS = {
    "a", "about", "after", "again", "all", "also", "an", "and", "any", "are",
    "as", "ask", "at", "back", "be", "because", "been", "before", "being",
    "between", "both", "but", "by", "call", "can", "come", "could", "day", "did",
    "do", "does", "down", "each", "even", "every", "few", "find", "first", "for",
    "from", "get", "give", "go", "good", "great", "had", "has", "have", "he",
    "her", "here", "him", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "just", "keep", "know", "last", "left", "let", "life", "like", "long",
    "look", "made", "make", "man", "many", "may", "me", "mind", "more", "most",
    "much", "must", "my", "need", "new", "next", "no", "not", "now", "number",
    "of", "off", "on", "one", "only", "or", "other", "our", "out", "over", "own",
    "part", "people", "place", "put", "review", "right", "run", "said", "same",
    "say", "see", "send", "service", "set", "she", "should", "since", "so",
    "some", "still", "such", "surface", "take", "tell", "than", "that", "their",
    "them", "then", "there", "these", "they", "thing", "think", "this", "those",
    "through", "time", "to", "today", "too", "try", "two", "under", "up", "us",
    "use", "very", "want", "was", "way", "we", "week", "well", "were", "what",
    "when", "where", "which", "while", "who", "why", "will", "with", "word",
    "work", "would", "year", "yes", "you", "your", "meeting", "meaning", "join",
    "joins", "joined", "joining", "mark", "marks", "marked", "bill", "bills",
    "will", "rob", "robs", "grant", "grants", "granted",
}

_FOOD_STRONG = {
    "ate", "eat", "eaten", "eating", "eats", "fruit", "fruits", "salad",
    "juice", "smoothie", "peel", "peeled", "ripe", "unripe", "slice", "sliced",
    "seeds", "rind",
}
_FOOD_WEAK = {
    "breakfast", "lunch", "dinner", "brunch", "snack", "snacks", "grocery",
    "groceries", "supermarket", "bowl", "plate", "hungry", "tasty", "delicious",
    "kitchen", "fridge",
}


def is_common(word: str) -> bool:
    return word.lower() in COMMON_WORDS


def food_context_score(context_tokens) -> float:
    """1.0+ means the sentence is clearly about food."""
    toks = [t.lower() for t in context_tokens]
    strong = sum(1 for t in toks if t in _FOOD_STRONG)
    weak = sum(1 for t in toks if t in _FOOD_WEAK)
    return strong + 0.5 * weak
