"""
news_fetcher.py - Moduł pobierania newsów crypto

Odpowiedzialny za:
- Pobieranie newsów z CryptoPanic API
- Parsowanie RSS feeds (CoinDesk, CoinTelegraph)
- Pobieranie ogłoszeń z Binance
- Filtrowanie i cache newsów
- Ranking ważności newsów
"""

import logging
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from enum import Enum

import requests

# RSS parser - graceful degradation
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

logger = logging.getLogger(__name__)


class NewsImportance(Enum):
    """Poziom ważności newsa"""
    BREAKING = 4      # Krytyczne wydarzenia (hack, delisting, regulacje)
    HIGH = 3          # Ważne (ETF, partnerstwa, major updates)
    MEDIUM = 2        # Standardowe newsy
    LOW = 1           # Mniej istotne
    NOISE = 0         # Spam, reklamy


class NewsSource(Enum):
    """Źródła newsów"""
    CRYPTOPANIC = "cryptopanic"
    COINDESK = "coindesk"
    COINTELEGRAPH = "cointelegraph"
    BINANCE = "binance"


@dataclass
class NewsItem:
    """Struktura pojedynczego newsa"""
    id: str
    title: str
    summary: Optional[str]
    source: NewsSource
    url: str
    published_at: datetime
    importance: NewsImportance
    currencies: List[str]  # BTC, ETH, etc.
    sentiment_keywords: List[str]
    raw_data: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'summary': self.summary,
            'source': self.source.value,
            'url': self.url,
            'published_at': self.published_at.isoformat(),
            'importance': self.importance.value,
            'currencies': self.currencies,
            'sentiment_keywords': self.sentiment_keywords
        }
    
    def __hash__(self):
        return hash(self.id)


