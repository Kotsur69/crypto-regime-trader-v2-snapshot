#!/usr/bin/env python3
"""
dashboard.py - Flask Web Dashboard

Strony:
- / : Główny dashboard z live stats
- /trades : Historia trade'ów
- /logs : Live logs z ostatnich godzin
- /settings : Edycja konfiguracji (user-friendly)
- /api/* : API endpoints dla frontendu
"""

import logging
import os
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from functools import wraps
import yaml

try:
    from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logging.warning("Flask nie zainstalowany - dashboard niedostępny")

logger = logging.getLogger(__name__)

# ============================================
# FLASK APP
# ============================================

if FLASK_AVAILABLE:
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'crypto-bot-secret-key-change-me')
else:
    app = None


# ============================================
# DASHBOARD CLASS
# ============================================

class Dashboard:
    """
    Web dashboard dla bota tradingowego
    """
    
    def __init__(self, config: dict, bot=None):
        """
        Inicjalizacja dashboardu
        
        Args:
            config: Konfiguracja z sekcją 'dashboard'
            bot: Opcjonalna referencja do bota (dla live data)
        """
        self.config = config.get('dashboard', {})
        self.enabled = self.config.get('enabled', False) and FLASK_AVAILABLE
        self.port = self.config.get('port', 5000)
        self.host = self.config.get('host', '0.0.0.0')
        self.debug = self.config.get('debug', False)
        
        self.bot = bot
        self.server_thread = None
        self.running = False
        
        # Paths
        self.log_path = config.get('logging', {}).get('log_path', './logs/')
        self.data_path = './data/'
        self.config_path = 'config.yaml'
        
        # Live data cache
        self.live_data = {
            'portfolio': {},
            'positions': {},
            'daily_stats': {},
            'last_update': None
        }
        
        # Log buffer
        self.log_buffer = []
        self.max_log_entries = 500
        
        if self.enabled:
            self._setup_routes()
            self._create_templates()
            logger.info(f"[OK] Dashboard zainicjalizowany (port {self.port})")
        else:
            if not FLASK_AVAILABLE:
                logger.warning("[WARNING] Dashboard wyłączony - Flask nie zainstalowany")
            else:
                logger.info("[INFO] Dashboard wyłączony w konfiguracji")
    
    def _setup_routes(self):
        """Konfiguruje routes Flask"""
        if not app:
            return
        
        dashboard = self  # Reference for closures
        
        @app.route('/')
        def index():
            """Główny dashboard"""
            return render_template('index.html', 
                                   data=dashboard.get_dashboard_data())
        
        @app.route('/trades')
        def trades():
            """Historia trade'ów"""
            return render_template('trades.html',
                                   trades=dashboard.get_trades_history())
        
        @app.route('/logs')
        def logs():
            """Live logs"""
            return render_template('logs.html',
                                   logs=dashboard.get_recent_logs())
        
        @app.route('/settings')
        def settings():
            """Ustawienia"""
            return render_template('settings.html',
                                   config=dashboard.get_editable_config())
        
        @app.route('/levels')
        def levels():
            """Technical levels visualization"""
            return render_template('levels.html')
        
        # ============================================
        # API ENDPOINTS
        # ============================================
        
        @app.route('/api/status')
        def api_status():
            """API: Status bota"""
            return jsonify(dashboard.get_dashboard_data())
        
        @app.route('/api/portfolio')
        def api_portfolio():
            """API: Portfolio"""
            return jsonify(dashboard.get_portfolio_data())
        
        @app.route('/api/trades')
        def api_trades():
            """API: Trade history"""
            limit = request.args.get('limit', 50, type=int)
            return jsonify(dashboard.get_trades_history(limit=limit))
        
        @app.route('/api/logs')
        def api_logs():
            """API: Recent logs"""
            hours = request.args.get('hours', 2, type=int)
            return jsonify(dashboard.get_recent_logs(hours=hours))
        
        @app.route('/api/config', methods=['GET'])
        def api_config_get():
            """API: Get config"""
            return jsonify(dashboard.get_editable_config())
        
        @app.route('/api/config', methods=['POST'])
        def api_config_save():
            """API: Save config"""
            try:
                new_config = request.json
                dashboard.save_config(new_config)
                return jsonify({'success': True, 'message': 'Konfiguracja zapisana'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400
        
        @app.route('/api/levels/<symbol>')
        def api_levels(symbol):
            """API: Technical levels for symbol"""
            return jsonify(dashboard.get_technical_levels(symbol))
        
        @app.route('/api/regime/<symbol>')
        def api_regime(symbol):
            """API: Market regime for symbol"""
            return jsonify(dashboard.get_market_regime(symbol))
        
        @app.route('/api/vwap/<symbol>')
        def api_vwap(symbol):
            """API: VWAP data for symbol"""
            return jsonify(dashboard.get_vwap_data(symbol))
        
        @app.route('/api/sentiment')
        def api_sentiment():
            """API: LLM Sentiment data"""
            return jsonify(dashboard.get_sentiment_data())
        
        @app.route('/api/emergency_stop', methods=['POST'])
        def api_emergency_stop():
            """API: Toggle emergency stop"""
            action = request.json.get('action', 'toggle')
            return jsonify(dashboard.toggle_emergency_stop(action))
        
        # ============================================
        # PROFITABILITY PACK v3.0 ENDPOINTS
        # ============================================
        
        @app.route('/profitability')
        def profitability():
            """Profitability metrics page"""
            return render_template('profitability.html',
                                   data=dashboard.get_profitability_data())
        
        @app.route('/api/kelly')
        def api_kelly():
            """API: Kelly Criterion stats"""
            return jsonify(dashboard.get_kelly_stats())
        
        @app.route('/api/scale_out')
        def api_scale_out():
            """API: Scale out stats"""
            symbol = request.args.get('symbol', None)
            return jsonify(dashboard.get_scale_out_stats(symbol))
        
        @app.route('/api/fees')
        def api_fees():
            """API: Fee tracking stats"""
            return jsonify(dashboard.get_fee_stats())
        
        @app.route('/api/profitability')
        def api_profitability():
            """API: Combined profitability metrics"""
            return jsonify(dashboard.get_profitability_data())
        
        @app.route('/api/refresh')
        def api_refresh():
            """API: Force refresh data"""
            dashboard.refresh_data()
            return jsonify({'success': True})
    
    def _create_templates(self):
        """Tworzy szablony HTML jeśli nie istnieją"""
        templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        
        os.makedirs(templates_dir, exist_ok=True)
        os.makedirs(static_dir, exist_ok=True)
        
        # Base template
        base_html = '''<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Crypto Trading Bot{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #1a1a2e; color: #eee; }
        .navbar { background-color: #16213e !important; }
        .card { background-color: #0f3460; border: none; }
        .card-header { background-color: #1a1a2e; border-bottom: 1px solid #333; }
        .table { color: #eee; }
        .text-profit { color: #00ff88; }
        .text-loss { color: #ff4444; }
        .badge-long { background-color: #00ff88; color: #000; }
        .badge-short { background-color: #ff4444; }
        .log-entry { font-family: monospace; font-size: 0.85rem; padding: 2px 5px; }
        .log-info { color: #00bfff; }
        .log-warning { color: #ffa500; }
        .log-error { color: #ff4444; }
        .log-debug { color: #888; }
        .stat-card { text-align: center; padding: 20px; }
        .stat-value { font-size: 2rem; font-weight: bold; }
        .stat-label { color: #888; }
        .refresh-btn { position: fixed; bottom: 20px; right: 20px; }
    </style>
    {% block extra_css %}{% endblock %}
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/"><i class="fas fa-robot"></i> Crypto Bot</a>
            <div class="navbar-nav">
                <a class="nav-link" href="/"><i class="fas fa-tachometer-alt"></i> Dashboard</a>
                <a class="nav-link" href="/trades"><i class="fas fa-exchange-alt"></i> Trades</a>
                <a class="nav-link" href="/profitability"><i class="fas fa-chart-pie"></i> Profitability</a>
                <a class="nav-link" href="/logs"><i class="fas fa-list"></i> Logs</a>
                <a class="nav-link" href="/levels"><i class="fas fa-chart-line"></i> Levels</a>
                <a class="nav-link" href="/settings"><i class="fas fa-cog"></i> Settings</a>
            </div>
            <span class="navbar-text">
                <span id="status-indicator" class="badge bg-success">Running</span>
            </span>
        </div>
    </nav>
    
    <div class="container-fluid mt-4">
        {% block content %}{% endblock %}
    </div>
    
    <button class="btn btn-primary refresh-btn" onclick="location.reload()">
        <i class="fas fa-sync-alt"></i>
    </button>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // Auto refresh every 30 seconds
        setTimeout(() => location.reload(), 30000);
    </script>
    {% block extra_js %}{% endblock %}
</body>
</html>
'''
        
        # Index template
        index_html = '''{% extends "base.html" %}
{% block title %}Dashboard - Crypto Bot{% endblock %}
{% block content %}
<div class="row mb-4">
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="stat-value {% if data.pnl_total >= 0 %}text-profit{% else %}text-loss{% endif %}">
                {{ "%.2f"|format(data.pnl_total) }} USDC
            </div>
            <div class="stat-label">Total PnL</div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="stat-value">{{ "%.2f"|format(data.total_capital) }}</div>
            <div class="stat-label">Total Capital (USDC)</div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="stat-value">{{ data.open_positions }}</div>
            <div class="stat-label">Open Positions</div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="stat-value">{{ "%.1f"|format(data.win_rate) }}%</div>
            <div class="stat-label">Win Rate</div>
        </div>
    </div>
</div>

<div class="row mb-4">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-wallet"></i> Portfolio</div>
            <div class="card-body">
                <table class="table table-sm">
                    <thead><tr><th>Pair</th><th>Capital</th><th>PnL</th></tr></thead>
                    <tbody>
                    {% for pair, capital in data.capital_per_pair.items() %}
                    <tr>
                        <td>{{ pair }}</td>
                        <td>{{ "%.2f"|format(capital) }} USDC</td>
                        <td class="{% if capital >= 10000 %}text-profit{% else %}text-loss{% endif %}">
                            {{ "%.2f"|format(capital - 10000) }}
                        </td>
                    </tr>
                    {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-chart-line"></i> Open Positions</div>
            <div class="card-body">
                {% if data.positions %}
                <table class="table table-sm">
                    <thead><tr><th>Symbol</th><th>Side</th><th>Entry</th><th>Unrealized PnL</th></tr></thead>
                    <tbody>
                    {% for symbol, pos in data.positions.items() %}
                    <tr>
                        <td>{{ symbol }}</td>
                        <td><span class="badge {% if pos.side == 'BUY' %}badge-long{% else %}badge-short{% endif %}">{{ pos.side }}</span></td>
                        <td>{{ "%.2f"|format(pos.entry_price) }}</td>
                        <td class="{% if pos.unrealized_pnl >= 0 %}text-profit{% else %}text-loss{% endif %}">
                            {{ "%.2f"|format(pos.unrealized_pnl|default(0)) }}
                        </td>
                    </tr>
                    {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p class="text-muted">No open positions</p>
                {% endif %}
            </div>
        </div>
    </div>
</div>

<div class="row">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-calendar-day"></i> Today's Stats</div>
            <div class="card-body">
                <p><strong>Trades:</strong> {{ data.daily_stats.trades_count }}</p>
                <p><strong>Wins:</strong> {{ data.daily_stats.wins }} | <strong>Losses:</strong> {{ data.daily_stats.losses }}</p>
                <p><strong>PnL:</strong> <span class="{% if data.daily_stats.pnl >= 0 %}text-profit{% else %}text-loss{% endif %}">{{ "%.2f"|format(data.daily_stats.pnl) }} USDC</span></p>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-exclamation-triangle"></i> Alerts</div>
            <div class="card-body">
                {% if data.emergency_stop %}
                <div class="alert alert-danger"><i class="fas fa-stop-circle"></i> EMERGENCY STOP ACTIVE</div>
                {% endif %}
                {% if data.daily_stats.consecutive_losses >= 3 %}
                <div class="alert alert-warning"><i class="fas fa-exclamation"></i> {{ data.daily_stats.consecutive_losses }} consecutive losses</div>
                {% endif %}
                {% if not data.emergency_stop and data.daily_stats.consecutive_losses < 3 %}
                <p class="text-success"><i class="fas fa-check"></i> All systems normal</p>
                {% endif %}
            </div>
        </div>
    </div>
</div>
{% endblock %}
'''
        
        # Trades template
        trades_html = '''{% extends "base.html" %}
{% block title %}Trade History - Crypto Bot{% endblock %}
{% block content %}
<div class="card">
    <div class="card-header"><i class="fas fa-history"></i> Trade History</div>
    <div class="card-body">
        <table class="table table-striped">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Direction</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>PnL</th>
                    <th>Reason</th>
                    <th>Pattern</th>
                </tr>
            </thead>
            <tbody>
            {% for trade in trades %}
            <tr>
                <td>{{ trade.exit_time }}</td>
                <td>{{ trade.symbol }}</td>
                <td><span class="badge {% if trade.direction == 'LONG' %}badge-long{% else %}badge-short{% endif %}">{{ trade.direction }}</span></td>
                <td>{{ "%.4f"|format(trade.entry_price) }}</td>
                <td>{{ "%.4f"|format(trade.exit_price) }}</td>
                <td class="{% if trade.pnl >= 0 %}text-profit{% else %}text-loss{% endif %}">{{ "%.2f"|format(trade.pnl) }}</td>
                <td>{{ trade.exit_reason }}</td>
                <td>{{ trade.pattern_type }}</td>
            </tr>
            {% else %}
            <tr><td colspan="8" class="text-center text-muted">No trades yet</td></tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
'''
        
        # Logs template
        logs_html = '''{% extends "base.html" %}
{% block title %}Logs - Crypto Bot{% endblock %}
{% block content %}
<div class="card">
    <div class="card-header"><i class="fas fa-terminal"></i> Recent Logs (last 2 hours)</div>
    <div class="card-body" style="max-height: 70vh; overflow-y: auto;">
        {% for log in logs %}
        <div class="log-entry log-{{ log.level|lower }}">
            <span class="text-muted">{{ log.timestamp }}</span> 
            <span class="badge bg-{{ 'info' if log.level == 'INFO' else ('warning' if log.level == 'WARNING' else 'danger') }}">{{ log.level }}</span>
            {{ log.message }}
        </div>
        {% else %}
        <p class="text-muted">No logs available</p>
        {% endfor %}
    </div>
</div>
{% endblock %}
'''
        
        # Settings template
        settings_html = '''{% extends "base.html" %}
{% block title %}Settings - Crypto Bot{% endblock %}
{% block content %}
<div class="card">
    <div class="card-header"><i class="fas fa-cog"></i> Configuration</div>
    <div class="card-body">
        <form id="configForm">
            <h5>Risk Management</h5>
            <div class="row mb-3">
                <div class="col-md-4">
                    <label class="form-label">Min Risk:Reward</label>
                    <input type="number" class="form-control" name="risk.min_risk_reward" value="{{ config.risk.min_risk_reward }}" step="0.1">
                </div>
                <div class="col-md-4">
                    <label class="form-label">Max Risk per Trade (%)</label>
                    <input type="number" class="form-control" name="risk.max_risk_per_trade_pct" value="{{ config.risk.max_risk_per_trade_pct }}" step="0.5">
                </div>
                <div class="col-md-4">
                    <label class="form-label">Max Daily Drawdown (%)</label>
                    <input type="number" class="form-control" name="risk.max_daily_drawdown_pct" value="{{ config.risk.max_daily_drawdown_pct }}" step="1">
                </div>
            </div>
            
            <h5>Trading</h5>
            <div class="row mb-3">
                <div class="col-md-4">
                    <label class="form-label">Primary Timeframe</label>
                    <select class="form-control" name="trading.primary_timeframe">
                        <option {% if config.trading.primary_timeframe == '5m' %}selected{% endif %}>5m</option>
                        <option {% if config.trading.primary_timeframe == '15m' %}selected{% endif %}>15m</option>
                        <option {% if config.trading.primary_timeframe == '1h' %}selected{% endif %}>1h</option>
                    </select>
                </div>
                <div class="col-md-4">
                    <label class="form-label">Max Concurrent Positions</label>
                    <input type="number" class="form-control" name="trading.max_concurrent_positions" value="{{ config.trading.max_concurrent_positions }}">
                </div>
            </div>
            
            <h5>Decision Engine</h5>
            <div class="row mb-3">
                <div class="col-md-4">
                    <label class="form-label">Min Trade Score</label>
                    <input type="number" class="form-control" name="decision.min_trade_score" value="{{ config.decision.min_trade_score }}" min="0" max="100">
                </div>
            </div>
            
            <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Configuration</button>
            <p class="text-muted mt-2"><small>[WARNING] Changes require bot restart to take effect</small></p>
        </form>
    </div>
</div>

<div class="card mt-4">
    <div class="card-header"><i class="fas fa-power-off"></i> Bot Control</div>
    <div class="card-body">
        <button class="btn btn-danger" onclick="toggleEmergencyStop('activate')">
            <i class="fas fa-stop"></i> Emergency Stop
        </button>
        <button class="btn btn-success" onclick="toggleEmergencyStop('deactivate')">
            <i class="fas fa-play"></i> Resume Trading
        </button>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
    document.getElementById('configForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const config = {};
        formData.forEach((value, key) => {
            const keys = key.split('.');
            let obj = config;
            for (let i = 0; i < keys.length - 1; i++) {
                if (!obj[keys[i]]) obj[keys[i]] = {};
                obj = obj[keys[i]];
            }
            obj[keys[keys.length - 1]] = isNaN(value) ? value : parseFloat(value);
        });
        
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });
        const result = await response.json();
        alert(result.message || result.error);
    });
    
    async function toggleEmergencyStop(action) {
        const response = await fetch('/api/emergency_stop', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action})
        });
        const result = await response.json();
        alert(result.message);
        location.reload();
    }
</script>
{% endblock %}
'''
        
        # Levels template
        levels_html = '''{% extends "base.html" %}
{% block title %}Technical Levels - Crypto Bot{% endblock %}
{% block content %}
<div class="row">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-chart-bar"></i> Select Symbol</div>
            <div class="card-body">
                <select id="symbolSelect" class="form-control" onchange="loadLevels()">
                    <option value="BTCUSDC">BTC/USDC</option>
                    <option value="ETHUSDC">ETH/USDC</option>
                    <option value="XRPUSDC">XRP/USDC</option>
                    <option value="DOGEUSDC">DOGE/USDC</option>
                </select>
            </div>
        </div>
    </div>
</div>

<div class="row mt-4">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-ruler-vertical"></i> Fibonacci Levels</div>
            <div class="card-body" id="fibLevels">Loading...</div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-shield-alt"></i> Support/Resistance</div>
            <div class="card-body" id="srLevels">Loading...</div>
        </div>
    </div>
</div>

<div class="row mt-4">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-compass"></i> Pivot Points</div>
            <div class="card-body" id="pivotLevels">Loading...</div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-thermometer-half"></i> Market Regime</div>
            <div class="card-body" id="marketRegime">Loading...</div>
        </div>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
    async function loadLevels() {
        const symbol = document.getElementById('symbolSelect').value;
        
        // Load technical levels
        try {
            const levelsRes = await fetch(`/api/levels/${symbol}`);
            const levels = await levelsRes.json();
            
            // Fibonacci
            let fibHtml = '';
            if (levels.fibonacci) {
                fibHtml = '<table class="table table-sm"><tbody>';
                for (const [name, price] of Object.entries(levels.fibonacci.levels)) {
                    fibHtml += `<tr><td>Fib ${name}%</td><td>${price.toFixed(2)}</td></tr>`;
                }
                fibHtml += '</tbody></table>';
            } else {
                fibHtml = '<p class="text-muted">Not available</p>';
            }
            document.getElementById('fibLevels').innerHTML = fibHtml;
            
            // S/R
            let srHtml = '<table class="table table-sm"><tbody>';
            for (const level of levels.support_resistance || []) {
                const color = level.type === 'support' ? 'text-profit' : 'text-loss';
                srHtml += `<tr><td>${level.name}</td><td class="${color}">${level.price.toFixed(2)}</td><td>Strength: ${level.strength}</td></tr>`;
            }
            srHtml += '</tbody></table>';
            document.getElementById('srLevels').innerHTML = srHtml || '<p class="text-muted">No levels</p>';
            
            // Pivots
            let pivotHtml = '<table class="table table-sm"><tbody>';
            for (const [name, pivot] of Object.entries(levels.pivots || {})) {
                const color = name.startsWith('R') ? 'text-loss' : (name.startsWith('S') ? 'text-profit' : '');
                pivotHtml += `<tr><td>${name}</td><td class="${color}">${pivot.price.toFixed(2)}</td></tr>`;
            }
            pivotHtml += '</tbody></table>';
            document.getElementById('pivotLevels').innerHTML = pivotHtml;
            
        } catch (e) {
            console.error('Error loading levels:', e);
        }
        
        // Load market regime
        try {
            const regimeRes = await fetch(`/api/regime/${symbol}`);
            const regime = await regimeRes.json();
            
            let regimeHtml = `
                <h4>${regime.regime || 'Unknown'}</h4>
                <p><strong>Confidence:</strong> ${(regime.confidence || 0).toFixed(1)}%</p>
                <p><strong>ADX:</strong> ${(regime.adx || 0).toFixed(2)} (${regime.adx_trend || 'n/a'})</p>
                <p><strong>Trend Strength:</strong> ${(regime.trend_strength || 0).toFixed(1)}</p>
                <hr>
                <h6>Recommendations:</h6>
                <ul>`;
            for (const rec of regime.recommendations || []) {
                regimeHtml += `<li>${rec}</li>`;
            }
            regimeHtml += '</ul>';
            document.getElementById('marketRegime').innerHTML = regimeHtml;
            
        } catch (e) {
            document.getElementById('marketRegime').innerHTML = '<p class="text-muted">Not available</p>';
        }
    }
    
    // Load on page load
    loadLevels();
</script>
{% endblock %}
'''
        
        # Write templates
        templates = {
            'base.html': base_html,
            'index.html': index_html,
            'trades.html': trades_html,
            'logs.html': logs_html,
            'settings.html': settings_html,
            'levels.html': levels_html
        }
        
        for name, content in templates.items():
            path = os.path.join(templates_dir, name)
            if not os.path.exists(path):
                with open(path, 'w') as f:
                    f.write(content)
    
    # ============================================
    # DATA METHODS
    # ============================================
    
    def get_dashboard_data(self) -> Dict:
        """Zwraca dane do głównego dashboardu"""
        data = {
            'total_capital': 0,
            'pnl_total': 0,
            'pnl_pct': 0,
            'open_positions': 0,
            'positions': {},
            'capital_per_pair': {},
            'daily_stats': {
                'trades_count': 0,
                'wins': 0,
                'losses': 0,
                'pnl': 0,
                'consecutive_losses': 0
            },
            'emergency_stop': False,
            'win_rate': 0,
            'last_update': datetime.now().isoformat()
        }
        
        # Load from risk_state.json
        try:
            state_file = os.path.join(self.data_path, 'risk_state.json')
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    state = json.load(f)
                
                capital = state.get('capital', {})
                data['capital_per_pair'] = capital
                data['total_capital'] = sum(capital.values())
                data['pnl_total'] = data['total_capital'] - (10000 * len(capital))
                data['pnl_pct'] = (data['pnl_total'] / (10000 * len(capital)) * 100) if capital else 0
                
                data['positions'] = state.get('positions', {})
                data['open_positions'] = len(data['positions'])
                data['emergency_stop'] = state.get('emergency_stop_active', False)
                
                daily = state.get('daily_stats', {})
                data['daily_stats'] = {
                    'trades_count': daily.get('trades_count', 0),
                    'wins': daily.get('wins', 0),
                    'losses': daily.get('losses', 0),
                    'pnl': daily.get('pnl', 0),
                    'consecutive_losses': daily.get('consecutive_losses', 0)
                }
                
                total_trades = data['daily_stats']['wins'] + data['daily_stats']['losses']
                data['win_rate'] = (data['daily_stats']['wins'] / total_trades * 100) if total_trades > 0 else 0
                
        except Exception as e:
            logger.error(f"Error loading dashboard data: {e}")
        
        return data
    
    def get_portfolio_data(self) -> Dict:
        """Zwraca dane portfolio"""
        return self.get_dashboard_data()
    
    def get_trades_history(self, limit: int = 50) -> List[Dict]:
        """Zwraca historię trade'ów"""
        trades = []
        
        try:
            trades_file = os.path.join(self.data_path, 'learning', 'trade_history.json')
            if os.path.exists(trades_file):
                with open(trades_file, 'r') as f:
                    all_trades = json.load(f)
                trades = all_trades[-limit:]
                trades.reverse()  # Newest first
        except Exception as e:
            logger.error(f"Error loading trades: {e}")
        
        return trades
    
    def get_recent_logs(self, hours: int = 2) -> List[Dict]:
        """Zwraca logi z ostatnich godzin"""
        logs = []
        
        try:
            today = datetime.now().strftime('%Y%m%d')
            log_file = os.path.join(self.log_path, f'trading_bot_{today}.log')
            
            if os.path.exists(log_file):
                cutoff_time = datetime.now() - timedelta(hours=hours)
                
                with open(log_file, 'r') as f:
                    for line in f:
                        try:
                            # Parse log line
                            parts = line.split(' | ')
                            if len(parts) >= 3:
                                timestamp_str = parts[0].strip()
                                level = parts[1].strip()
                                message = ' | '.join(parts[2:]).strip()
                                
                                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                                if timestamp >= cutoff_time:
                                    logs.append({
                                        'timestamp': timestamp_str,
                                        'level': level,
                                        'message': message[:200]  # Truncate
                                    })
                        except:
                            continue
                
                logs = logs[-500:]  # Last 500 entries
                logs.reverse()  # Newest first
                
        except Exception as e:
            logger.error(f"Error loading logs: {e}")
        
        return logs
    
    def get_editable_config(self) -> Dict:
        """Zwraca konfigurację do edycji"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}
    
    def save_config(self, updates: Dict):
        """Zapisuje zmiany w konfiguracji"""
        try:
            # Load current config
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Deep merge updates
            def deep_merge(base, updates):
                for key, value in updates.items():
                    if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                        deep_merge(base[key], value)
                    else:
                        base[key] = value
            
            deep_merge(config, updates)
            
            # Save
            with open(self.config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
            logger.info("Configuration saved")
            
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            raise
    
    def get_technical_levels(self, symbol: str) -> Dict:
        """Zwraca poziomy techniczne dla symbolu"""
        try:
            # Try to get from bot's technical_levels module
            if self.bot and hasattr(self.bot, 'technical_levels'):
                return self.bot.technical_levels.get_visualization_data(symbol)
            
            # Load from cache file
            cache_file = os.path.join(self.data_path, f'levels_{symbol}.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error getting technical levels: {e}")
        
        return {}
    
    def get_market_regime(self, symbol: str) -> Dict:
        """Zwraca regime rynkowy dla symbolu"""
        try:
            if self.bot and hasattr(self.bot, 'market_regime_detector'):
                analysis = self.bot.market_regime_detector.get_cached_analysis(symbol)
                if analysis:
                    return analysis.to_dict()
            
            cache_file = os.path.join(self.data_path, f'regime_{symbol}.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error getting market regime: {e}")
        
        return {'regime': 'unknown', 'confidence': 0, 'recommendations': []}
    
    def toggle_emergency_stop(self, action: str) -> Dict:
        """Włącza/wyłącza emergency stop"""
        try:
            state_file = os.path.join(self.data_path, 'risk_state.json')
            
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    state = json.load(f)
                
                if action == 'activate':
                    state['emergency_stop_active'] = True
                    message = 'Emergency stop activated'
                elif action == 'deactivate':
                    state['emergency_stop_active'] = False
                    message = 'Emergency stop deactivated - trading resumed'
                else:
                    state['emergency_stop_active'] = not state.get('emergency_stop_active', False)
                    message = f"Emergency stop {'activated' if state['emergency_stop_active'] else 'deactivated'}"
                
                with open(state_file, 'w') as f:
                    json.dump(state, f, indent=2)
                
                return {'success': True, 'message': message}
            
        except Exception as e:
            logger.error(f"Error toggling emergency stop: {e}")
            return {'success': False, 'error': str(e)}
        
        return {'success': False, 'error': 'State file not found'}
    
    def get_vwap_data(self, symbol: str) -> Dict:
        """Zwraca dane VWAP dla symbolu"""
        try:
            # Try to get from bot's indicators module
            if self.bot and hasattr(self.bot, 'indicators'):
                from indicators import TechnicalIndicators
                
                # Get latest data with VWAP
                if hasattr(self.bot, 'data_fetcher'):
                    df = self.bot.data_fetcher.get_klines(symbol, '15m', limit=100)
                    if not df.empty:
                        df = self.bot.indicators.calculate_all(df)
                        df = self.bot.indicators.add_vwap(df)
                        
                        summary = self.bot.indicators.get_vwap_summary(df)
                        
                        # Add recent VWAP values for charting
                        vwap_data = {}
                        for col in df.columns:
                            if col.startswith('vwap_'):
                                session = col.replace('vwap_', '')
                                values = df[col].dropna().tail(50).tolist()
                                timestamps = df.index[-len(values):].strftime('%Y-%m-%d %H:%M').tolist()
                                vwap_data[session] = {
                                    'values': values,
                                    'timestamps': timestamps,
                                    'current': values[-1] if values else None
                                }
                        
                        return {
                            'symbol': symbol,
                            'summary': summary,
                            'sessions': vwap_data,
                            'timestamp': datetime.now().isoformat()
                        }
            
            # Fallback: load from cache
            cache_file = os.path.join(self.data_path, f'vwap_{symbol}.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    return json.load(f)
                    
        except Exception as e:
            logger.error(f"Error getting VWAP data: {e}")
        
        return {
            'symbol': symbol,
            'summary': {},
            'sessions': {},
            'error': 'VWAP data not available'
        }
    
    def get_sentiment_data(self) -> Dict:
        """Zwraca dane sentymentu z LLM"""
        try:
            # Try to get from decision engine
            if self.bot and hasattr(self.bot, 'decision_engine'):
                engine = self.bot.decision_engine
                
                result = {
                    'enabled': engine.llm_enabled,
                    'timestamp': datetime.now().isoformat()
                }
                
                if engine.llm_enabled:
                    cached = engine._cached_sentiment
                    if cached:
                        result['sentiment'] = {
                            'score': cached.score,
                            'confidence': cached.confidence,
                            'reasoning': cached.reasoning,
                            'key_factors': cached.key_factors,
                            'is_emergency': cached.is_emergency,
                            'analyzed_at': cached.timestamp.isoformat()
                        }
                    
                    # Get last briefing if available
                    analyzer = engine._get_llm_analyzer()
                    if analyzer:
                        briefing = analyzer.get_cached_briefing()
                        if briefing:
                            result['briefing'] = {
                                'recommendation': briefing.recommendation,
                                'overall_sentiment': briefing.overall_sentiment,
                                'market_summary': briefing.market_summary,
                                'key_events': briefing.key_events[:5],
                                'risks': briefing.risks[:5],
                                'date': briefing.date.isoformat()
                            }
                
                return result
            
            # Fallback: load from cache
            cache_file = os.path.join(self.data_path, 'sentiment_cache.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    return json.load(f)
                    
        except Exception as e:
            logger.error(f"Error getting sentiment data: {e}")
        
        return {
            'enabled': False,
            'error': 'Sentiment data not available'
        }
    
    # ============================================
    # PROFITABILITY PACK v3.0 METHODS
    # ============================================
    
    def get_kelly_stats(self) -> Dict:
        """Zwraca statystyki Kelly Criterion"""
        try:
            if self.bot and hasattr(self.bot, 'risk_manager'):
                rm = self.bot.risk_manager
                if hasattr(rm, 'get_kelly_summary'):
                    return rm.get_kelly_summary()
            
            # Fallback: load from file
            kelly_file = os.path.join(self.data_path, 'kelly_stats.json')
            if os.path.exists(kelly_file):
                with open(kelly_file, 'r') as f:
                    return json.load(f)
                    
        except Exception as e:
            logger.error(f"Error getting Kelly stats: {e}")
        
        return {
            'enabled': False,
            'error': 'Kelly stats not available'
        }
    
    def get_scale_out_stats(self, symbol: str = None) -> Dict:
        """Zwraca statystyki scale out"""
        try:
            if self.bot and hasattr(self.bot, 'execution'):
                exec_layer = self.bot.execution
                if hasattr(exec_layer, 'get_scale_out_stats'):
                    return exec_layer.get_scale_out_stats(symbol)
            
            # Fallback: load from file
            scale_out_file = os.path.join(self.data_path, 'execution/scale_out_state.json')
            if os.path.exists(scale_out_file):
                with open(scale_out_file, 'r') as f:
                    data = json.load(f)
                    if symbol:
                        return data.get(symbol, {})
                    return data
                    
        except Exception as e:
            logger.error(f"Error getting scale out stats: {e}")
        
        return {
            'error': 'Scale out stats not available'
        }
    
    def get_fee_stats(self) -> Dict:
        """Zwraca statystyki fee tracking"""
        try:
            if self.bot and hasattr(self.bot, 'execution'):
                exec_layer = self.bot.execution
                if hasattr(exec_layer, 'get_fee_stats'):
                    stats = exec_layer.get_fee_stats()
                    if stats:
                        return stats
            
            # Fallback: load from file
            fee_file = os.path.join(self.data_path, 'execution/fee_stats.json')
            if os.path.exists(fee_file):
                with open(fee_file, 'r') as f:
                    data = json.load(f)
                    return data.get('fee_stats', {})
                    
        except Exception as e:
            logger.error(f"Error getting fee stats: {e}")
        
        return {
            'total_maker_orders': 0,
            'total_taker_orders': 0,
            'total_fees_paid': 0,
            'total_rebates_earned': 0,
            'net_fees': 0,
            'maker_ratio': 0
        }
    
    def get_profitability_data(self) -> Dict:
        """Zwraca połączone dane profitability"""
        return {
            'kelly': self.get_kelly_stats(),
            'scale_out': self.get_scale_out_stats(),
            'fees': self.get_fee_stats(),
            'timestamp': datetime.now().isoformat()
        }
    
    def refresh_data(self):
        """Odświeża dane z bota"""
        if self.bot and hasattr(self.bot, 'risk_manager'):
            self.live_data['portfolio'] = self.bot.risk_manager.get_portfolio_summary()
            self.live_data['last_update'] = datetime.now().isoformat()
    
    def add_log(self, level: str, message: str):
        """Dodaje log do bufora (dla real-time logs)"""
        self.log_buffer.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': level,
            'message': message
        })
        
        if len(self.log_buffer) > self.max_log_entries:
            self.log_buffer.pop(0)
    
    # ============================================
    # SERVER METHODS
    # ============================================
    
    def start(self):
        """Uruchamia dashboard w osobnym wątku"""
        if not self.enabled:
            return
        
        if self.running:
            logger.warning("Dashboard already running")
            return
        
        self.running = True
        self.server_thread = threading.Thread(
            target=self._run_server,
            daemon=True
        )
        self.server_thread.start()
        logger.info(f"[WEB] Dashboard started at http://{self.host}:{self.port}")
    
    def _run_server(self):
        """Uruchamia serwer Flask"""
        try:
            # Disable Flask logging in production
            import logging as log
            log.getLogger('werkzeug').setLevel(log.WARNING)
            
            app.run(
                host=self.host,
                port=self.port,
                debug=self.debug,
                use_reloader=False,
                threaded=True
            )
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            self.running = False
    
    def stop(self):
        """Zatrzymuje dashboard"""
        self.running = False
        logger.info("Dashboard stopped")


if __name__ == "__main__":
    # Test dashboardu
    import yaml
    
    logging.basicConfig(level=logging.INFO)
    
    config = {
        'dashboard': {
            'enabled': True,
            'port': 5000,
            'host': '0.0.0.0',
            'debug': True
        },
        'logging': {
            'log_path': './logs/'
        }
    }
    
    dashboard = Dashboard(config)
    dashboard.start()
    
    print("Dashboard running at http://localhost:5000")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        dashboard.stop()
