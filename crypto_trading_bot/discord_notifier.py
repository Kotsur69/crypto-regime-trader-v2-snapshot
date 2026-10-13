#!/usr/bin/env python3
"""
discord_notifier.py - Discord Webhook Notifications

Powiadomienia Discord dla:
- Nowych trade'ów (entry/exit)
- Osiągnięcia TP/SL
- Drawdown warnings
- Emergency stop
- Daily summary
"""

import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from enum import Enum
import requests
import threading
from queue import Queue

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Typy alertów"""
    TRADE_ENTRY = "trade_entry"
    TRADE_EXIT = "trade_exit"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    DRAWDOWN_WARNING = "drawdown_warning"
    EMERGENCY_STOP = "emergency_stop"
    DAILY_SUMMARY = "daily_summary"
    PATTERN_DETECTED = "pattern_detected"
    INFO = "info"
    ERROR = "error"


@dataclass
class DiscordEmbed:
    """Struktura embed dla Discord"""
    title: str
    description: str
    color: int
    fields: List[Dict[str, Any]] = None
    footer: str = None
    timestamp: str = None
    thumbnail: str = None
    
    def to_dict(self) -> Dict:
        embed = {
            "title": self.title,
            "description": self.description,
            "color": self.color
        }
        
        if self.fields:
            embed["fields"] = self.fields
        
        if self.footer:
            embed["footer"] = {"text": self.footer}
        
        if self.timestamp:
            embed["timestamp"] = self.timestamp
        
        if self.thumbnail:
            embed["thumbnail"] = {"url": self.thumbnail}
        
        return embed


class DiscordNotifier:
    """
    System powiadomień Discord przez webhook
    
    Używa kolejki i osobnego wątku do wysyłania,
    aby nie blokować głównej pętli tradingowej.
    """
    
    # Kolory dla różnych typów alertów
    COLORS = {
        "profit": 0x00FF00,      # Zielony
        "loss": 0xFF0000,        # Czerwony
        "warning": 0xFFA500,     # Pomarańczowy
        "info": 0x00BFFF,        # Niebieski
        "emergency": 0x8B0000,   # Ciemnoczerwony
        "neutral": 0x808080      # Szary
    }
    
    def __init__(self, config: dict):
        """
        Inicjalizacja notyfikatora
        
        Args:
            config: Konfiguracja z sekcją 'discord'
        """
        self.config = config.get('discord', {})
        self.enabled = self.config.get('enabled', False)
        self.webhook_url = self.config.get('webhook_url', '')
        
        # Opcjonalnie z zmiennych środowiskowych
        if not self.webhook_url:
            self.webhook_url = os.environ.get('DISCORD_WEBHOOK_URL', '')
        
        # Ustawienia
        self.bot_name = self.config.get('bot_name', '[BOT] Crypto Trading Bot')
        self.avatar_url = self.config.get('avatar_url', '')
        self.mention_on_emergency = self.config.get('mention_on_emergency', '')
        self.daily_summary_hour = self.config.get('daily_summary_hour', 23)
        
        # Rate limiting
        self.min_interval = self.config.get('min_interval_seconds', 1)
        self.last_send_time = None
        
        # Kolejka wiadomości
        self.message_queue = Queue()
        self.worker_thread = None
        self.running = False
        
        # Sprawdź konfigurację
        if self.enabled and not self.webhook_url:
            logger.warning("[WARNING] Discord enabled ale brak webhook_url - wyłączam")
            self.enabled = False
        
        if self.enabled:
            self._start_worker()
            logger.info("[OK] Discord Notifier zainicjalizowany")
        else:
            logger.info("[INFO] Discord Notifier wyłączony")
    
    def _start_worker(self):
        """Uruchamia wątek wysyłający wiadomości"""
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
    
    def _worker_loop(self):
        """Pętla wątku wysyłającego"""
        while self.running:
            try:
                # Pobierz z kolejki (timeout 1s)
                message = self.message_queue.get(timeout=1)
                self._send_webhook(message)
                self.message_queue.task_done()
            except Exception:
                # Timeout lub błąd - kontynuuj
                pass
    
    def _send_webhook(self, payload: Dict) -> bool:
        """Wysyła wiadomość przez webhook"""
        if not self.enabled:
            return False
        
        try:
            # Rate limiting
            if self.last_send_time:
                elapsed = (datetime.now() - self.last_send_time).total_seconds()
                if elapsed < self.min_interval:
                    import time
                    time.sleep(self.min_interval - elapsed)
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            self.last_send_time = datetime.now()
            
            if response.status_code in [200, 204]:
                return True
            else:
                logger.error(f"Discord webhook error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Discord send error: {e}")
            return False
    
    def _create_payload(self, embed: DiscordEmbed, content: str = None) -> Dict:
        """Tworzy payload dla webhook"""
        payload = {
            "username": self.bot_name,
            "embeds": [embed.to_dict()]
        }
        
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url
        
        if content:
            payload["content"] = content
        
        return payload
    
    def send(self, alert_type: AlertType, **kwargs):
        """Wysyła alert do Discord"""
        if not self.enabled:
            return
        
        try:
            embed = self._create_embed(alert_type, **kwargs)
            content = kwargs.get('content')
            
            # Dla emergency dodaj mention
            if alert_type == AlertType.EMERGENCY_STOP and self.mention_on_emergency:
                content = f"{self.mention_on_emergency} [ALERT] EMERGENCY!"
            
            payload = self._create_payload(embed, content)
            self.message_queue.put(payload)
            
        except Exception as e:
            logger.error(f"Error creating Discord message: {e}")
    
    def _create_embed(self, alert_type: AlertType, **kwargs) -> DiscordEmbed:
        """Tworzy embed na podstawie typu alertu"""
        
        if alert_type == AlertType.TRADE_ENTRY:
            return self._embed_trade_entry(**kwargs)
        elif alert_type == AlertType.TRADE_EXIT:
            return self._embed_trade_exit(**kwargs)
        elif alert_type == AlertType.TAKE_PROFIT:
            return self._embed_take_profit(**kwargs)
        elif alert_type == AlertType.STOP_LOSS:
            return self._embed_stop_loss(**kwargs)
        elif alert_type == AlertType.TRAILING_STOP:
            return self._embed_trailing_stop(**kwargs)
        elif alert_type == AlertType.DRAWDOWN_WARNING:
            return self._embed_drawdown_warning(**kwargs)
        elif alert_type == AlertType.EMERGENCY_STOP:
            return self._embed_emergency_stop(**kwargs)
        elif alert_type == AlertType.DAILY_SUMMARY:
            return self._embed_daily_summary(**kwargs)
        elif alert_type == AlertType.PATTERN_DETECTED:
            return self._embed_pattern(**kwargs)
        elif alert_type == AlertType.ERROR:
            return self._embed_error(**kwargs)
        else:
            return self._embed_info(**kwargs)
    
    def _embed_trade_entry(self, **kwargs) -> DiscordEmbed:
        """Embed dla nowego trade'a"""
        symbol = kwargs.get('symbol', 'UNKNOWN')
        direction = kwargs.get('direction', 'LONG')
        entry_price = kwargs.get('entry_price', 0)
        stop_loss = kwargs.get('stop_loss', 0)
        take_profit = kwargs.get('take_profit', 0)
        quantity = kwargs.get('quantity', 0)
        value = kwargs.get('value', 0)
        risk = kwargs.get('risk', 0)
        pattern = kwargs.get('pattern', '')
        score = kwargs.get('score', 0)
        
        emoji = "[GREEN]" if direction == "LONG" else "[RED]"
        
        return DiscordEmbed(
            title=f"{emoji} NOWY TRADE: {symbol}",
            description=f"**Kierunek:** {direction}\n**Pattern:** {pattern}",
            color=self.COLORS['info'],
            fields=[
                {"name": "[UP] Entry Price", "value": f"`{entry_price:.4f}`", "inline": True},
                {"name": "[STOP] Stop Loss", "value": f"`{stop_loss:.4f}`", "inline": True},
                {"name": "[TARGET] Take Profit", "value": f"`{take_profit:.4f}`", "inline": True},
                {"name": "[INFO] Quantity", "value": f"`{quantity:.6f}`", "inline": True},
                {"name": "[$] Value", "value": f"`{value:.2f} USDC`", "inline": True},
                {"name": "[WARNING] Risk", "value": f"`{risk:.2f} USDC`", "inline": True},
                {"name": "[TARGET] Score", "value": f"`{score:.0f}/100`", "inline": True}
            ],
            footer="Crypto Trading Bot",
            timestamp=datetime.utcnow().isoformat()
        )
    
    def _embed_trade_exit(self, **kwargs) -> DiscordEmbed:
        """Embed dla zamknięcia trade'a"""
        symbol = kwargs.get('symbol', 'UNKNOWN')
        direction = kwargs.get('direction', 'LONG')
        entry_price = kwargs.get('entry_price', 0)
        exit_price = kwargs.get('exit_price', 0)
        pnl = kwargs.get('pnl', 0)
        pnl_pct = kwargs.get('pnl_pct', 0)
        reason = kwargs.get('reason', 'manual')
        duration = kwargs.get('duration', '')
        
        color = self.COLORS['profit'] if pnl > 0 else self.COLORS['loss']
        emoji = "[OK]" if pnl > 0 else "[ERROR]"
        
        return DiscordEmbed(
            title=f"{emoji} TRADE ZAMKNIĘTY: {symbol}",
            description=f"**Powód:** {reason}",
            color=color,
            fields=[
                {"name": "[UP] Entry", "value": f"`{entry_price:.4f}`", "inline": True},
                {"name": "[DOWN] Exit", "value": f"`{exit_price:.4f}`", "inline": True},
                {"name": "[$] PnL", "value": f"`{pnl:+.2f} USDC`", "inline": True},
                {"name": "[INFO] PnL %", "value": f"`{pnl_pct:+.2f}%`", "inline": True},
                {"name": "[TIMER] Duration", "value": f"`{duration}`", "inline": True}
            ],
            footer="Crypto Trading Bot",
            timestamp=datetime.utcnow().isoformat()
        )
    
    def _embed_take_profit(self, **kwargs) -> DiscordEmbed:
        """Embed dla osiągnięcia TP"""
        kwargs['reason'] = '[TARGET] TAKE PROFIT'
        return self._embed_trade_exit(**kwargs)
    
    def _embed_stop_loss(self, **kwargs) -> DiscordEmbed:
        """Embed dla osiągnięcia SL"""
        kwargs['reason'] = '[STOP] STOP LOSS'
        return self._embed_trade_exit(**kwargs)
    
    def _embed_trailing_stop(self, **kwargs) -> DiscordEmbed:
        """Embed dla trailing stop"""
        kwargs['reason'] = '[UP] TRAILING STOP'
        return self._embed_trade_exit(**kwargs)
    
    def _embed_drawdown_warning(self, **kwargs) -> DiscordEmbed:
        """Embed dla ostrzeżenia o drawdown"""
        current_drawdown = kwargs.get('current_drawdown', 0)
        max_allowed = kwargs.get('max_allowed', 0)
        daily_pnl = kwargs.get('daily_pnl', 0)
        
        return DiscordEmbed(
            title="[WARNING] DRAWDOWN WARNING",
            description="Zbliżamy się do limitu dziennego drawdown!",
            color=self.COLORS['warning'],
            fields=[
                {"name": "[DOWN] Current Drawdown", "value": f"`{current_drawdown:.2f}%`", "inline": True},
                {"name": "[ALERT] Max Allowed", "value": f"`{max_allowed:.2f}%`", "inline": True},
                {"name": "[$] Daily PnL", "value": f"`{daily_pnl:+.2f} USDC`", "inline": True}
            ],
            footer="Crypto Trading Bot - Risk Alert",
            timestamp=datetime.utcnow().isoformat()
        )
    
    def _embed_emergency_stop(self, **kwargs) -> DiscordEmbed:
        """Embed dla emergency stop"""
        reason = kwargs.get('reason', 'Unknown')
        daily_pnl = kwargs.get('daily_pnl', 0)
        consecutive_losses = kwargs.get('consecutive_losses', 0)
        
        return DiscordEmbed(
            title="[ALERT] EMERGENCY STOP ACTIVATED",
            description=f"**Powód:** {reason}\n\nBot został zatrzymany. Wymagana manualna interwencja.",
            color=self.COLORS['emergency'],
            fields=[
                {"name": "[$] Daily PnL", "value": f"`{daily_pnl:+.2f} USDC`", "inline": True},
                {"name": "[DOWN] Consecutive Losses", "value": f"`{consecutive_losses}`", "inline": True}
            ],
            footer="URGENT - Manual intervention required",
            timestamp=datetime.utcnow().isoformat()
        )
    
    def _embed_daily_summary(self, **kwargs) -> DiscordEmbed:
        """Embed dla dziennego podsumowania"""
        date = kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))
        trades_count = kwargs.get('trades_count', 0)
        wins = kwargs.get('wins', 0)
        losses = kwargs.get('losses', 0)
        daily_pnl = kwargs.get('daily_pnl', 0)
        daily_pnl_pct = kwargs.get('daily_pnl_pct', 0)
        total_capital = kwargs.get('total_capital', 0)
        best_trade = kwargs.get('best_trade', 0)
        worst_trade = kwargs.get('worst_trade', 0)
        win_rate = (wins / trades_count * 100) if trades_count > 0 else 0
        
        color = self.COLORS['profit'] if daily_pnl >= 0 else self.COLORS['loss']
        emoji = "[UP]" if daily_pnl >= 0 else "[DOWN]"
        
        return DiscordEmbed(
            title=f"{emoji} PODSUMOWANIE DNIA: {date}",
            description=f"Dzisiejszy wynik tradingu",
            color=color,
            fields=[
                {"name": "[INFO] Trades", "value": f"`{trades_count}`", "inline": True},
                {"name": "[OK] Wins", "value": f"`{wins}`", "inline": True},
                {"name": "[ERROR] Losses", "value": f"`{losses}`", "inline": True},
                {"name": "[TARGET] Win Rate", "value": f"`{win_rate:.1f}%`", "inline": True},
                {"name": "[$] Daily PnL", "value": f"`{daily_pnl:+.2f} USDC`", "inline": True},
                {"name": "[UP] Daily PnL %", "value": f"`{daily_pnl_pct:+.2f}%`", "inline": True},
                {"name": "[WIN] Best Trade", "value": f"`{best_trade:+.2f} USDC`", "inline": True},
                {"name": "[BAD] Worst Trade", "value": f"`{worst_trade:+.2f} USDC`", "inline": True},
                {"name": "[CASE] Total Capital", "value": f"`{total_capital:.2f} USDC`", "inline": True}
            ],
            footer="Crypto Trading Bot - Daily Report",
            timestamp=datetime.utcnow().isoformat()
        )
    
    def _embed_pattern(self, **kwargs) -> DiscordEmbed:
        """Embed dla wykrytego patternu"""
        symbol = kwargs.get('symbol', 'UNKNOWN')
        pattern = kwargs.get('pattern', '')
        direction = kwargs.get('direction', '')
        confidence = kwargs.get('confidence', 0)
        
        return DiscordEmbed(
            title=f"[SCAN] PATTERN: {symbol}",
            description=f"Wykryto pattern: **{pattern}**",
            color=self.COLORS['info'],
            fields=[
                {"name": "Direction", "value": f"`{direction}`", "inline": True},
                {"name": "Confidence", "value": f"`{confidence:.0f}%`", "inline": True}
            ],
            footer="Crypto Trading Bot",
            timestamp=datetime.utcnow().isoformat()
        )
    
    def _embed_error(self, **kwargs) -> DiscordEmbed:
        """Embed dla błędu"""
        error = kwargs.get('error', 'Unknown error')
        module = kwargs.get('module', '')
        
        return DiscordEmbed(
            title="[ERROR] ERROR",
            description=f"**Module:** {module}\n\n```{error}```",
            color=self.COLORS['loss'],
            footer="Crypto Trading Bot - Error",
            timestamp=datetime.utcnow().isoformat()
        )
    
    def _embed_info(self, **kwargs) -> DiscordEmbed:
        """Embed dla ogólnej informacji"""
        title = kwargs.get('title', 'Info')
        message = kwargs.get('message', '')
        
        return DiscordEmbed(
            title=f"[INFO] {title}",
            description=message,
            color=self.COLORS['info'],
            footer="Crypto Trading Bot",
            timestamp=datetime.utcnow().isoformat()
        )
    
    # ============================================
    # CONVENIENCE METHODS
    # ============================================
    
    def notify_trade_entry(self, symbol: str, direction: str, entry_price: float,
                           stop_loss: float, take_profit: float, quantity: float,
                           value: float, risk: float, pattern: str = '', score: float = 0):
        """Powiadamia o nowym trade'ie"""
        self.send(
            AlertType.TRADE_ENTRY,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
            value=value,
            risk=risk,
            pattern=pattern,
            score=score
        )
    
    def notify_trade_exit(self, symbol: str, direction: str, entry_price: float,
                          exit_price: float, pnl: float, pnl_pct: float,
                          reason: str, duration: str = ''):
        """Powiadamia o zamknięciu trade'a"""
        # Wybierz odpowiedni typ na podstawie reason
        if 'TAKE_PROFIT' in reason.upper():
            alert_type = AlertType.TAKE_PROFIT
        elif 'STOP_LOSS' in reason.upper():
            alert_type = AlertType.STOP_LOSS
        elif 'TRAILING' in reason.upper():
            alert_type = AlertType.TRAILING_STOP
        else:
            alert_type = AlertType.TRADE_EXIT
        
        self.send(
            alert_type,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            reason=reason,
            duration=duration
        )
    
    def notify_drawdown_warning(self, current_drawdown: float, max_allowed: float, daily_pnl: float):
        """Powiadamia o wysokim drawdown"""
        self.send(
            AlertType.DRAWDOWN_WARNING,
            current_drawdown=current_drawdown,
            max_allowed=max_allowed,
            daily_pnl=daily_pnl
        )
    
    def notify_emergency_stop(self, reason: str, daily_pnl: float = 0, consecutive_losses: int = 0):
        """Powiadamia o emergency stop"""
        self.send(
            AlertType.EMERGENCY_STOP,
            reason=reason,
            daily_pnl=daily_pnl,
            consecutive_losses=consecutive_losses
        )
    
    def notify_daily_summary(self, stats: Dict):
        """Wysyła dzienne podsumowanie"""
        self.send(AlertType.DAILY_SUMMARY, **stats)
    
    def notify_error(self, error: str, module: str = ''):
        """Powiadamia o błędzie"""
        self.send(AlertType.ERROR, error=error, module=module)
    
    def notify_info(self, title: str, message: str):
        """Wysyła ogólną informację"""
        self.send(AlertType.INFO, title=title, message=message)
    
    def shutdown(self):
        """Zatrzymuje notyfikator"""
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
        logger.info("Discord Notifier zatrzymany")


if __name__ == "__main__":
    # Test modułu
    import yaml
    
    logging.basicConfig(level=logging.INFO)
    
    # Przykładowa konfiguracja
    config = {
        'discord': {
            'enabled': True,
            'webhook_url': os.environ.get('DISCORD_WEBHOOK_URL', ''),
            'bot_name': '[BOT] Test Bot',
            'mention_on_emergency': '@everyone'
        }
    }
    
    notifier = DiscordNotifier(config)
    
    # Test różnych powiadomień
    print("Sending test notifications...")
    
    # Test trade entry
    notifier.notify_trade_entry(
        symbol='BTCUSDC',
        direction='LONG',
        entry_price=65000,
        stop_loss=64000,
        take_profit=68000,
        quantity=0.015,
        value=975,
        risk=15,
        pattern='EMA Pullback',
        score=75
    )
    
    print("Test complete!")
    notifier.shutdown()
