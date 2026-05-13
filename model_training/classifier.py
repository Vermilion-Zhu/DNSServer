import math
import re
from collections import Counter

class DGADetector:
    """A simple DGA (Domain Generation Algorithm) detector based on lexical features."""
    def __init__(self, threshold=0.5):
        self.threshold = threshold
        # Placeholder for a real model (e.g., sklearn Random Forest)
        self.model = None 

    def get_entropy(self, domain):
        """Calculate Shannon entropy of the domain name."""
        # Strip TLD and dots
        name = domain.split('.')[0]
        if not name:
            return 0
        counts = Counter(name)
        probs = [count / len(name) for count in counts.values()]
        return -sum(p * math.log2(p) for p in probs)

    def get_vowel_ratio(self, domain):
        """Calculate the ratio of vowels in the domain name."""
        name = domain.split('.')[0].lower()
        if not name:
            return 0
        vowels = re.findall(r'[aeiou]', name)
        return len(vowels) / len(name)

    def get_digit_ratio(self, domain):
        """Calculate the ratio of digits in the domain name."""
        name = domain.split('.')[0]
        if not name:
            return 0
        digits = re.findall(r'\d', name)
        return len(digits) / len(name)

    def get_consonant_streak(self, domain):
        """Find the longest streak of consonants."""
        name = domain.split('.')[0].lower()
        streaks = re.findall(r'[bcdfghjklmnpqrstvwxyz]+', name)
        return max(len(s) for s in streaks) if streaks else 0

    def predict(self, domain):
        """
        Predict if a domain is DGA. 
        For now, uses a simple heuristic-based approach.
        """
        # Heuristic rules for DGA-like domains:
        # 1. High entropy
        # 2. Low vowel ratio
        # 3. High digit ratio
        # 4. Long consonant streaks
        
        domain_part = domain.split('.')[0]
        if not domain_part:
            return False, 0.0
            
        entropy = self.get_entropy(domain)
        vowel_ratio = self.get_vowel_ratio(domain)
        digit_ratio = self.get_digit_ratio(domain)
        consonant_streak = self.get_consonant_streak(domain)
        length = len(domain_part)
        
        score = 0
        if entropy > 3.2: score += 0.3
        if vowel_ratio < 0.25: score += 0.2
        if digit_ratio > 0.15: score += 0.2
        if consonant_streak > 4: score += 0.3
        if length > 12: score += 0.2
        
        # Additional check for random-looking characters
        if re.search(r'[a-z0-9]{10,}', domain_part):
            score += 0.2
            
        is_dga = score >= self.threshold
        return is_dga, score

if __name__ == "__main__":
    detector = DGADetector()
    test_domains = ["google.com", "example.com", "7asdf89asdf789asdf.com", "vowelless.com", "qwrtyp.xyz"]
    for d in test_domains:
        is_dga, score = detector.predict(d)
        print(f"Domain: {d:25} DGA: {str(is_dga):6} Score: {score:.2f}")
