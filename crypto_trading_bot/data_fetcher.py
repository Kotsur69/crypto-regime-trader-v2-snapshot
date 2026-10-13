"""
data_fetcher.py - Moduł pobierania danych z Binance

Odpowiedzialny za:
- Połączenie z Binance API (testnet/production)
- Pobieranie danych świecowych (OHLCV)
- Obsługa WebSocket dla real-time data
- Cache i zarządzanie danymi historycznymi
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from binance.client import Client
from binance.exceptions import BinanceAPIException
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


class DataFetcher:
    """Klasa do pobierania danych rynkowych z Binance"""
    
    # Mapowanie timeframe na minuty
    TIMEFRAME_MINUTES = {
        '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
        '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720,
        '1d': 1440, '1w': 10080
    }
    
    def __init__(self, config: dict):
        """
        Inicjalizacja DataFetcher
        
        Args:
            config: Słownik konfiguracji z kluczami API i ustawieniami
        """
        self.config = config
        self.client = None
        self.cache: Dict[str, pd.DataFrame] = {}
        self.last_fetch_time: Dict[str, datetime] = {}
        
        # Sprawdź czy używamy testnet
        self.use_testnet = config.get('binance', {}).get('testnet', True)
        
        if config.get('safety', {}).get('force_testnet_only', True) and not self.use_testnet:
            raise ValueError("SAFETY: Konfiguracja wymusza użycie testnet!")
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Inicjalizacja klienta Binance"""
        try:
            api_key = self.config['binance']['api_key']
            api_secret = self.config['binance']['api_secret']
            
            if self.use_testnet:
                self.client = Client(api_key, api_secret, testnet=True)
                logger.info("[OK] Połączono z Binance TESTNET")
            else:
                # UWAGA: Production mode - używaj ostrożnie!
                self.client = Client(api_key, api_secret)
                logger.warning("[WARNING] UWAGA: Połączono z Binance PRODUCTION!")
            
            # Test połączenia
            self.client.ping()
            server_time = self.client.get_server_time()
            logger.info(f"Server time: {datetime.fromtimestamp(server_time['serverTime']/1000)}")
            
        except BinanceAPIException as e:
            logger.error(f"[ERROR] Błąd połączenia z Binance: {e}")
            raise
        except Exception as e:
            logger.error(f"[ERROR] Nieoczekiwany błąd: {e}")
            raise
    
    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Pobiera dane świecowe (OHLCV) dla danego symbolu
        
        Args:
            symbol: Para walutowa (np. 'BTCUSDC')
            interval: Timeframe ('1m', '5m', '15m', '1h', etc.)
            limit: Liczba świec do pobrania (max 1000)
            start_time: Początek okresu (opcjonalnie)
            end_time: Koniec okresu (opcjonalnie)
        
        Returns:
            DataFrame z kolumnami: open, high, low, close, volume, etc.
        """
        cache_key = f"{symbol}_{interval}"
        
        # Sprawdź cache (jeśli dane są świeże)
        if self._is_cache_valid(cache_key, interval):
            logger.debug(f"Używam cache dla {cache_key}")
            return self.cache[cache_key].copy()
        
        try:
            # Przygotuj parametry
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': min(limit, 1000)
            }
            
            if start_time:
                params['startTime'] = int(start_time.timestamp() * 1000)
            if end_time:
                params['endTime'] = int(end_time.timestamp() * 1000)
            
            # Pobierz dane
            klines = self.client.get_klines(**params)
            
            # Konwertuj do DataFrame
            df = self._klines_to_dataframe(klines)
            
            # Zapisz do cache
            self.cache[cache_key] = df
            self.last_fetch_time[cache_key] = datetime.now()
            
            logger.info(f"[INFO] Pobrano {len(df)} świec dla {symbol} ({interval})")
            return df.copy()
            
        except BinanceAPIException as e:
            logger.error(f"[ERROR] Błąd API przy pobieraniu {symbol}: {e}")
            # Zwróć cache jeśli istnieje
            if cache_key in self.cache:
                logger.warning(f"Używam starego cache dla {cache_key}")
                return self.cache[cache_key].copy()
            raise
    
    def _klines_to_dataframe(self, klines: List) -> pd.DataFrame:
        """
        Konwertuje surowe dane klines do DataFrame
        
        Args:
            klines: Lista danych z API Binance
        
        Returns:
            Sformatowany DataFrame
        """
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        # Konwersja typów
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
        
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 
                       'quote_volume', 'taker_buy_base', 'taker_buy_quote']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['trades'] = df['trades'].astype(int)
        
        # Ustaw index na czas
        df.set_index('open_time', inplace=True)
        
        # Usuń niepotrzebne kolumny
        df.drop(['ignore'], axis=1, inplace=True)
        
        return df
    
    def _is_cache_valid(self, cache_key: str, interval: str) -> bool:
        """
        Sprawdza czy cache jest aktualny
        
        Args:
            cache_key: Klucz cache
            interval: Timeframe
        
        Returns:
            True jeśli cache jest aktualny
        """
        if cache_key not in self.cache or cache_key not in self.last_fetch_time:
            return False
        
        # Cache jest ważny przez połowę okresu świecy
        minutes = self.TIMEFRAME_MINUTES.get(interval, 15)
        max_age = timedelta(minutes=minutes / 2)
        
        return datetime.now() - self.last_fetch_time[cache_key] < max_age
    
    def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        days: int = 30
    ) -> pd.DataFrame:
        """
        Pobiera historyczne dane dla backtestingu
        
        Args:
            symbol: Para walutowa
            interval: Timeframe
            days: Liczba dni wstecz
        
        Returns:
            DataFrame z danymi historycznymi
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        all_data = []
        current_start = start_time
        
        logger.info(f"[DOWNLOAD] Pobieranie {days} dni danych dla {symbol}...")
        
        while current_start < end_time:
            try:
                df = self.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=1000,
                    start_time=current_start,
                    end_time=end_time
                )
                
                if df.empty:
                    break
                
                all_data.append(df)
                
                # Następny okres
                current_start = df.index[-1] + timedelta(minutes=1)
                
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Błąd przy pobieraniu historii: {e}")
                break
        
        if not all_data:
            return pd.DataFrame()
        
        # Połącz wszystkie dane
        result = pd.concat(all_data)
        result = result[~result.index.duplicated(keep='last')]
        result.sort_index(inplace=True)
        
        logger.info(f"[OK] Pobrano {len(result)} świec historycznych dla {symbol}")
        return result
    
    def get_current_price(self, symbol: str) -> float:
        """
        Pobiera aktualną cenę dla symbolu
        
        Args:
            symbol: Para walutowa
        
        Returns:
            Aktualna cena
        """
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except BinanceAPIException as e:
            logger.error(f"Błąd pobierania ceny {symbol}: {e}")
            raise
    
    def get_orderbook(self, symbol: str, limit: int = 100) -> Dict:
        """
        Pobiera order book dla symbolu
        
        Args:
            symbol: Para walutowa
            limit: Głębokość order book
        
        Returns:
            Słownik z bids i asks
        """
        try:
            depth = self.client.get_order_book(symbol=symbol, limit=limit)
            return {
                'bids': [(float(p), float(q)) for p, q in depth['bids']],
                'asks': [(float(p), float(q)) for p, q in depth['asks']],
                'timestamp': datetime.now()
            }
        except BinanceAPIException as e:
            logger.error(f"Błąd pobierania orderbook {symbol}: {e}")
            raise
    
    def get_24h_stats(self, symbol: str) -> Dict:
        """
        Pobiera statystyki 24h dla symbolu
        
        Args:
            symbol: Para walutowa
        
        Returns:
            Słownik ze statystykami
        """
        try:
            stats = self.client.get_ticker(symbol=symbol)
            return {
                'price_change': float(stats['priceChange']),
                'price_change_pct': float(stats['priceChangePercent']),
                'high_24h': float(stats['highPrice']),
                'low_24h': float(stats['lowPrice']),
                'volume_24h': float(stats['volume']),
                'quote_volume_24h': float(stats['quoteVolume']),
                'trades_24h': int(stats['count'])
            }
        except BinanceAPIException as e:
            logger.error(f"Błąd pobierania statystyk {symbol}: {e}")
            raise
    
    def get_all_pairs_data(
        self,
        pairs: List[str],
        interval: str,
        limit: int = 500
    ) -> Dict[str, pd.DataFrame]:
        """
        Pobiera dane dla wielu par jednocześnie
        
        Args:
            pairs: Lista par walutowych
            interval: Timeframe
            limit: Liczba świec
        
        Returns:
            Słownik {symbol: DataFrame}
        """
        result = {}
        
        for pair in pairs:
            try:
                result[pair] = self.get_klines(pair, interval, limit)
            except Exception as e:
                logger.error(f"Błąd pobierania danych dla {pair}: {e}")
                result[pair] = pd.DataFrame()
        
        return result
    
    def check_connection(self) -> bool:
        """
        Sprawdza połączenie z API
        
        Returns:
            True jeśli połączenie działa
        """
        try:
            self.client.ping()
            return True
        except:
            return False
    
    def reconnect(self) -> bool:
        """
        Próbuje ponownie połączyć z API
        
        Returns:
            True jeśli udało się połączyć
        """
        logger.info("[SYNC] Próba ponownego połączenia...")
        
        for attempt in range(3):
            try:
                self._initialize_client()
                return True
            except Exception as e:
                logger.warning(f"Próba {attempt + 1}/3 nieudana: {e}")
                time.sleep(5 * (attempt + 1))
        
        logger.error("[ERROR] Nie udało się ponownie połączyć")
        return False
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Pobiera informacje o symbolu (precyzja, limity)
        
        Args:
            symbol: Para walutowa
        
        Returns:
            Słownik z informacjami o symbolu
        """
        try:
            info = self.client.get_symbol_info(symbol)
            if info:
                # Wyciągnij ważne filtry
                filters = {f['filterType']: f for f in info['filters']}
                
                return {
                    'symbol': symbol,
                    'base_asset': info['baseAsset'],
                    'quote_asset': info['quoteAsset'],
                    'status': info['status'],
                    'price_precision': int(filters.get('PRICE_FILTER', {}).get('tickSize', '0.01').find('1') - 1),
                    'qty_precision': int(filters.get('LOT_SIZE', {}).get('stepSize', '0.01').find('1') - 1),
                    'min_qty': float(filters.get('LOT_SIZE', {}).get('minQty', 0)),
                    'min_notional': float(filters.get('NOTIONAL', {}).get('minNotional', 0))
                }
            return None
        except Exception as e:
            logger.error(f"Błąd pobierania info dla {symbol}: {e}")
            return None


class DataFetcherAsync:
    """Asynchroniczna wersja DataFetcher dla lepszej wydajności"""
    
    def __init__(self, config: dict):
        self.config = config
        self.base_url = config['binance'].get('testnet_url', 'https://testnet.binance.vision')
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_klines_async(
        self,
        symbol: str,
        interval: str,
        limit: int = 500
    ) -> pd.DataFrame:
        """Asynchroniczne pobieranie klines"""
        url = f"{self.base_url}/api/v3/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        async with self.session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return self._klines_to_dataframe(data)
            else:
                raise Exception(f"API error: {response.status}")
    
    def _klines_to_dataframe(self, klines: List) -> pd.DataFrame:
        """Konwersja do DataFrame (identyczna z synchroniczną wersją)"""
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
        
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 
                       'quote_volume', 'taker_buy_base', 'taker_buy_quote']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.set_index('open_time', inplace=True)
        df.drop(['ignore'], axis=1, inplace=True)
        
        return df
    
    async def get_all_pairs_async(
        self,
        pairs: List[str],
        interval: str,
        limit: int = 500
    ) -> Dict[str, pd.DataFrame]:
        """Pobiera dane dla wielu par równolegle"""
        tasks = [
            self.get_klines_async(pair, interval, limit)
            for pair in pairs
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            pair: result if not isinstance(result, Exception) else pd.DataFrame()
            for pair, result in zip(pairs, results)
        }


if __name__ == "__main__":
    # Test modułu
    import yaml
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Test DataFetcher
    fetcher = DataFetcher(config)
    
    # Pobierz dane testowe
    df = fetcher.get_klines('BTCUSDC', '15m', limit=100)
    print(f"\nOstatnie 5 świec BTCUSDC:")
    print(df.tail())
    
    # Pobierz aktualną cenę
    price = fetcher.get_current_price('BTCUSDC')
    print(f"\nAktualna cena BTC: {price} USDC")
