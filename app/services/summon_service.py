import re

class SummonService:
    def __init__(self):
        # Regex to match "jarvis" or "@jarvis" at word boundaries
        # Case insensitive
        self.summon_pattern = re.compile(r'(^|\s)@?jarvis(:|\s|$)', re.IGNORECASE)

    def is_summon(self, text: str) -> bool:
        if not text:
            return False
        return bool(self.summon_pattern.search(text))

summon_service = SummonService()
