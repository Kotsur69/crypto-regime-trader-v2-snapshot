"""
indicators.py - Moduł obliczania wskaźników technicznych

Odpowiedzialny za:
- Obliczanie EMA (9, 21, 50, 100)
- RSI i Stochastic RSI
- MACD z histogramem
- Wskaźniki wolumenowe
- ATR (Average True Range)
- Dodatkowe wskaźniki pomocnicze
"""

import logging
from typing import Dict, Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Spróbuj zaimportować pandas-ta, jeśli dostępne
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
    logger.info("[OK] Używam pandas-ta dla wskaźników")
except ImportError:
    HAS_PANDAS_TA = False
    logger.warning("[WARNING] pandas-ta niedostępne, używam własnych implementacji")


class TechnicalIndicators:
    """Klasa do obliczania wskaźników technicznych"""
    
    def __init__(self, config: dict):
        """
        Inicjalizacja kalkulatora wskaźników
        
        Args:
            config: Słownik konfiguracji z parametrami wskaźników
        """
        self.config = config.get('indicators', {})
        
        # Parametry EMA
        self.ema_fast = self.config.get('ema_fast', 9)
        self.ema_medium = self.config.get('ema_medium', 21)
        self.ema_slow = self.config.get('ema_slow', 50)
        self.ema_trend = self.config.get('ema_trend', 100)
        
        # Parametry RSI
        self.rsi_period = self.config.get('rsi_period', 14)
        self.rsi_oversold = self.config.get('rsi_oversold', 30)
        self.rsi_overbought = self.config.get('rsi_overbought', 70)
        
        # Parametry Stochastic RSI
        self.stoch_rsi_period = self.config.get('stoch_rsi_period', 14)
        self.stoch_rsi_k = self.config.get('stoch_rsi_k', 3)
        self.stoch_rsi_d = self.config.get('stoch_rsi_d', 3)
        
        # Parametry MACD
        self.macd_fast = self.config.get('macd_fast', 12)
        self.macd_slow = self.config.get('macd_slow', 26)
        self.macd_signal = self.config.get('macd_signal', 9)
        
        # Parametry Volume
        self.volume_ma_period = self.config.get('volume_ma_period', 20)
        self.volume_spike_multiplier = self.config.get('volume_spike_multiplier', 1.5)
    
    def calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Oblicza wszystkie wskaźniki dla DataFrame
        
        Args:
            df: DataFrame z kolumnami OHLCV
        
        Returns:
            DataFrame z dodanymi kolumnami wskaźników
        """
        if df.empty:
            logger.warning("Pusty DataFrame - pomijam obliczenia")
            return df
        
        # Kopia żeby nie modyfikować oryginału
        result = df.copy()
        
        # Oblicz wskaźniki
        result = self.add_ema(result)
        result = self.add_rsi(result)
        result = self.add_stochastic_rsi(result)
        result = self.add_macd(result)
        result = self.add_volume_indicators(result)
        result = self.add_atr(result)
        result = self.add_trend_indicators(result)
        
        logger.debug(f"Obliczono wskaźniki dla {len(result)} świec")
        return result
    
    def add_ema(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Dodaje EMA do DataFrame
        
        EMA (Exponential Moving Average) - średnia krocząca wykładnicza
        Używana do identyfikacji trendu i dynamicznych poziomów wsparcia/oporu
        """
        if HAS_PANDAS_TA:
            df[f'ema_{self.ema_fast}'] = ta.ema(df['close'], length=self.ema_fast)
            df[f'ema_{self.ema_medium}'] = ta.ema(df['close'], length=self.ema_medium)
            df[f'ema_{self.ema_slow}'] = ta.ema(df['close'], length=self.ema_slow)
            df[f'ema_{self.ema_trend}'] = ta.ema(df['close'], length=self.ema_trend)
        else:
            df[f'ema_{self.ema_fast}'] = self._ema(df['close'], self.ema_fast)
            df[f'ema_{self.ema_medium}'] = self._ema(df['close'], self.ema_medium)
            df[f'ema_{self.ema_slow}'] = self._ema(df['close'], self.ema_slow)
            df[f'ema_{self.ema_trend}'] = self._ema(df['close'], self.ema_trend)
        
        # Dodatkowe obliczenia EMA
        df['ema_fast'] = df[f'ema_{self.ema_fast}']
        df['ema_medium'] = df[f'ema_{self.ema_medium}']
        df['ema_slow'] = df[f'ema_{self.ema_slow}']
        df['ema_trend'] = df[f'ema_{self.ema_trend}']
        
        # Odległość ceny od EMA (w %)
        df['dist_ema_fast_pct'] = ((df['close'] - df['ema_fast']) / df['ema_fast']) * 100
        df['dist_ema_slow_pct'] = ((df['close'] - df['ema_slow']) / df['ema_slow']) * 100
        
        return df
    
    def add_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Dodaje RSI do DataFrame
        
        RSI (Relative Strength Index) - wskaźnik siły względnej
        Używany jako WARUNEK (oversold/overbought), nie bezpośredni sygnał
        """
        if HAS_PANDAS_TA:
            df['rsi'] = ta.rsi(df['close'], length=self.rsi_period)
        else:
            df['rsi'] = self._rsi(df['close'], self.rsi_period)
        
        # Warunki RSI
        df['rsi_oversold'] = df['rsi'] < self.rsi_oversold
        df['rsi_overbought'] = df['rsi'] > self.rsi_overbought
        df['rsi_neutral'] = ~(df['rsi_oversold'] | df['rsi_overbought'])
        
        # Zmiana RSI (momentum)
        df['rsi_change'] = df['rsi'].diff()
        df['rsi_rising'] = df['rsi_change'] > 0
        
        return df
    
    def add_stochastic_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Dodaje Stochastic RSI do DataFrame
        
        Stochastic RSI - bardziej wrażliwa wersja RSI
        Pomaga identyfikować lokalne ekstrema
        """
        if HAS_PANDAS_TA:
            stoch_rsi = ta.stochrsi(
                df['close'],
                length=self.stoch_rsi_period,
                rsi_length=self.stoch_rsi_period,
                k=self.stoch_rsi_k,
                d=self.stoch_rsi_d
            )
            if stoch_rsi is not None and not stoch_rsi.empty:
                df['stoch_rsi_k'] = stoch_rsi.iloc[:, 0]
                df['stoch_rsi_d'] = stoch_rsi.iloc[:, 1]
            else:
                df['stoch_rsi_k'] = np.nan
                df['stoch_rsi_d'] = np.nan
        else:
            stoch_k, stoch_d = self._stochastic_rsi(
                df['close'],
                self.stoch_rsi_period,
                self.stoch_rsi_k,
                self.stoch_rsi_d
            )
            df['stoch_rsi_k'] = stoch_k
            df['stoch_rsi_d'] = stoch_d
        
        # Warunki Stochastic RSI
        stoch_oversold = self.config.get('stoch_rsi_oversold', 20)
        stoch_overbought = self.config.get('stoch_rsi_overbought', 80)
        
        df['stoch_oversold'] = df['stoch_rsi_k'] < stoch_oversold
        df['stoch_overbought'] = df['stoch_rsi_k'] > stoch_overbought
        
        # Crossover sygnały
        df['stoch_bullish_cross'] = (df['stoch_rsi_k'] > df['stoch_rsi_d']) & \
                                    (df['stoch_rsi_k'].shift(1) <= df['stoch_rsi_d'].shift(1))
        df['stoch_bearish_cross'] = (df['stoch_rsi_k'] < df['stoch_rsi_d']) & \
                                    (df['stoch_rsi_k'].shift(1) >= df['stoch_rsi_d'].shift(1))
        
        return df
    
    def add_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Dodaje MACD do DataFrame
        
        MACD (Moving Average Convergence Divergence)
        Histogram MACD interpretuje momentum - rosnący = momentum w kierunku trendu
        """
        if HAS_PANDAS_TA:
            macd = ta.macd(
                df['close'],
                fast=self.macd_fast,
                slow=self.macd_slow,
                signal=self.macd_signal
            )
            if macd is not None and not macd.empty:
                df['macd'] = macd.iloc[:, 0]
                df['macd_histogram'] = macd.iloc[:, 1]
                df['macd_signal'] = macd.iloc[:, 2]
            else:
                df['macd'] = np.nan
                df['macd_histogram'] = np.nan
                df['macd_signal'] = np.nan
        else:
            macd_line, signal_line, histogram = self._macd(
                df['close'],
                self.macd_fast,
                self.macd_slow,
                self.macd_signal
            )
            df['macd'] = macd_line
            df['macd_signal'] = signal_line
            df['macd_histogram'] = histogram
        
        # Analiza MACD
        df['macd_above_signal'] = df['macd'] > df['macd_signal']
        df['macd_above_zero'] = df['macd'] > 0
        
        # Histogram momentum
        df['macd_hist_rising'] = df['macd_histogram'] > df['macd_histogram'].shift(1)
        df['macd_hist_falling'] = df['macd_histogram'] < df['macd_histogram'].shift(1)
        
        # Momentum shift - zmiana kierunku histogramu
        # UWAGA: shift(1) wprowadza NaN, który zmienia dtype na object
        # Rozwiązanie: użyj np.where lub porównanie z negacją
        prev_rising = df['macd_hist_rising'].shift(1)
        prev_falling = df['macd_hist_falling'].shift(1)
        # Momentum shift: obecnie true, poprzednio false lub NaN (czyli nie było rising)
        df['momentum_shift_bullish'] = (df['macd_hist_rising']) & ((prev_rising == False) | prev_rising.isna())
        df['momentum_shift_bearish'] = (df['macd_hist_falling']) & ((prev_falling == False) | prev_falling.isna())
        
        # Crossover sygnały
        df['macd_bullish_cross'] = (df['macd'] > df['macd_signal']) & \
                                   (df['macd'].shift(1) <= df['macd_signal'].shift(1))
        df['macd_bearish_cross'] = (df['macd'] < df['macd_signal']) & \
                                   (df['macd'].shift(1) >= df['macd_signal'].shift(1))
        
        return df
    
    def add_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Dodaje wskaźniki wolumenowe
        
        Wolumen potwierdza lub osłabia ruch cenowy
        - Wysoki wolumen przy ruchu = potwierdzenie
        - Niski wolumen przy ruchu = ostrzeżenie
        """
        # Volume MA
        df['volume_ma'] = df['volume'].rolling(window=self.volume_ma_period).mean()
        
        # Volume ratio (aktualny vs średnia)
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # Volume spike detection
        df['volume_spike'] = df['volume_ratio'] > self.volume_spike_multiplier
        
        # Volume trend
        df['volume_increasing'] = df['volume'] > df['volume'].shift(1)
        df['volume_decreasing'] = df['volume'] < df['volume'].shift(1)
        
        # High volume na świecy wzrostowej/spadkowej
        df['high_volume_bullish'] = (df['volume_spike']) & (df['close'] > df['open'])
        df['high_volume_bearish'] = (df['volume_spike']) & (df['close'] < df['open'])
        
        # On-Balance Volume (OBV) - prostsza wersja
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        df['obv_ma'] = df['obv'].rolling(window=self.volume_ma_period).mean()
        df['obv_trend_up'] = df['obv'] > df['obv_ma']
        
        return df
    
    def add_atr(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        Dodaje ATR (Average True Range)
        
        ATR mierzy zmienność rynku - używany do:
        - Ustawiania stop loss
        - Oceny pullbacków do EMA
        - Określania wielkości pozycji
        """
        if HAS_PANDAS_TA:
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=period)
        else:
            df['atr'] = self._atr(df, period)
        
        # ATR jako % ceny
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        
        # ATR trend
        df['atr_ma'] = df['atr'].rolling(window=period).mean()
        df['volatility_high'] = df['atr'] > df['atr_ma'] * 1.2
        df['volatility_low'] = df['atr'] < df['atr_ma'] * 0.8
        
        return df
    
    def add_trend_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Dodaje wskaźniki trendu
        
        Określa kierunek i siłę trendu na podstawie układu EMA
        """
        # Układ EMA - trend wzrostowy gdy fast > medium > slow > trend
        df['ema_bullish_stack'] = (
            (df['ema_fast'] > df['ema_medium']) &
            (df['ema_medium'] > df['ema_slow']) &
            (df['ema_slow'] > df['ema_trend'])
        )
        
        # Układ EMA - trend spadkowy gdy fast < medium < slow < trend
        df['ema_bearish_stack'] = (
            (df['ema_fast'] < df['ema_medium']) &
            (df['ema_medium'] < df['ema_slow']) &
            (df['ema_slow'] < df['ema_trend'])
        )
        
        # Cena względem EMA trendu
        df['above_trend_ema'] = df['close'] > df['ema_trend']
        df['below_trend_ema'] = df['close'] < df['ema_trend']
        
        # Overall trend direction
        df['trend_direction'] = np.where(
            df['ema_bullish_stack'], 1,
            np.where(df['ema_bearish_stack'], -1, 0)
        )
        
        # Trend strength (0-100)
        df['trend_strength'] = self._calculate_trend_strength(df)
        
        # Cena względem all EMA (kontakt z EMA)
        df['touching_ema_fast'] = (
            (df['low'] <= df['ema_fast']) & (df['high'] >= df['ema_fast'])
        )
        df['touching_ema_medium'] = (
            (df['low'] <= df['ema_medium']) & (df['high'] >= df['ema_medium'])
        )
        
        return df
    
    def _calculate_trend_strength(self, df: pd.DataFrame) -> pd.Series:
        """Oblicza siłę trendu (0-100)"""
        strength = pd.Series(index=df.index, dtype=float)
        
        # Punkty za układ EMA
        ema_points = (
            (df['ema_fast'] > df['ema_medium']).astype(int) * 10 +
            (df['ema_medium'] > df['ema_slow']).astype(int) * 10 +
            (df['ema_slow'] > df['ema_trend']).astype(int) * 10
        )
        
        # Punkty za RSI (nie skrajne = lepsze)
        rsi_points = np.where(
            (df['rsi'] > 40) & (df['rsi'] < 60), 10,
            np.where((df['rsi'] > 30) & (df['rsi'] < 70), 5, 0)
        )
        
        # Punkty za MACD
        macd_points = (
            df['macd_above_zero'].astype(int) * 10 +
            df['macd_above_signal'].astype(int) * 10 +
            df['macd_hist_rising'].astype(int) * 10
        )
        
        # Punkty za volume
        volume_points = (
            (df['volume_ratio'] > 1).astype(int) * 10 +
            df['obv_trend_up'].astype(int) * 10
        )
        
        strength = ema_points + rsi_points + macd_points + volume_points
        
        # Normalizuj do 0-100
        return strength.clip(0, 100)
    
    # ========================================
    # WŁASNE IMPLEMENTACJE WSKAŹNIKÓW
    # (używane gdy pandas-ta nie jest dostępne)
    # ========================================
    
    def _ema(self, series: pd.Series, period: int) -> pd.Series:
        """Oblicza EMA"""
        return series.ewm(span=period, adjust=False).mean()
    
    def _sma(self, series: pd.Series, period: int) -> pd.Series:
        """Oblicza SMA"""
        return series.rolling(window=period).mean()
    
    def _rsi(self, series: pd.Series, period: int) -> pd.Series:
        """Oblicza RSI"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _stochastic_rsi(
        self,
        series: pd.Series,
        period: int,
        k_period: int,
        d_period: int
    ) -> Tuple[pd.Series, pd.Series]:
        """Oblicza Stochastic RSI"""
        rsi = self._rsi(series, period)
        
        rsi_min = rsi.rolling(window=period).min()
        rsi_max = rsi.rolling(window=period).max()
        
        stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min) * 100
        stoch_k = stoch_rsi.rolling(window=k_period).mean()
        stoch_d = stoch_k.rolling(window=d_period).mean()
        
        return stoch_k, stoch_d
    
    def _macd(
        self,
        series: pd.Series,
        fast: int,
        slow: int,
        signal: int
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Oblicza MACD"""
        ema_fast = self._ema(series, fast)
        ema_slow = self._ema(series, slow)
        
        macd_line = ema_fast - ema_slow
        signal_line = self._ema(macd_line, signal)
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def _atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Oblicza ATR"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    # ========================================
    # METODY POMOCNICZE
    # ========================================
    
    def get_indicator_summary(self, df: pd.DataFrame) -> Dict:
        """
        Zwraca podsumowanie wskaźników dla ostatniej świecy
        
        Args:
            df: DataFrame z obliczonymi wskaźnikami
        
        Returns:
            Słownik z podsumowaniem
        """
        if df.empty:
            return {}
        
        last = df.iloc[-1]
        
        return {
            'timestamp': df.index[-1],
            'close': last['close'],
            
            # EMA
            'ema_fast': last.get('ema_fast', np.nan),
            'ema_medium': last.get('ema_medium', np.nan),
            'ema_slow': last.get('ema_slow', np.nan),
            'ema_trend': last.get('ema_trend', np.nan),
            'dist_ema_fast_pct': last.get('dist_ema_fast_pct', np.nan),
            
            # RSI
            'rsi': last.get('rsi', np.nan),
            'rsi_oversold': last.get('rsi_oversold', False),
            'rsi_overbought': last.get('rsi_overbought', False),
            
            # Stochastic RSI
            'stoch_rsi_k': last.get('stoch_rsi_k', np.nan),
            'stoch_rsi_d': last.get('stoch_rsi_d', np.nan),
            
            # MACD
            'macd': last.get('macd', np.nan),
            'macd_signal': last.get('macd_signal', np.nan),
            'macd_histogram': last.get('macd_histogram', np.nan),
            'macd_hist_rising': last.get('macd_hist_rising', False),
            
            # Volume
            'volume_ratio': last.get('volume_ratio', np.nan),
            'volume_spike': last.get('volume_spike', False),
            
            # Trend
            'trend_direction': last.get('trend_direction', 0),
            'trend_strength': last.get('trend_strength', 0),
            'ema_bullish_stack': last.get('ema_bullish_stack', False),
            'ema_bearish_stack': last.get('ema_bearish_stack', False),
            
            # ATR
            'atr': last.get('atr', np.nan),
            'atr_pct': last.get('atr_pct', np.nan),
        }
    
    def is_valid_data(self, df: pd.DataFrame) -> bool:
        """
        Sprawdza czy dane mają wystarczającą historię dla wskaźników
        
        Args:
            df: DataFrame z danymi
        
        Returns:
            True jeśli dane są wystarczające
        """
        min_required = max(
            self.ema_trend,
            self.macd_slow + self.macd_signal,
            self.volume_ma_period
        ) + 10  # bufor
        
        return len(df) >= min_required
    
    # ========================================
    # VWAP (Volume Weighted Average Price)
    # ========================================
    
    def add_vwap(self, df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
        """
        Dodaje VWAP do DataFrame dla wszystkich sesji
        
        Args:
            df: DataFrame z kolumnami OHLCV i indeksem datetime
            config: Opcjonalna konfiguracja VWAP
        
        Returns:
            DataFrame z kolumnami VWAP
        """
        if df.empty:
            return df
        
        # Oblicz VWAP dla każdej sesji
        session_vwaps = self.calculate_session_vwaps(df, config)
        
        for session_name, vwap_series in session_vwaps.items():
            df[f'vwap_{session_name}'] = vwap_series
        
        # Dodaj pozycję ceny względem VWAP
        df = self._add_vwap_position(df)
        
        return df
    
    def calculate_vwap(
        self,
        df: pd.DataFrame,
        session_start_hour: int = 0,
        reset_daily: bool = True
    ) -> pd.Series:
        """
        Oblicza VWAP od określonej godziny UTC
        
        Formula: VWAP = Σ(Typical Price × Volume) / Σ(Volume)
        Typical Price = (High + Low + Close) / 3
        
        Args:
            df: DataFrame z kolumnami high, low, close, volume
            session_start_hour: Godzina UTC rozpoczęcia sesji (0-23)
            reset_daily: Czy resetować VWAP codziennie
        
        Returns:
            Series z wartościami VWAP
        """
        if df.empty:
            return pd.Series(index=df.index, dtype=float)
        
        # Oblicz Typical Price
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        
        # Oblicz kumulatywne wartości
        tp_volume = typical_price * df['volume']
        
        if reset_daily:
            # Znajdź punkty reset (początek sesji)
            if isinstance(df.index, pd.DatetimeIndex):
                # Grupuj po dacie i resetuj VWAP
                session_groups = self._get_session_groups(df.index, session_start_hour)
                
                vwap = pd.Series(index=df.index, dtype=float)
                
                for session_id in session_groups.unique():
                    mask = session_groups == session_id
                    cum_tp_vol = tp_volume[mask].cumsum()
                    cum_vol = df.loc[mask, 'volume'].cumsum()
                    
                    # Unikaj dzielenia przez zero
                    with np.errstate(divide='ignore', invalid='ignore'):
                        session_vwap = np.where(cum_vol > 0, cum_tp_vol / cum_vol, np.nan)
                    
                    vwap.loc[mask] = session_vwap
                
                return vwap
            else:
                # Fallback dla indeksu nie-datetime
                cum_tp_vol = tp_volume.cumsum()
                cum_vol = df['volume'].cumsum()
        else:
            cum_tp_vol = tp_volume.cumsum()
            cum_vol = df['volume'].cumsum()
        
        # Unikaj dzielenia przez zero
        with np.errstate(divide='ignore', invalid='ignore'):
            vwap = np.where(cum_vol > 0, cum_tp_vol / cum_vol, np.nan)
        
        return pd.Series(vwap, index=df.index)
    
    def _get_session_groups(self, index: pd.DatetimeIndex, session_start_hour: int) -> pd.Series:
        """
        Tworzy grupowanie sesji dla VWAP
        
        Args:
            index: DatetimeIndex z timestampami
            session_start_hour: Godzina rozpoczęcia sesji
        
        Returns:
            Series z identyfikatorami sesji
        """
        # Konwertuj do UTC jeśli ma timezone
        if index.tz is not None:
            index = index.tz_convert('UTC').tz_localize(None)
        
        # Oblicz offset od session_start_hour
        hours = index.hour
        dates = index.date
        
        # Sesja zaczyna się o session_start_hour UTC
        # Wszystko przed tą godziną należy do poprzedniej sesji
        session_dates = pd.Series([
            d if h >= session_start_hour else d - pd.Timedelta(days=1)
            for d, h in zip(dates, hours)
        ], index=index)
        
        # Utwórz unikalny ID sesji
        session_ids = session_dates.astype(str) + '_' + str(session_start_hour)
        
        return session_ids
    
    def calculate_session_vwaps(self, df: pd.DataFrame, config: dict = None) -> Dict[str, pd.Series]:
        """
        Oblicza VWAP dla wszystkich standardowych sesji tradingowych
        
        Sesje:
        - Asian: 00:00 UTC (Tokyo open)
        - European: 09:00 UTC (London open)  
        - US: 15:30 UTC (NYSE open)
        - Daily: 00:00 UTC (rolling 24h)
        
        Args:
            df: DataFrame z danymi OHLCV
            config: Opcjonalna konfiguracja z godzinami sesji
        
        Returns:
            Dict z VWAP dla każdej sesji
        """
        if config is None:
            config = {}
        
        vwap_config = config.get('vwap', {})
        sessions = vwap_config.get('sessions', {
            'asian': '00:00',
            'european': '09:00',
            'us': '15:30'
        })
        
        result = {}
        
        # Parse session times
        session_hours = {}
        for name, time_str in sessions.items():
            try:
                hour = int(time_str.split(':')[0])
                session_hours[name] = hour
            except:
                logger.warning(f"Invalid session time format: {name}={time_str}")
        
        # Calculate VWAP for each session
        for session_name, start_hour in session_hours.items():
            vwap = self.calculate_vwap(df, session_start_hour=start_hour, reset_daily=True)
            result[session_name] = vwap
        
        # Always add daily VWAP (00:00 UTC)
        if 'daily' not in result:
            result['daily'] = self.calculate_vwap(df, session_start_hour=0, reset_daily=True)
        
        return result
    
    def get_current_session(self) -> str:
        """
        Określa aktualną sesję tradingową
        
        Returns:
            Nazwa sesji: 'asian', 'european', 'us', lub 'asian' (po zamknięciu US)
        """
        from datetime import datetime, timezone
        
        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour
        
        # Session boundaries (UTC):
        # Asian: 00:00 - 09:00 UTC
        # European: 09:00 - 15:30 UTC
        # US: 15:30 - 22:00 UTC
        # Late night: 22:00 - 00:00 UTC (effectively Asian pre-market)
        
        if 0 <= hour < 9:
            return 'asian'
        elif 9 <= hour < 15:
            return 'european'
        elif 15 <= hour < 22:
            return 'us'
        else:  # 22-24
            return 'asian'  # Transition to Asian session
    
    def vwap_position(self, price: float, vwap: float) -> Dict:
        """
        Określa pozycję ceny względem VWAP
        
        Args:
            price: Aktualna cena
            vwap: Wartość VWAP
        
        Returns:
            Dict z pozycją i odległością:
            {
                'position': 'above' | 'below' | 'at',
                'distance_pct': float,
                'strength': 'strong' | 'moderate' | 'weak'
            }
        """
        if vwap == 0 or np.isnan(vwap):
            return {
                'position': 'unknown',
                'distance_pct': 0,
                'strength': 'unknown'
            }
        
        distance_pct = ((price - vwap) / vwap) * 100
        
        # Determine position
        if abs(distance_pct) < 0.1:
            position = 'at'
        elif distance_pct > 0:
            position = 'above'
        else:
            position = 'below'
        
        # Determine strength
        abs_dist = abs(distance_pct)
        if abs_dist < 0.3:
            strength = 'weak'
        elif abs_dist < 1.0:
            strength = 'moderate'
        else:
            strength = 'strong'
        
        return {
            'position': position,
            'distance_pct': distance_pct,
            'strength': strength
        }
    
    def _add_vwap_position(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Dodaje kolumny z pozycją ceny względem VWAP
        
        Args:
            df: DataFrame z obliczonymi VWAP
        
        Returns:
            DataFrame z dodatkowymi kolumnami
        """
        # Znajdź aktualną sesję
        current_session = self.get_current_session()
        vwap_col = f'vwap_{current_session}'
        
        if vwap_col not in df.columns:
            vwap_col = 'vwap_daily'
        
        if vwap_col in df.columns:
            # Pozycja względem VWAP sesji
            df['price_vs_vwap_pct'] = ((df['close'] - df[vwap_col]) / df[vwap_col]) * 100
            df['above_vwap'] = df['close'] > df[vwap_col]
            df['below_vwap'] = df['close'] < df[vwap_col]
            
            # Dotknięcie VWAP (+/-0.2%)
            df['touching_vwap'] = abs(df['price_vs_vwap_pct']) < 0.2
            
            # VWAP jako dynamiczny S/R
            # Bounce from VWAP
            df['vwap_bounce_potential'] = (
                df['touching_vwap'] &
                (df['volume_ratio'] > 1.3) if 'volume_ratio' in df.columns else df['touching_vwap']
            )
        
        return df
    
    def get_vwap_summary(self, df: pd.DataFrame) -> Dict:
        """
        Zwraca podsumowanie VWAP dla ostatniej świecy
        
        Args:
            df: DataFrame z obliczonymi VWAP
        
        Returns:
            Dict z podsumowaniem VWAP
        """
        if df.empty:
            return {}
        
        last = df.iloc[-1]
        current_session = self.get_current_session()
        
        summary = {
            'current_session': current_session,
            'current_price': last['close'],
        }
        
        # Dodaj wartości VWAP dla każdej sesji
        for col in df.columns:
            if col.startswith('vwap_'):
                session_name = col.replace('vwap_', '')
                vwap_value = last[col]
                
                if not np.isnan(vwap_value):
                    position = self.vwap_position(last['close'], vwap_value)
                    summary[f'{session_name}_vwap'] = vwap_value
                    summary[f'{session_name}_position'] = position['position']
                    summary[f'{session_name}_distance_pct'] = position['distance_pct']
        
        # Dodaj pozycję względem aktywnego VWAP
        active_vwap_col = f'vwap_{current_session}'
        if active_vwap_col in df.columns:
            active_vwap = last[active_vwap_col]
            if not np.isnan(active_vwap):
                summary['active_vwap'] = active_vwap
                summary['active_position'] = self.vwap_position(last['close'], active_vwap)
        
        return summary


if __name__ == "__main__":
    # Test modułu
    import yaml
    from data_fetcher import DataFetcher
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Pobierz dane testowe
    fetcher = DataFetcher(config)
    df = fetcher.get_klines('BTCUSDC', '15m', limit=200)
    
    # Oblicz wskaźniki
    indicators = TechnicalIndicators(config)
    df_with_indicators = indicators.calculate_all(df)
    
    # Pokaż podsumowanie
    summary = indicators.get_indicator_summary(df_with_indicators)
    
    print("\n[INFO] Podsumowanie wskaźników dla BTCUSDC:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
