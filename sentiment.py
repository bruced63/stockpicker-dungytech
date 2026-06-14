"""
sentiment.py — News sentiment analysis for StockPicker Web
"""

import yfinance as yf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


def analyze_sentiment(ticker):
    """Fetch news and analyze sentiment. Returns dict with headlines and summary."""
    ticker = ticker.upper()
    try:
        t = yf.Ticker(ticker)
        news_items = t.news
    except Exception as e:
        return {"error": str(e), "ticker": ticker}

    if not news_items:
        return {"ticker": ticker, "headlines": [], "summary": None}

    analyzer = SentimentIntensityAnalyzer()
    headlines = []
    compound_scores = []

    for item in news_items[:15]:
        content = item.get('content', {})
        if isinstance(content, dict):
            headline = content.get('title', '') or item.get('title', 'No title')
        else:
            headline = item.get('title', 'No title')

        if not headline or headline == 'No title':
            continue

        scores = analyzer.polarity_scores(headline)
        compound = scores['compound']
        compound_scores.append(compound)

        if compound >= 0.05:
            label = "POSITIVE"
        elif compound <= -0.05:
            label = "NEGATIVE"
        else:
            label = "NEUTRAL"

        headlines.append({
            "text": headline,
            "score": round(compound, 3),
            "label": label,
        })

    summary = None
    if compound_scores:
        avg = sum(compound_scores) / len(compound_scores)
        pos = sum(1 for s in compound_scores if s >= 0.05)
        neg = sum(1 for s in compound_scores if s <= -0.05)
        neu = len(compound_scores) - pos - neg

        if avg >= 0.05:
            overall = "POSITIVE"
        elif avg <= -0.05:
            overall = "NEGATIVE"
        else:
            overall = "NEUTRAL"

        summary = {
            "avg_score": round(avg, 3),
            "overall": overall,
            "positive": pos,
            "negative": neg,
            "neutral": neu,
            "total": len(compound_scores),
        }

    return {"ticker": ticker, "headlines": headlines, "summary": summary}


def get_sentiment_score(ticker):
    """Return just the compound score (for recommender). Silent mode."""
    try:
        t = yf.Ticker(ticker.upper())
        news_items = t.news
        if not news_items:
            return 0.0

        analyzer = SentimentIntensityAnalyzer()
        scores = []
        for item in news_items[:10]:
            content = item.get('content', {})
            if isinstance(content, dict):
                headline = content.get('title', '') or item.get('title', '')
            else:
                headline = item.get('title', '')
            if headline:
                s = analyzer.polarity_scores(headline)['compound']
                scores.append(s)

        return sum(scores) / len(scores) if scores else 0.0
    except Exception:
        return 0.0