class NewsFetcher:
    """
    Główna klasa do pobierania i zarządzania newsami crypto
    
    Wspiera:
    - CryptoPanic API (darmowy tier 200 calls/day)
    - CoinDesk RSS feed
    - CoinTelegraph RSS feed
    - Binance announcements
    """
    
    # RSS Feed URLs
    RSS_FEEDS = {
        NewsSource.COINDESK: "https://www.coindesk.com/arc/outboundfeeds/rss/",
        NewsSource.COINTELEGRAPH: "https://cointelegraph.com/rss"
    }
    
    # Binance announcements API
    BINANCE_ANNOUNCEMENTS_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"
    
    # Cryptopanic API
    CRYPTOPANIC_API_URL = "https://cryptopanic.com/api/v1/posts/"
    
    # Keywords dla wykrywania ważności
    BREAKING_KEYWORDS = [
        'hack', 'hacked', 'exploit', 'stolen', 'breach', 'attack',
        'sec', 'lawsuit', 'regulation', 'ban', 'emergency', 'crash',
        'delisting', 'bankrupt', 'fraud', 'arrest', 'investigation',
        'shut down', 'shutdown', 'collapse'
    ]
    
    HIGH_KEYWORDS = [
        'etf', 'approval', 'approved', 'partnership', 'adoption',
        'institutional', 'upgrade', 'mainnet', 'halving', 'airdrop',
        'integration', 'launch', 'massive', 'billion', 'record'
    ]
    
    BULLISH_KEYWORDS = [
        'bullish', 'surge', 'rally', 'soar', 'breakout', 'all-time high',
        'ath', 'adoption', 'institutional', 'partnership', 'upgrade',
        'approval', 'positive', 'growth', 'gains', 'pump', 'moon',
        'accumulation', 'buy signal', 'support'
    ]
    
    BEARISH_KEYWORDS = [
        'bearish', 'crash', 'plunge', 'dump', 'sell-off', 'selloff',
        'fear', 'panic', 'hack', 'exploit', 'lawsuit', 'ban',
        'negative', 'decline', 'drop', 'loss', 'resistance', 'breakdown',
        'capitulation', 'concern', 'warning'
    ]
    
    # Supported currencies
    SUPPORTED_CURRENCIES = {'BTC', 'ETH', 'XRP', 'DOGE'}
    
    CURRENCY_PATTERNS = {
        'BTC': [r'\bbtc\b', r'\bbitcoin\b', r'\bbtcusdt?\b'],
        'ETH': [r'\beth\b', r'\bethereum\b', r'\bethusdt?\b'],
        'XRP': [r'\bxrp\b', r'\bripple\b', r'\bxrpusdt?\b'],
        'DOGE': [r'\bdoge\b', r'\bdogecoin\b', r'\bdogeusdt?\b']
    }
    
    def __init__(self, config: dict):
        """
        Inicjalizacja NewsFetcher
        
        Args:
            config: Konfiguracja z parametrami news
        """
        self.config = config.get('news', {})
        self.llm_config = config.get('llm', {})
        
        # Parametry
        self.enabled = self.config.get('enabled', True)
        self.cache_hours = self.config.get('cache_hours', 24)
        self.update_interval = self.config.get('update_interval', 300)  # 5 min
        
        # API keys (opcjonalne)
        self.cryptopanic_api_key = self.config.get('cryptopanic_api_key', '')
        
        # Enabled sources
        enabled_sources = self.config.get('sources', ['coindesk', 'cointelegraph'])
        self.enabled_sources = [NewsSource(s) for s in enabled_sources if s in [ns.value for ns in NewsSource]]
        
        # Cache
        self.news_cache: Dict[str, NewsItem] = {}
        self.seen_ids: Set[str] = set()
        self.last_fetch_time: Dict[NewsSource, datetime] = {}
        
        # Cache file path
        self.cache_path = self.config.get('cache_path', './data/news_cache.json')
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        
        # Load cache
        self._load_cache()
        
        if not HAS_FEEDPARSER:
            logger.warning("[WARNING] feedparser nie zainstalowany - RSS feeds niedostępne")
        
        logger.info(f"[OK] NewsFetcher zainicjalizowany (sources: {[s.value for s in self.enabled_sources]})")
    
    def get_latest_news(self, hours: int = 24, currencies: Optional[List[str]] = None) -> List[NewsItem]:
        """
        Pobiera najnowsze newsy
        
        Args:
            hours: Ile godzin wstecz
            currencies: Filtr walut (domyślnie: BTC, ETH, XRP, DOGE)
        
        Returns:
            Lista newsów posortowana po dacie (najnowsze najpierw)
        """
        if not self.enabled:
            return []
        
        # Odśwież cache jeśli potrzeba
        self._refresh_if_needed()
        
        # Filtruj po czasie
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Filtruj po walutach
        if currencies is None:
            currencies = list(self.SUPPORTED_CURRENCIES)
        currencies_set = set(c.upper() for c in currencies)
        
        filtered_news = []
        for news_item in self.news_cache.values():
            # Sprawdź czas
            if news_item.published_at < cutoff_time:
                continue
            
            # Sprawdź waluty
            if not any(c in currencies_set for c in news_item.currencies):
                continue
            
            filtered_news.append(news_item)
        
        # Sortuj po dacie (najnowsze najpierw)
        filtered_news.sort(key=lambda x: x.published_at, reverse=True)
        
        logger.debug(f"[NEWS] Znaleziono {len(filtered_news)} newsów z ostatnich {hours}h")
        return filtered_news
    
    def get_breaking_news(self, hours: int = 4) -> List[NewsItem]:
        """
        Pobiera tylko breaking news
        
        Args:
            hours: Ile godzin wstecz
        
        Returns:
            Lista breaking newsów
        """
        all_news = self.get_latest_news(hours=hours)
        return [n for n in all_news if n.importance == NewsImportance.BREAKING]
    
    def get_news_by_currency(self, currency: str, hours: int = 24) -> List[NewsItem]:
        """
        Pobiera newsy dla konkretnej waluty
        
        Args:
            currency: Symbol waluty (np. 'BTC')
            hours: Ile godzin wstecz
        
        Returns:
            Lista newsów dla waluty
        """
        all_news = self.get_latest_news(hours=hours)
        return [n for n in all_news if currency.upper() in n.currencies]
    
    def _refresh_if_needed(self):
        """Odświeża cache jeśli minął interval"""
        now = datetime.now()
        
        for source in self.enabled_sources:
            last_fetch = self.last_fetch_time.get(source, datetime.min)
            if (now - last_fetch).total_seconds() >= self.update_interval:
                try:
                    self._fetch_from_source(source)
                    self.last_fetch_time[source] = now
                except Exception as e:
                    logger.error(f"[ERROR] Błąd pobierania z {source.value}: {e}")
        
        # Zapisz cache
        self._save_cache()
    
    def _fetch_from_source(self, source: NewsSource):
        """Pobiera newsy z określonego źródła"""
        if source == NewsSource.CRYPTOPANIC:
            self._fetch_cryptopanic()
        elif source in [NewsSource.COINDESK, NewsSource.COINTELEGRAPH]:
            self._fetch_rss(source)
        elif source == NewsSource.BINANCE:
            self._fetch_binance()
    
    def _fetch_cryptopanic(self):
        """Pobiera newsy z CryptoPanic API"""
        if not self.cryptopanic_api_key:
            logger.debug("CryptoPanic API key nie skonfigurowany - pomijam")
            return
        
        try:
            params = {
                'auth_token': self.cryptopanic_api_key,
                'currencies': ','.join(self.SUPPORTED_CURRENCIES).lower(),
                'filter': 'hot',  # Tylko ważne newsy
                'public': 'true'
            }
            
            response = requests.get(
                self.CRYPTOPANIC_API_URL,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            results = data.get('results', [])
            
            for item in results:
                news = self._parse_cryptopanic_item(item)
                if news and news.id not in self.seen_ids:
                    self.news_cache[news.id] = news
                    self.seen_ids.add(news.id)
            
            logger.info(f"[NEWS] CryptoPanic: Pobrano {len(results)} newsów")
            
        except Exception as e:
            logger.error(f"[ERROR] CryptoPanic API error: {e}")
    
    def _parse_cryptopanic_item(self, item: Dict) -> Optional[NewsItem]:
        """Parsuje pojedynczy news z CryptoPanic"""
        try:
            # Extract currencies
            currencies = []
            for curr in item.get('currencies', []):
                code = curr.get('code', '').upper()
                if code in self.SUPPORTED_CURRENCIES:
                    currencies.append(code)
            
            if not currencies:
                return None
            
            # Parse date
            published_str = item.get('published_at', '')
            try:
                published_at = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                published_at = published_at.replace(tzinfo=None)
            except:
                published_at = datetime.now()
            
            title = item.get('title', '')
            
            # Determine importance and sentiment
            importance = self._determine_importance(title)
            sentiment_keywords = self._extract_sentiment_keywords(title)
            
            return NewsItem(
                id=f"cp_{item.get('id', hashlib.md5(title.encode()).hexdigest()[:8])}",
                title=title,
                summary=None,
                source=NewsSource.CRYPTOPANIC,
                url=item.get('url', ''),
                published_at=published_at,
                importance=importance,
                currencies=currencies,
                sentiment_keywords=sentiment_keywords,
                raw_data=item
            )
        except Exception as e:
            logger.debug(f"Błąd parsowania CryptoPanic item: {e}")
            return None
    
    def _fetch_rss(self, source: NewsSource):
        """Pobiera newsy z RSS feed"""
        if not HAS_FEEDPARSER:
            return
        
        url = self.RSS_FEEDS.get(source)
        if not url:
            return
        
        try:
            feed = feedparser.parse(url)
            
            count = 0
            for entry in feed.entries[:50]:  # Max 50 entries
                news = self._parse_rss_entry(entry, source)
                if news and news.id not in self.seen_ids:
                    # Sprawdź czy dotyczy obsługiwanych walut
                    if news.currencies:
                        self.news_cache[news.id] = news
                        self.seen_ids.add(news.id)
                        count += 1
            
            logger.info(f"[NEWS] {source.value}: Pobrano {count} newsów")
            
        except Exception as e:
            logger.error(f"[ERROR] RSS feed error ({source.value}): {e}")
    
    def _parse_rss_entry(self, entry: Dict, source: NewsSource) -> Optional[NewsItem]:
        """Parsuje pojedynczy wpis RSS"""
        try:
            title = entry.get('title', '')
            summary = entry.get('summary', entry.get('description', ''))[:500]
            link = entry.get('link', '')
            
            # Parse date
            published_struct = entry.get('published_parsed') or entry.get('updated_parsed')
            if published_struct:
                published_at = datetime(*published_struct[:6])
            else:
                published_at = datetime.now()
            
            # Extract currencies from title + summary
            full_text = f"{title} {summary}".lower()
            currencies = self._extract_currencies(full_text)
            
            if not currencies:
                return None
            
            # Determine importance
            importance = self._determine_importance(full_text)
            sentiment_keywords = self._extract_sentiment_keywords(full_text)
            
            # Generate ID
            news_id = f"{source.value[:2]}_{hashlib.md5((title + link).encode()).hexdigest()[:8]}"
            
            return NewsItem(
                id=news_id,
                title=title,
                summary=summary if summary != title else None,
                source=source,
                url=link,
                published_at=published_at,
                importance=importance,
                currencies=currencies,
                sentiment_keywords=sentiment_keywords
            )
        except Exception as e:
            logger.debug(f"Błąd parsowania RSS entry: {e}")
            return None
    
    def _fetch_binance(self):
        """Pobiera ogłoszenia z Binance"""
        try:
            payload = {
                "type": 1,
                "pageNo": 1,
                "pageSize": 20
            }
            
            response = requests.post(
                self.BINANCE_ANNOUNCEMENTS_URL,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            articles = data.get('data', {}).get('articles', [])
            
            count = 0
            for article in articles:
                news = self._parse_binance_article(article)
                if news and news.id not in self.seen_ids:
                    if news.currencies:
                        self.news_cache[news.id] = news
                        self.seen_ids.add(news.id)
                        count += 1
            
            logger.info(f"[NEWS] Binance: Pobrano {count} ogłoszeń")
            
        except Exception as e:
            logger.error(f"[ERROR] Binance announcements error: {e}")
    
    def _parse_binance_article(self, article: Dict) -> Optional[NewsItem]:
        """Parsuje ogłoszenie Binance"""
        try:
            title = article.get('title', '')
            
            # Parse date
            release_date = article.get('releaseDate', 0)
            if release_date:
                published_at = datetime.fromtimestamp(release_date / 1000)
            else:
                published_at = datetime.now()
            
            # Extract currencies
            currencies = self._extract_currencies(title.lower())
            
            # Binance announcements are typically high importance
            importance = NewsImportance.HIGH
            sentiment_keywords = self._extract_sentiment_keywords(title)
            
            return NewsItem(
                id=f"bn_{article.get('code', hashlib.md5(title.encode()).hexdigest()[:8])}",
                title=title,
                summary=None,
                source=NewsSource.BINANCE,
                url=f"https://www.binance.com/en/support/announcement/{article.get('code', '')}",
                published_at=published_at,
                importance=importance,
                currencies=currencies if currencies else ['BTC'],  # Default to BTC for exchange news
                sentiment_keywords=sentiment_keywords
            )
        except Exception as e:
            logger.debug(f"Błąd parsowania Binance article: {e}")
            return None
    
    def _extract_currencies(self, text: str) -> List[str]:
        """Wyciąga waluty z tekstu"""
        currencies = []
        text_lower = text.lower()
        
        for currency, patterns in self.CURRENCY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    if currency not in currencies:
                        currencies.append(currency)
                    break
        
        return currencies
    
    def _determine_importance(self, text: str) -> NewsImportance:
        """Określa ważność newsa na podstawie tekstu"""
        text_lower = text.lower()
        
        # Check for breaking keywords
        for keyword in self.BREAKING_KEYWORDS:
            if keyword in text_lower:
                return NewsImportance.BREAKING
        
        # Check for high importance keywords
        for keyword in self.HIGH_KEYWORDS:
            if keyword in text_lower:
                return NewsImportance.HIGH
        
        # Default to medium
        return NewsImportance.MEDIUM
    
    def _extract_sentiment_keywords(self, text: str) -> List[str]:
        """Wyciąga słowa kluczowe sentymentu"""
        text_lower = text.lower()
        keywords = []
        
        for keyword in self.BULLISH_KEYWORDS:
            if keyword in text_lower:
                keywords.append(f"+{keyword}")
        
        for keyword in self.BEARISH_KEYWORDS:
            if keyword in text_lower:
                keywords.append(f"-{keyword}")
        
        return keywords[:5]  # Max 5 keywords
    
    def _load_cache(self):
        """Ładuje cache z pliku"""
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Reconstruct NewsItem objects
                cutoff = datetime.now() - timedelta(hours=self.cache_hours)
                
                for item_data in data.get('news', []):
                    try:
                        published_at = datetime.fromisoformat(item_data['published_at'])
                        if published_at < cutoff:
                            continue
                        
                        news = NewsItem(
                            id=item_data['id'],
                            title=item_data['title'],
                            summary=item_data.get('summary'),
                            source=NewsSource(item_data['source']),
                            url=item_data['url'],
                            published_at=published_at,
                            importance=NewsImportance(item_data['importance']),
                            currencies=item_data['currencies'],
                            sentiment_keywords=item_data.get('sentiment_keywords', [])
                        )
                        self.news_cache[news.id] = news
                        self.seen_ids.add(news.id)
                    except Exception as e:
                        logger.debug(f"Błąd ładowania news item: {e}")
                
                logger.info(f"[PACKAGE] Załadowano {len(self.news_cache)} newsów z cache")
        except Exception as e:
            logger.debug(f"Nie można załadować cache: {e}")
    
    def _save_cache(self):
        """Zapisuje cache do pliku"""
        try:
            # Clean old news
            cutoff = datetime.now() - timedelta(hours=self.cache_hours)
            valid_news = [n for n in self.news_cache.values() if n.published_at >= cutoff]
            
            data = {
                'last_update': datetime.now().isoformat(),
                'news': [n.to_dict() for n in valid_news]
            }
            
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd zapisywania cache: {e}")
    
    def force_refresh(self):
        """Wymusza odświeżenie wszystkich źródeł"""
        logger.info("[SYNC] Wymuszam odświeżenie newsów...")
        self.last_fetch_time.clear()
        self._refresh_if_needed()
    
    def get_stats(self) -> Dict:
        """Zwraca statystyki newsów"""
        now = datetime.now()
        
        stats = {
            'total_cached': len(self.news_cache),
            'by_source': {},
            'by_currency': {},
            'by_importance': {},
            'last_24h': 0,
            'last_1h': 0
        }
        
        for news in self.news_cache.values():
            # By source
            source = news.source.value
            stats['by_source'][source] = stats['by_source'].get(source, 0) + 1
            
            # By currency
            for curr in news.currencies:
                stats['by_currency'][curr] = stats['by_currency'].get(curr, 0) + 1
            
            # By importance
            imp = news.importance.name
            stats['by_importance'][imp] = stats['by_importance'].get(imp, 0) + 1
            
            # Time-based
            age = now - news.published_at
            if age < timedelta(hours=24):
                stats['last_24h'] += 1
            if age < timedelta(hours=1):
                stats['last_1h'] += 1
        
        return stats


if __name__ == "__main__":
    # Test modułu
    import yaml
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Test bez API key (tylko RSS)
    config['news'] = {
        'enabled': True,
        'sources': ['coindesk', 'cointelegraph'],
        'cache_hours': 24,
        'update_interval': 60
    }
    
    fetcher = NewsFetcher(config)
    
    # Pobierz newsy
    news = fetcher.get_latest_news(hours=24)
    
    print(f"\n[NEWS] Znaleziono {len(news)} newsów:")
    for item in news[:10]:
        print(f"\n  [{item.importance.name}] {item.source.value}")
        print(f"  [DATE] {item.published_at}")
        print(f"  [$] {', '.join(item.currencies)}")
        print(f"  [LOG] {item.title[:80]}...")
        if item.sentiment_keywords:
            print(f"  [TARGET] Keywords: {', '.join(item.sentiment_keywords)}")
    
    # Stats
    stats = fetcher.get_stats()
    print(f"\n[INFO] Statystyki:")
    print(f"  Total: {stats['total_cached']}")
    print(f"  Last 24h: {stats['last_24h']}")
    print(f"  By source: {stats['by_source']}")
    print(f"  By currency: {stats['by_currency']}")
