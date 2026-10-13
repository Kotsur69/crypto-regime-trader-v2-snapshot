# 🤖 LLM Integration Setup Guide

Przewodnik konfiguracji integracji LLM (Large Language Model) z Trading Botem dla analizy sentymentu newsów.

## 📋 Spis treści

1. [Wymagania sprzętowe](#wymagania-sprzętowe)
2. [Instalacja LM Studio](#instalacja-lm-studio)
3. [Pobieranie modelu](#pobieranie-modelu)
4. [Konfiguracja serwera](#konfiguracja-serwera)
5. [Konfiguracja bota](#konfiguracja-bota)
6. [Testowanie](#testowanie)
7. [Alternatywne providery](#alternatywne-providery)
8. [Troubleshooting](#troubleshooting)

---

## 💻 Wymagania sprzętowe

### Minimalne wymagania dla Llama 3 8B:

| Komponent | Minimum | Rekomendowane |
|-----------|---------|---------------|
| GPU VRAM | 8 GB | 12+ GB |
| RAM | 16 GB | 32 GB |
| Dysk | 20 GB wolnego | 50 GB SSD |

### Twój sprzęt:
- **GPU**: AMD Radeon RX 9070 XT (16GB VRAM) ✅
- **RAM**: 32GB ✅

**Wniosek**: Twój sprzęt jest w pełni wystarczający dla Llama 3 8B!

---

## 📥 Instalacja LM Studio

### Windows / macOS / Linux:

1. **Pobierz LM Studio**:
   - Odwiedź: https://lmstudio.ai/
   - Pobierz wersję dla swojego systemu

2. **Zainstaluj**:
   - Windows: Uruchom instalator `.exe`
   - macOS: Przeciągnij do Applications
   - Linux: Rozpakuj AppImage i uruchom

3. **Uruchom LM Studio**:
   - Przy pierwszym uruchomieniu przejdź przez konfigurację
   - Wybierz folder na modele (potrzeba ~20GB na Llama 3 8B)

---

## 📦 Pobieranie modelu

### Rekomendowany: Llama 3 8B Instruct

1. **W LM Studio**:
   - Przejdź do zakładki "Search"
   - Wyszukaj: `llama-3-8b-instruct`

2. **Wybierz wersję** (rekomendowane dla 16GB VRAM):
   ```
   lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF
   - Wybierz: Q5_K_M (najlepsza jakość dla twojego GPU)
   - Lub: Q4_K_M (szybsza, nieco mniejsza jakość)
   ```

3. **Pobierz model**:
   - Kliknij "Download"
   - Poczekaj na zakończenie (~5-10 GB do pobrania)

### Alternatywne modele:

| Model | VRAM | Jakość | Szybkość |
|-------|------|--------|----------|
| Llama 3 8B Q5_K_M | ~8 GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Llama 3 8B Q4_K_M | ~6 GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Mistral 7B Q5_K_M | ~6 GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Phi-3 Mini 3.8B | ~3 GB | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## ⚙️ Konfiguracja serwera

### Uruchomienie serwera lokalnego:

1. **W LM Studio**:
   - Przejdź do zakładki "Local Server"
   - Załaduj pobrany model
   - Kliknij "Start Server"

2. **Ustawienia serwera**:
   ```
   Host: 0.0.0.0 (lub localhost)
   Port: 1234
   
   Context Length: 4096 (wystarczające dla newsów)
   GPU Layers: Auto (lub max dla najszybszej pracy)
   ```

3. **Sprawdź działanie**:
   ```bash
   # Test połączenia
   curl http://localhost:1234/v1/models
   ```
   
   Powinno zwrócić listę dostępnych modeli.

### Auto-start serwera:

Aby serwer uruchamiał się automatycznie:
- LM Studio: Settings → Enable "Start server on launch"

---

## 🔧 Konfiguracja bota

### 1. Edytuj `config.yaml`:

```yaml
llm:
  enabled: true
  provider: "lm_studio"
  base_url: "http://localhost:1234/v1"
  model: "llama3:8b"
  timeout: 30
  temperature: 0.1
  sentiment_weight: 0.15  # 15% wpływu na decyzję
  veto_threshold: -0.7    # Blokuj trade przy silnym bearish

news:
  enabled: true
  sources:
    - coindesk
    - cointelegraph
  update_interval: 300  # 5 minut
  cache_hours: 24
```

### 2. Zainstaluj zależności:

```bash
pip install openai feedparser
```

### 3. Sprawdź instalację:

```bash
python test_llm.py
```

---

## 🧪 Testowanie

### Test podstawowy:

```bash
cd /home/ubuntu/crypto_trading_bot
python test_llm.py
```

Oczekiwany output:
```
📰 TEST: News Fetcher
✅ Znaleziono X newsów

🤖 TEST: LLM Connection
✅ LLM jest dostępny!

📊 TEST: Sentiment Analysis
✅ Wynik analizy:
   Score: 0.35 (-1.0 do +1.0)
   Confidence: 0.85
```

### Test manual z LLM:

```python
from llm_sentiment import LLMSentimentAnalyzer
import yaml

with open('config.yaml') as f:
    config = yaml.safe_load(f)

analyzer = LLMSentimentAnalyzer(config)

# Test
if analyzer.is_available():
    print("✅ LLM działa!")
else:
    print("❌ LLM niedostępny")
```

---

## 🔄 Alternatywne providery

### Ollama (alternatywa dla LM Studio):

1. **Instalacja**:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```

2. **Pobierz model**:
   ```bash
   ollama pull llama3:8b
   ```

3. **Uruchom serwer**:
   ```bash
   ollama serve
   ```

4. **Konfiguracja**:
   ```yaml
   llm:
     provider: "ollama"
     base_url: "http://localhost:11434/v1"
     model: "llama3:8b"
   ```

### OpenAI API (płatne, najszybsze):

```yaml
llm:
  provider: "openai"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o-mini"  # Najtańszy
  api_key: "sk-..."     # Twój klucz API
```

---

## ⚠️ Troubleshooting

### Problem: "LLM niedostępny"

**Rozwiązania**:
1. Sprawdź czy LM Studio jest uruchomione
2. Sprawdź czy model jest załadowany
3. Sprawdź port: `curl http://localhost:1234/v1/models`

### Problem: "Timeout przy analizie"

**Rozwiązania**:
1. Zwiększ timeout w config.yaml: `timeout: 60`
2. Użyj mniejszego modelu (Q4 zamiast Q5)
3. Zmniejsz liczbę newsów do analizy

### Problem: "Brak pamięci GPU"

**Rozwiązania**:
1. Zamknij inne aplikacje używające GPU
2. Użyj mniejszej kwantyzacji (Q4_K_S)
3. Ogranicz kontekst: `max_tokens: 300`

### Problem: "Dziwne odpowiedzi LLM"

**Rozwiązania**:
1. Zmniejsz temperature: `temperature: 0.05`
2. Użyj modelu "instruct" zamiast base
3. Sprawdź czy prompt jest poprawny

---

## 📊 Monitoring wydajności

### Sprawdź wykorzystanie GPU:

```bash
# AMD
rocm-smi

# NVIDIA
nvidia-smi
```

### Logi LLM:

```python
import logging
logging.getLogger('llm_sentiment').setLevel(logging.DEBUG)
```

---

## 🎯 Przykłady użycia

### Analiza sentymentu:

```python
from news_fetcher import NewsFetcher
from llm_sentiment import LLMSentimentAnalyzer

# Pobierz newsy
fetcher = NewsFetcher(config)
news = fetcher.get_latest_news(hours=12)

# Analizuj
analyzer = LLMSentimentAnalyzer(config)
sentiment = analyzer.analyze_news(news)

print(f"Sentiment: {sentiment.score}")  # -1 do +1
print(f"Emergency: {sentiment.is_emergency}")
```

### Daily briefing:

```python
briefing = analyzer.daily_briefing(news)

print(f"Recommendation: {briefing.recommendation}")
print(f"Key events: {briefing.key_events}")
print(f"Risks: {briefing.risks}")
```

### Trade explanation:

```python
explanation = analyzer.explain_trade({
    'symbol': 'BTCUSDC',
    'direction': 'LONG',
    'pattern': 'EMA_PULLBACK_BULLISH',
    'technical_score': 75,
    'sentiment_score': 0.4,
    'reasoning': ['Bullish trend', 'Volume confirms']
})

print(explanation)
```

---

## 📚 Dodatkowe zasoby

- [LM Studio Documentation](https://lmstudio.ai/docs)
- [Ollama Documentation](https://ollama.com/docs)
- [Llama 3 Model Card](https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct)

---

## ✅ Checklist przed startem

- [ ] LM Studio zainstalowane
- [ ] Model Llama 3 8B pobrany
- [ ] Serwer uruchomiony na localhost:1234
- [ ] `config.yaml` skonfigurowany
- [ ] `pip install openai feedparser` wykonane
- [ ] `python test_llm.py` przechodzi pomyślnie
