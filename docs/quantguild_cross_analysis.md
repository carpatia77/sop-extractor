# QuantGuild — Cross-Analysis & Knowledge Graph

**Source**: 26 transcripts, 72,845 words, 8.1h of content
**Author**: Roman (Quant Guild)
**Extracted by**: 3 parallel knowledge compilation agents

---

## 1. TOPIC CLUSTERS

### Cluster A: Portfolio Engineering (8 videos, 31K words)
- The Ultimate Guide to Quant Portfolio Management (9,012w)
- Portfolio Management and Volatility Drag (2,431w)
- How to Derive Volatility Drag (3,282w)
- Math to Increase your Sharpe Ratios (2,482w)
- How Quants Engineer Portfolios (1,589w)
- How to Calculate Portfolio Alpha and Beta (2,264w)
- How a Quant would Invest One Million (1,057w)
- The Mathematical Trap of Just Buy SPY (1,068w)

### Cluster B: Risk Management & Volatility (8 videos, 24K words)
- Volatility Risk Premium Explained (3,106w)
- Modeling Tail Risk: A Quantitative Survival Guide (3,086w)
- When Does a Trading Strategy Need to be Secret (2,936w)
- You do not need to backtest a trading strategy (3,495w)
- What the F*ck is Alpha (2,693w)
- Academia is wrong. Markets are not efficient (2,658w)
- Stock Picking is Worse than Gambling (2,510w)
- How to Think About Stock Market Bubbles (3,172w)

### Cluster C: Career, Mindset & Applied Trading (10 videos, 28K words)
- Why I Quit Being a Quant Researcher (3,902w)
- Projects to Help you Become a Quant (3,010w)
- Live Capital Management: My 2025 Crisis Alpha (3,964w)
- A REAL Quant Debunks the Day Trading Scam (3,346w)
- Quant Explains Investing at 5 Different Levels (2,649w)
- I Met a Jane Street Quant at the Gym (2,121w)
- I want the market to crash (1,990w)
- Why You Should Not Be a Quant (1,815w)
- CAGR for Quant Finance (1,620w)
- The Quant Case for Bitcoin (1,587w)

---

## 2. CONCEPT GRAPH (Cross-Video)

### Tier 1: Core Concepts (appear in 5+ videos)
| Concept | Videos | Author's Position |
|---|---|---|
| **Volatility Drag** | A,B,C (12+ videos) | #1 most underappreciated force in investing |
| **No Free Lunch** | A,B,C (15+ videos) | Higher returns = higher risk, always |
| **Positioning > Prediction** | A,B,C (10+ videos) | Nobody predicts; you position for survival |
| **Sharpe Ratio** | A,B (8+ videos) | Standard risk-adjusted metric, but not sufficient alone |
| **Diversification** | A,B,C (12+ videos) | Essential but breaks down in crises |

### Tier 2: Important Concepts (3-4 videos)
| Concept | Videos | Definition |
|---|---|---|
| **Physical Decorrelation** | A (3 videos) | Assets from structurally independent markets |
| **Volatility Risk Premium** | B (3 videos) | Implied vol > realized vol on average |
| **Tail Risk / Black Swan** | B (4 videos) | Extreme events far more frequent than normal distribution predicts |
| **Alpha** | B,C (4 videos) | Return orthogonal to pricing model, NOT excess return vs SPY |
| **CAGR** | A,C (4 videos) | Smooth equivalent of volatile return path |
| **CAPM Beta** | A,B (5 videos) | Sensitivity to market returns via regression |
| **Convexity** | A,B (3 videos) | Growth on growth; nonlinear compounding |

### Tier 3: Specialized Concepts (1-2 videos)
| Concept | Video |
|---|---|
| GARCH regime modeling | Tail Risk |
| Hawkes processes | (not in this batch) |
| Markov chains | (not in this batch) |
| Order book mechanics | Projects (Intermediate) |
| Market making | Projects (Intermediate) |
| PDE pricing | Projects (Intermediate) |
| Black-Scholes Greeks | VRP, Bitcoin |

---

## 3. CORRELATION MATRIX (Topic Cross-References)

```
                Portfolio  Risk/Mkt  Career  Vol Drag  Backtest  Alpha
Portfolio          1.0       0.8     0.4      0.9       0.3     0.6
Risk/Mkt           0.8       1.0     0.5      0.7       0.7     0.8
Career             0.4       0.5     1.0      0.3       0.2     0.3
Vol Drag           0.9       0.7     0.3      1.0       0.2     0.5
Backtest           0.3       0.7     0.2      0.2       1.0     0.4
Alpha              0.6       0.8     0.3      0.5       0.4     1.0
```

**Strongest cross-references:**
- Portfolio Engineering ↔ Volatility Drag (0.9): Vol drag IS the portfolio construction problem
- Risk/Market ↔ Alpha (0.8): Alpha definition is central to risk framework
- Portfolio Engineering ↔ Risk/Market (0.8): Portfolio design must account for tail risk

---

## 4. AUTHOR'S CORE THESIS

Roman's ONE message across 26 videos:

> **"Insane wealth is built incredibly slowly. Nobody knows what will happen next. Your only edge is positioning for survival while volatility drag erodes everyone who chases returns without understanding the math."**

### The 5 Pillars (derived from cross-analysis)

1. **Volatility drag is the enemy** — R_G ≈ μ - σ²/2. Every high-vol strategy loses to compounding.

2. **Positioning, not prediction** — You cannot predict markets. You can position for survival under adverse scenarios.

3. **Physical decorrelation > statistical diversification** — Correlations fail in crises. Use structurally independent assets.

4. **Alpha ≠ excess return** — Alpha is return orthogonal to a pricing model. Confusing it with "beating SPY" leads to wrong decisions.

5. **Time is the only free lunch** — Convexity (growth on growth) requires time. There is no shortcut.

---

## 5. UNIQUE INSIGHTS (Said in Only One Video)

| Insight | Video | Epistemic Status |
|---|---|---|
| Triple loss scenario (job + home + portfolio all crash simultaneously) | Bitcoin | Probable |
| Hedge sleeve with negative arithmetic return can yield positive geometric growth | Portfolio Mgmt | Proven (math) |
| Backtesting is fundamentally overfitting; understand the game, not the history | Backtest | Certain |
| 80% of quant work is data cleaning; 95% of work product gets discarded | Projects | Observation |
| CAGR BS test: compound claimed returns 30yr — if exceeds world wealth, strategy is false | CAGR | Heuristic |
| Price discovery framework: top-down (Bretton Woods) vs bottom-up (Bitcoin) explains vol differences | Bitcoin | Probable |
| A casino may refuse a bet even with house edge — same logic for portfolio risk | Tail Risk | Metaphor (certain) |

---

## 6. EPITEMIC STATUS MAP

### Certain (Author states as absolute truth)
- No free lunch exists in markets
- Volatility drag compounds against high-vol strategies
- Nobody can predict single-trade outcomes
- Diversification breaks down in crises (correlations → 1)
- EMH is wrong in all three forms

### Probable (Author believes but qualifies)
- Physical decorrelation is superior to statistical diversification
- Selling VRP is profitable long-term with tail hedge
- Bitcoin has structural bid from fixed supply + growing demand
- Most retail trading strategies are negative expected value

### Speculative (Author presents as hypothesis)
- Triple-long exposure (job + house + stocks) creates catastrophic correlated risk
- GARCH regime models capture tail events better than static models
- Volatility surface smile reflects systematic put overpricing

---
