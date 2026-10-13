"""
llm_sentiment.py - Moduł analizy sentymentu przez LLM

Odpowiedzialny za:
- Integracja z LM Studio (OpenAI compatible API)
- Analiza sentymentu newsów (-1.0 do +1.0)
- Generowanie daily briefing
- Wykrywanie black swan events
- Wyjaśnianie decyzji tradingowych
"""

import logging
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

import requests

# OpenAI library - graceful degradation
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Dostępni providerzy LLM"""
    LM_STUDIO = "lm_studio"
    OLLAMA = "ollama"
    OPENAI = "openai"


@dataclass
class SentimentResult:
    """Wynik analizy sentymentu"""
    score: float  # -1.0 (bearish) do +1.0 (bullish)
    confidence: float  # 0.0 do 1.0
    reasoning: str
    key_factors: List[str]
    is_emergency: bool  # Black swan detected?
    emergency_details: Optional[str]
    timestamp: datetime
    
    def to_dict(self) -> Dict:
        return {
            'score': self.score,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'key_factors': self.key_factors,
            'is_emergency': self.is_emergency,
            'emergency_details': self.emergency_details,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class DailyBriefing:
    """Dzienny briefing rynkowy"""
    date: datetime
    overall_sentiment: float
    market_summary: str
    key_events: List[str]
    opportunities: List[str]
    risks: List[str]
    recommendation: str  # "BULLISH", "BEARISH", "NEUTRAL", "CAUTIOUS"
    
    def to_dict(self) -> Dict:
        return {
            'date': self.date.isoformat(),
            'overall_sentiment': self.overall_sentiment,
            'market_summary': self.market_summary,
            'key_events': self.key_events,
            'opportunities': self.opportunities,
            'risks': self.risks,
            'recommendation': self.recommendation
        }


class LLMSentimentAnalyzer:
    """
    Analizator sentymentu oparty na LLM
    
    Wspiera:
    - LM Studio (domyślny, http://localhost:1234)
    - Ollama
    - OpenAI API (jako backup)
    """
    
    # System prompts dla różnych zadań
    SENTIMENT_SYSTEM_PROMPT = """Jesteś ekspertem analizy rynku kryptowalut. Twoim zadaniem jest analiza sentymentu newsów crypto.

ZASADY:
1. Analizuj obiektywnie, bez emocji
2. Uwzględniaj kontekst rynkowy
3. Rozróżniaj FUD od rzeczywistych problemów
4. Oceniaj wpływ na cenę w perspektywie 24-72h

ODPOWIEDZ W FORMACIE JSON:
{
    "sentiment_score": <float od -1.0 do 1.0>,
    "confidence": <float od 0.0 do 1.0>,
    "reasoning": "<krótkie uzasadnienie w 1-2 zdaniach>",
    "key_factors": ["<czynnik 1>", "<czynnik 2>"],
    "is_emergency": <true/false>,
    "emergency_details": "<jeśli is_emergency=true, opisz>"
}

SKALA SENTYMENTU:
-1.0 do -0.7: Bardzo bearish (crash, hack, ban)
-0.7 do -0.3: Bearish (negatywne newsy)
-0.3 do +0.3: Neutralny
+0.3 do +0.7: Bullish (pozytywne newsy)
+0.7 do +1.0: Bardzo bullish (ETF approval, major adoption)"""

    BRIEFING_SYSTEM_PROMPT = """Jesteś strategiem rynku kryptowalut. Przygotuj dzienny briefing dla tradera.

Na podstawie dostarczonych newsów przygotuj:
1. Podsumowanie nastrojów rynkowych
2. Kluczowe wydarzenia dnia
3. Potencjalne okazje tradingowe
4. Ryzyka do monitorowania
5. Ogólną rekomendację (BULLISH/BEARISH/NEUTRAL/CAUTIOUS)

ODPOWIEDZ W FORMACIE JSON:
{
    "overall_sentiment": <float od -1.0 do 1.0>,
    "market_summary": "<2-3 zdania podsumowania>",
    "key_events": ["<wydarzenie 1>", "<wydarzenie 2>"],
    "opportunities": ["<okazja 1>", "<okazja 2>"],
    "risks": ["<ryzyko 1>", "<ryzyko 2>"],
    "recommendation": "BULLISH|BEARISH|NEUTRAL|CAUTIOUS"
}"""

    TRADE_EXPLANATION_PROMPT = """Jesteś AI trading assistantem. Wyjaśnij decyzję tradingową w przystępny sposób.

Na podstawie kontekstu trade'a (pattern, wskaźniki, sentiment) wyjaśnij:
1. Dlaczego ten setup jest (nie)korzystny
2. Główne czynniki za/przeciw
3. Potencjalne ryzyka
4. Zalecenia dotyczące zarządzania pozycją

Odpowiedz zwięźle (max 150 słów), po polsku."""

    EMERGENCY_DETECTION_PROMPT = """Jesteś systemem wykrywania BLACK SWAN events na rynku crypto.

BLACK SWAN = nagłe, nieoczekiwane wydarzenie o potencjalnie katastrofalnym wpływie na rynek.

PRZYKŁADY BLACK SWAN:
- Hack dużej giełdy (>$100M)
- Nagły ban/regulacja w dużym kraju
- Upadek dużego projektu/giełdy
- Masowe wyprzedaże wielorybów
- Problemy z stablecoinami

Przeanalizuj news i odpowiedz:
{
    "is_black_swan": <true/false>,
    "severity": <1-10>,
    "action_required": "HALT_TRADING|CLOSE_LONGS|CLOSE_SHORTS|MONITOR|NONE",
    "reasoning": "<krótkie uzasadnienie>"
}"""
    
    def __init__(self, config: dict):
        """
        Inicjalizacja LLM Sentiment Analyzer
        
        Args:
            config: Konfiguracja z parametrami LLM
        """
        self.config = config.get('llm', {})
        
        # Parametry
        self.enabled = self.config.get('enabled', True)
        self.provider = LLMProvider(self.config.get('provider', 'lm_studio'))
        self.base_url = self.config.get('base_url', 'http://localhost:1234/v1')
        self.model = self.config.get('model', 'llama3:8b')
        self.timeout = self.config.get('timeout', 30)
        self.temperature = self.config.get('temperature', 0.1)
        self.max_tokens = self.config.get('max_tokens', 500)
        
        # Wagi dla Decision Engine
        self.sentiment_weight = self.config.get('sentiment_weight', 0.15)
        self.veto_threshold = self.config.get('veto_threshold', -0.7)
        
        # Cache
        self._last_sentiment: Optional[SentimentResult] = None
        self._last_briefing: Optional[DailyBriefing] = None
        
        # Initialize client
        self.client = None
        if self.enabled:
            self._init_client()
        
        logger.info(f"[OK] LLMSentimentAnalyzer zainicjalizowany (provider: {self.provider.value})")
    
    def _init_client(self):
        """Inicjalizuje klienta OpenAI/LM Studio"""
        if not HAS_OPENAI:
            logger.warning("[WARNING] openai library nie zainstalowana - LLM niedostępne")
            return
        
        try:
            # LM Studio i Ollama używają OpenAI-compatible API
            self.client = OpenAI(
                base_url=self.base_url,
                api_key="not-needed"  # LM Studio nie wymaga klucza
            )
            
            # Test połączenia
            logger.info(f"[PLUG] Próbuję połączyć z {self.base_url}...")
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd inicjalizacji LLM client: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """Sprawdza czy LLM jest dostępny"""
        if not self.enabled or not self.client:
            return False
        
        try:
            # Prosty test ping
            self.client.models.list()
            return True
        except Exception:
            return False
    
    def analyze_news(self, news_items: List[Any]) -> Optional[SentimentResult]:
        """
        Analizuje sentiment newsów
        
        Args:
            news_items: Lista obiektów NewsItem
        
        Returns:
            SentimentResult lub None przy błędzie
        """
        if not self.enabled or not news_items:
            return self._fallback_sentiment(news_items)
        
        if not self.client:
            logger.warning("[WARNING] LLM client niedostępny - używam fallback")
            return self._fallback_sentiment(news_items)
        
        try:
            # Przygotuj newsy do analizy
            news_text = self._format_news_for_llm(news_items)
            
            # Wywołaj LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SENTIMENT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Przeanalizuj następujące newsy crypto:\n\n{news_text}"}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout
            )
            
            # Parse response
            content = response.choices[0].message.content
            result = self._parse_sentiment_response(content)
            
            if result:
                self._last_sentiment = result
                logger.info(f"[INFO] LLM Sentiment: {result.score:.2f} (confidence: {result.confidence:.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd analizy LLM: {e}")
            return self._fallback_sentiment(news_items)
    
    def daily_briefing(self, news_items: List[Any]) -> Optional[DailyBriefing]:
        """
        Generuje dzienny briefing rynkowy
        
        Args:
            news_items: Lista newsów z ostatnich 24h
        
        Returns:
            DailyBriefing lub None przy błędzie
        """
        if not self.enabled or not news_items:
            return None
        
        if not self.client:
            return None
        
        try:
            news_text = self._format_news_for_llm(news_items, detailed=True)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.BRIEFING_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Przygotuj briefing na podstawie newsów:\n\n{news_text}"}
                ],
                temperature=self.temperature,
                max_tokens=800,
                timeout=self.timeout * 2  # Więcej czasu na dłuższą odpowiedź
            )
            
            content = response.choices[0].message.content
            result = self._parse_briefing_response(content)
            
            if result:
                self._last_briefing = result
                logger.info(f"[NEWS] Daily Briefing: {result.recommendation} (sentiment: {result.overall_sentiment:.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd generowania briefingu: {e}")
            return None
    
    def emergency_detection(self, news_items: List[Any]) -> Tuple[bool, Optional[Dict]]:
        """
        Wykrywa black swan events
        
        Args:
            news_items: Lista newsów do sprawdzenia
        
        Returns:
            (is_emergency, details_dict)
        """
        if not self.enabled or not news_items:
            return False, None
        
        # Najpierw szybka heurystyka
        emergency_keywords = [
            'hack', 'hacked', 'exploit', 'stolen', 'breach',
            'crash', 'collapse', 'bankrupt', 'fraud', 'arrest',
            'ban', 'shutdown', 'emergency'
        ]
        
        potential_emergencies = []
        for news in news_items:
            title_lower = news.title.lower()
            if any(kw in title_lower for kw in emergency_keywords):
                potential_emergencies.append(news)
        
        if not potential_emergencies:
            return False, None
        
        # Użyj LLM do weryfikacji
        if not self.client:
            # Fallback: jeśli są słowa kluczowe, zakładaj emergency
            return True, {
                'is_black_swan': True,
                'severity': 7,
                'action_required': 'MONITOR',
                'reasoning': 'Wykryto potencjalnie krytyczne słowa kluczowe - zweryfikuj ręcznie'
            }
        
        try:
            news_text = self._format_news_for_llm(potential_emergencies)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.EMERGENCY_DETECTION_PROMPT},
                    {"role": "user", "content": f"Sprawdź czy to BLACK SWAN:\n\n{news_text}"}
                ],
                temperature=0.0,  # Deterministyczna odpowiedź
                max_tokens=300,
                timeout=self.timeout
            )
            
            content = response.choices[0].message.content
            result = self._parse_json_response(content)
            
            if result and result.get('is_black_swan', False):
                logger.warning(f"[ALERT] BLACK SWAN DETECTED: {result.get('reasoning', 'Unknown')}")
                return True, result
            
            return False, result
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd emergency detection: {e}")
            return False, None
    
    def explain_trade(self, trade_context: Dict) -> Optional[str]:
        """
        Wyjaśnia decyzję tradingową
        
        Args:
            trade_context: Słownik z kontekstem trade'a
                - symbol: Para walutowa
                - direction: LONG/SHORT
                - pattern: Typ patternu
                - technical_score: Score techniczny
                - sentiment_score: Score sentymentu
                - reasoning: Lista powodów
        
        Returns:
            Wyjaśnienie tekstowe
        """
        if not self.enabled or not self.client:
            return self._fallback_explanation(trade_context)
        
        try:
            context_text = f"""
Symbol: {trade_context.get('symbol', 'N/A')}
Kierunek: {trade_context.get('direction', 'N/A')}
Pattern: {trade_context.get('pattern', 'N/A')}
Technical Score: {trade_context.get('technical_score', 0):.1f}/100
Sentiment Score: {trade_context.get('sentiment_score', 0):.2f} (-1 do +1)
Powody:
{chr(10).join('- ' + r for r in trade_context.get('reasoning', [])[:5])}
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.TRADE_EXPLANATION_PROMPT},
                    {"role": "user", "content": f"Wyjaśnij ten trade:\n{context_text}"}
                ],
                temperature=0.3,
                max_tokens=300,
                timeout=self.timeout
            )
            
            explanation = response.choices[0].message.content
            return explanation.strip()
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd wyjaśniania trade'a: {e}")
            return self._fallback_explanation(trade_context)
    
    def get_cached_sentiment(self) -> Optional[SentimentResult]:
        """Zwraca ostatni wynik analizy sentymentu"""
        return self._last_sentiment
    
    def get_cached_briefing(self) -> Optional[DailyBriefing]:
        """Zwraca ostatni briefing"""
        return self._last_briefing
    
    # ========================================
    # HELPER METHODS
    # ========================================
    
    def _format_news_for_llm(self, news_items: List[Any], detailed: bool = False) -> str:
        """Formatuje newsy dla LLM"""
        lines = []
        
        for i, news in enumerate(news_items[:15], 1):  # Max 15 newsów
            if detailed:
                lines.append(f"{i}. [{news.importance.name}] {news.title}")
                if news.summary:
                    lines.append(f"   {news.summary[:200]}")
                lines.append(f"   Źródło: {news.source.value}, Waluty: {', '.join(news.currencies)}")
                lines.append("")
            else:
                importance_emoji = {
                    'BREAKING': '[ALERT]',
                    'HIGH': '[WARNING]',
                    'MEDIUM': '[NEWS]',
                    'LOW': '[FILE]'
                }.get(news.importance.name, '[FILE]')
                
                lines.append(f"{importance_emoji} {news.title}")
        
        return "\n".join(lines)
    
    def _parse_sentiment_response(self, content: str) -> Optional[SentimentResult]:
        """Parsuje odpowiedź JSON z sentymentem"""
        try:
            data = self._parse_json_response(content)
            if not data:
                return None
            
            return SentimentResult(
                score=float(data.get('sentiment_score', 0)),
                confidence=float(data.get('confidence', 0.5)),
                reasoning=str(data.get('reasoning', '')),
                key_factors=data.get('key_factors', []),
                is_emergency=bool(data.get('is_emergency', False)),
                emergency_details=data.get('emergency_details'),
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Błąd parsowania sentiment response: {e}")
            return None
    
    def _parse_briefing_response(self, content: str) -> Optional[DailyBriefing]:
        """Parsuje odpowiedź JSON z briefingiem"""
        try:
            data = self._parse_json_response(content)
            if not data:
                return None
            
            return DailyBriefing(
                date=datetime.now(),
                overall_sentiment=float(data.get('overall_sentiment', 0)),
                market_summary=str(data.get('market_summary', '')),
                key_events=data.get('key_events', []),
                opportunities=data.get('opportunities', []),
                risks=data.get('risks', []),
                recommendation=str(data.get('recommendation', 'NEUTRAL'))
            )
        except Exception as e:
            logger.error(f"Błąd parsowania briefing response: {e}")
            return None
    
    def _parse_json_response(self, content: str) -> Optional[Dict]:
        """Wyciąga i parsuje JSON z odpowiedzi LLM"""
        try:
            # Spróbuj bezpośrednio
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Szukaj JSON w markdown code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Szukaj { ... } w tekście
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        logger.warning(f"Nie można sparsować JSON z odpowiedzi: {content[:100]}...")
        return None
    
    def _fallback_sentiment(self, news_items: List[Any]) -> Optional[SentimentResult]:
        """
        Fallback sentiment analysis bez LLM
        Używa prostej heurystyki słów kluczowych
        """
        if not news_items:
            return SentimentResult(
                score=0.0,
                confidence=0.3,
                reasoning="Brak newsów do analizy",
                key_factors=[],
                is_emergency=False,
                emergency_details=None,
                timestamp=datetime.now()
            )
        
        # Zlicz słowa kluczowe
        bullish_count = 0
        bearish_count = 0
        emergency_detected = False
        
        bullish_keywords = ['bullish', 'surge', 'rally', 'adoption', 'approval', 'partnership']
        bearish_keywords = ['bearish', 'crash', 'hack', 'ban', 'lawsuit', 'fraud']
        emergency_keywords = ['hack', 'exploit', 'crash', 'collapse', 'emergency']
        
        for news in news_items:
            title_lower = news.title.lower()
            
            for kw in bullish_keywords:
                if kw in title_lower:
                    bullish_count += 1
            
            for kw in bearish_keywords:
                if kw in title_lower:
                    bearish_count += 1
            
            for kw in emergency_keywords:
                if kw in title_lower:
                    emergency_detected = True
        
        # Oblicz prosty score
        total = bullish_count + bearish_count
        if total == 0:
            score = 0.0
        else:
            score = (bullish_count - bearish_count) / total
        
        return SentimentResult(
            score=score,
            confidence=0.4,  # Niska pewność dla heurystyki
            reasoning=f"Heurystyka: {bullish_count} bullish, {bearish_count} bearish keywords",
            key_factors=[f"Bullish: {bullish_count}", f"Bearish: {bearish_count}"],
            is_emergency=emergency_detected,
            emergency_details="Wykryto słowa kluczowe emergency (fallback)" if emergency_detected else None,
            timestamp=datetime.now()
        )
    
    def _fallback_explanation(self, trade_context: Dict) -> str:
        """Fallback wyjaśnienie bez LLM"""
        direction = trade_context.get('direction', 'N/A')
        pattern = trade_context.get('pattern', 'N/A')
        score = trade_context.get('technical_score', 0)
        
        if score >= 70:
            quality = "silny"
        elif score >= 60:
            quality = "umiarkowany"
        else:
            quality = "słaby"
        
        return f"""Trade {direction} na podstawie patternu {pattern}.
Technical score: {score:.1f}/100 - {quality} setup.
Główne czynniki: {', '.join(trade_context.get('reasoning', ['brak danych'])[:3])}
Rekomendacja: {'Ostrożność wskazana' if score < 65 else 'Setup spełnia kryteria'}."""


# Singleton instance
_llm_analyzer: Optional[LLMSentimentAnalyzer] = None


def get_llm_analyzer(config: dict) -> LLMSentimentAnalyzer:
    """Factory function dla LLM analyzer"""
    global _llm_analyzer
    if _llm_analyzer is None:
        _llm_analyzer = LLMSentimentAnalyzer(config)
    return _llm_analyzer


if __name__ == "__main__":
    # Test modułu
    import yaml
    from news_fetcher import NewsFetcher
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Dodaj config LLM do testów
    config['llm'] = {
        'enabled': True,
        'provider': 'lm_studio',
        'base_url': 'http://localhost:1234/v1',
        'model': 'llama3:8b',
        'timeout': 30,
        'temperature': 0.1
    }
    
    # Test analyzer
    analyzer = LLMSentimentAnalyzer(config)
    
    print(f"\n[BOT] LLM Available: {analyzer.is_available()}")
    
    # Pobierz newsy do testu
    config['news'] = {
        'enabled': True,
        'sources': ['coindesk', 'cointelegraph'],
        'cache_hours': 24
    }
    
    fetcher = NewsFetcher(config)
    news = fetcher.get_latest_news(hours=24)
    
    if news:
        print(f"\n[NEWS] Analizuję {len(news)} newsów...")
        
        # Test sentiment analysis
        sentiment = analyzer.analyze_news(news)
        if sentiment:
            print(f"\n[INFO] Sentiment Analysis:")
            print(f"   Score: {sentiment.score:.2f}")
            print(f"   Confidence: {sentiment.confidence:.2f}")
            print(f"   Reasoning: {sentiment.reasoning}")
            print(f"   Key factors: {sentiment.key_factors}")
            print(f"   Emergency: {sentiment.is_emergency}")
        
        # Test daily briefing
        print(f"\n[LOG] Generuję daily briefing...")
        briefing = analyzer.daily_briefing(news)
        if briefing:
            print(f"   Recommendation: {briefing.recommendation}")
            print(f"   Summary: {briefing.market_summary}")
        
        # Test emergency detection
        print(f"\n[ALERT] Sprawdzam emergency events...")
        is_emergency, details = analyzer.emergency_detection(news)
        print(f"   Emergency: {is_emergency}")
        if details:
            print(f"   Details: {details}")
        
        # Test trade explanation
        print(f"\n[TIP] Testuję wyjaśnienie trade'a...")
        explanation = analyzer.explain_trade({
            'symbol': 'BTCUSDC',
            'direction': 'LONG',
            'pattern': 'EMA_PULLBACK_BULLISH',
            'technical_score': 72.5,
            'sentiment_score': 0.35,
            'reasoning': ['Trend bullish', 'Volume confirms', 'RSI favorable']
        })
        print(f"   {explanation}")
    else:
        print("[WARNING] Brak newsów do analizy - testując fallback...")
        sentiment = analyzer._fallback_sentiment([])
        print(f"   Fallback sentiment: {sentiment.score:.2f}")
