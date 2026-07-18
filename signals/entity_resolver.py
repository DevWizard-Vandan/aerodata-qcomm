import os
import sys
import re
import logging

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class EntityResolver:
    # Explicit brand mapping rules
    BRAND_MAP = {
        'HINDUNILVR': [r'^surf\s+excel$', r'^dove$', r'^knorr$', r'^horlicks$', r'^kwality\s+wall\'s$'],
        'ITC': [r'^aashirvaad$', r'^sunfeast$', r'^yippee!?$', r'^fiama$', r'^bingo$'],
        'TATACONSUM': [r'^tata\s+salt$', r'^tata\s+tea$', r'^sampann$', r'^soulfull$', r'^starbucks$'],
        'GODREJCP': [r'^goodknight$', r'^hit$', r'^cinthol$', r'^godrej\s+expert$'],
        'VBL': [r'^pepsi$', r'^mountain\s+dew$', r'^tropicana$', r'^aquafina$'],
        'UNLISTED': [r'^amul$', r'^nandini$', r'^mother\s+dairy$'],
        'BRITANNIA': [r'^britannia$', r'^good\s+day$', r'^tiger$', r'^bourbon$', r'^marie\s+gold$', r'^milk\s+bikis$'],
        'NESTLEIND': [r'^nestle$', r'^maggi$', r'^nescafe$', r'^kitkat$', r'^munch$', r'^milkybar$'],
        'MARICO': [r'^marico$', r'^parachute$', r'^saffola$', r'^livon$', r'^set\s+wet$', r'^beardo$'],
        'DABUR': [r'^dabur$', r'^chyawanprash$', r'^honey$', r'^real$', r'^vatika$', r'^hajmola$'],
        'COLPAL': [r'^colgate$', r'^palmolive$', r'^colpal$']
    }

    # Heuristic product name token checks
    HEURISTIC_MAP = {
        'HINDUNILVR': [r'\bhul\b', r'\bhindustan\s+unilever\b', r'\bsurf\s+excel\b', r'\bdove\b', r'\bhorlicks\b', r'\bknorr\b', r'\bkwality\s+wall\b'],
        'ITC': [r'\bitc\b', r'\baashirvaad\b', r'\bsunfeast\b', r'\byippee\b', r'\bbingo\b', r'\bfiama\b'],
        'TATACONSUM': [r'\btata\b', r'\bsampann\b', r'\bsoulfull\b', r'\bstarbucks\b'],
        'GODREJCP': [r'\bgodrej\b', r'\bcinthol\b', r'\bgoodknight\b', r'\bhit\b'],
        'VBL': [r'\bpepsi\b', r'\bmountain\s+dew\b', r'\btropicana\b', r'\baquafina\b', r'\bvbl\b'],
        'UNLISTED': [r'\bamul\b', r'\bnandini\b', r'\bmother\s+dairy\b'],
        'BRITANNIA': [r'\bbritannia\b', r'\bgood\s+day\b', r'\btiger\b', r'\bbourbon\b', r'\bmarie\s+gold\b', r'\bmilk\s+bikis\b'],
        'NESTLEIND': [r'\bnestle\b', r'\bmaggi\b', r'\bnescafe\b', r'\bkitkat\b', r'\bmunch\b', r'\bmilkybar\b'],
        'MARICO': [r'\bmarico\b', r'\bparachute\b', r'\bsaffola\b', r'\blivon\b', r'\bset\s+wet\b', r'\bbeardo\b'],
        'DABUR': [r'\bdabur\b', r'\bchyawanprash\b', r'\bhoney\b', r'\breal\b', r'\bvatika\b', r'\bhajmola\b'],
        'COLPAL': [r'\bcolgate\b', r'\bpalmolive\b', r'\bcolpal\b']
    }

    def __init__(self):
        # Precompile regular expressions for maximum token-matching speed
        self.compiled_brands = {}
        for ticker, patterns in self.BRAND_MAP.items():
            self.compiled_brands[ticker] = [re.compile(p, re.IGNORECASE) for p in patterns]

        self.compiled_heuristics = {}
        for ticker, patterns in self.HEURISTIC_MAP.items():
            self.compiled_heuristics[ticker] = [re.compile(p, re.IGNORECASE) for p in patterns]

    def resolve(self, brand_name, product_name, store_id="", platform_name=""):
        """
        Resolves brand/product parameters to listed corporate tickers.
        Priority:
        1. Exact Brand Map Match
        2. Heuristic Product Name Keyword Match
        3. Structural Platform Parent Match
        """
        # 1. Exact Brand Mapping Check
        if brand_name:
            brand_clean = str(brand_name).strip()
            for ticker, regexes in self.compiled_brands.items():
                for rx in regexes:
                    if rx.match(brand_clean):
                        return ticker

        # 2. Fallback Heuristic Matcher Check
        if product_name:
            prod_clean = str(product_name).strip()
            for ticker, regexes in self.compiled_heuristics.items():
                for rx in regexes:
                    if rx.search(prod_clean):
                        return ticker

        # 3. Platform-level structural parent mapping fallback
        platform_clean = str(platform_name).lower()
        store_clean = str(store_id).lower()
        
        if "blinkit" in platform_clean or "blinkit" in store_clean or "grofers" in store_clean:
            return "ZOMATO"
        elif "swiggy" in platform_clean or "swiggy" in store_clean:
            return "SWIGGY"
        elif "zepto" in platform_clean or "zepto" in store_clean:
            return "UNLISTED"
            
        return "UNLISTED"

if __name__ == "__main__":
    # Self-test logic
    resolver = EntityResolver()
    assert resolver.resolve("Surf Excel", "Surf Excel Easy Wash 1kg") == "HINDUNILVR"
    assert resolver.resolve("Heritage", "Heritage Paneer 200g", platform_name="Swiggy Instamart") == "SWIGGY"
    assert resolver.resolve("Amul", "Amul Butter 100g") == "UNLISTED"
    assert resolver.resolve("Maggi", "Maggi 2-Min Noodles 70g") == "NESTLEIND"
    assert resolver.resolve("Parachute", "Parachute Coconut Hair Oil 250ml") == "MARICO"
    assert resolver.resolve("Good Day", "Good Day Choco Cookies 100g") == "BRITANNIA"
    assert resolver.resolve("Dabur", "Dabur Honey 500g") == "DABUR"
    assert resolver.resolve("Colgate", "Colgate MaxFresh Toothpaste 150g") == "COLPAL"
    print("All EntityResolver self-tests passed successfully.")
