# Quant Guild — Knowledge Compilation: Risk, Strategy & Portfolio Engineering

**Source**: 8 transcripts from Quant Guild (Roman)  
**Extracted**: Decision logic only — no summaries, no opinions.

---

## 1. VOLATILITY RISK PREMIUM EXPLAINED
**Source**: kmAE9ZhQ0jU.txt

### SOPs
1. Compute realized volatility from historical returns: take rolling window mean → variance → square root.
2. Compute implied volatility: back out vol from Black-Scholes model using current option prices.
3. Regress forward realized vol against current implied vol; if slope < 1 (Y=X line), implied vol is overstated on average → sell vol.
4. To harvest VRP: sell straddles, strangles, naked calls, or naked puts at points on the implied vol surface where overpricing is greatest.
5. Simultaneously hold a long convexity hedge (portfolio insurance) to protect tail risk during drawdowns.
6. During a crisis (outlier on VRP regression): roll down and monetize the convexity layer; use proceeds to buy assets at discount.
7. When crisis resolves, resume short-vol harvesting.

### Fundamental Principles
- Selling insurance is profitable only if the insurance is statistically overpriced.
- Implied volatility is the market's forward-looking measure; realized volatility is backward-looking and a **latent process** (cannot be directly observed).
- Both selling and buying portfolio insurance can be simultaneously profitable — the difference is **timing**.
- Window size for realized vol computation dramatically changes lag and statistical relationship to implied vol.
- The individual option contract is a **zero-sum game**; the edge comes from aggregate statistical relationship.

### Key Concepts
- **Volatility Risk Premium (VRP)**: The statistical tendency for implied volatility to exceed subsequently realized volatility.
- **Implied Volatility**: Volatility backed out of Black-Scholes to reproduce current market option prices. Forward-looking.
- **Realized Volatility**: Standard deviation of observed historical returns. Backward-looking, latent process.
- **Latent Process**: A process that exists but cannot be directly observed; must be inferred from data.
- **Implied Volatility Surface**: Collection of implied volatilities across strikes and expiries; forms a "smile" reflecting overpricing of puts.
- **Volatility Drag**: Gap between arithmetic and geometric mean returns; compounds against high-vol strategies over time.
- **Convexity Layer**: Long volatility position that pays off disproportionately during crashes.

### Named References
- Black-Scholes model (pricing, not prediction)
- VIX
- S&P 500 / SPX
- Interactive Brokers (data/API)

---

## 2. MODELING TAIL RISK
**Source**: -sE1kz-fypI.txt

### SOPs
1. Gather daily returns (e.g., SPY ETF, 25 years).
2. Compute empirical mean and standard deviations; flag returns >5σ as Black Swan events.
3. Fit a **static normal distribution** to returns → observe that it **dramatically underestimates** tail event frequency.
4. Abandon static parametric models for tail risk — they are a "full-scale failure."
5. Implement **GARCH(1,1)** or similar regime model to classify periods into low/mid/high volatility regimes.
6. For each regime, fit a separate conditional distribution → compute tail event probabilities per regime.
7. Validate: high-vol regime should show ~12.5 days expected between extreme moves (vs. ~7,000 years from static model).
8. Use regime-aware VaR / CVaR / expected shortfall for position sizing.
9. **Walk-forward validation fails** for tail events — no historical sample fully represents the next crisis.
10. Size positions based on survival probability under worst-case shock (20-80% drawdown), not on historical frequency.

### Fundamental Principles
- Static parametric models (normal distribution) are a **full-scale failure** for tail risk estimation.
- Market returns exhibit **excess kurtosis** (fat tails, leptokurtic).
- **Goal is positioning for survival, not prediction.** No model can predict the future.
- No two Black Swan events are equivalent — historical data cannot fully proxy for future crises.
- Walk-forward validation can be overfitted if hyperparameters are tuned to death.
- You can position for survival even with incorrect distributions — survival probability is what matters.
- A casino may refuse a large bet even with a house edge — same logic applies to portfolio risk.

### Key Concepts
- **Black Swan Event**: Returns that shatter statistical expectations; 19 observed in SPY over 25 years at 5σ threshold.
- **Leptokurtic Distribution**: Distribution with fat tails and a sharp peak; market returns exhibit this.
- **Regime Modeling**: Partitioning data into volatility regimes (low/mid/high) with separate conditional distributions.
- **GARCH(1,1)**: Generalized Autoregressive Conditional Heteroskedasticity model; forecasts volatility regimes.
- **Walk-Forward Validation Failure**: Historical empirical probabilities fail to represent losses in the next, unprecedented crisis.
- **Positioning vs. Prediction**: Aim for survival under adverse scenarios; don't claim to predict the future.
- **Maximum Optionality**: Maintaining the ability to act (buy fire sales) during crises.

### Named References
- Great Depression, post-WWII adjustment, Vietnam/OPEC inflation, Bretton Woods, GFC, COVID, 2025 terror shock
- Japan's lost decades (1989–2024 for peak recovery)
- GARCH(1,1) model
- Bloomberg (data source)

---

## 3. YOU DO NOT NEED TO BACKTEST
**Source**: KD_fh_jA_iQ.txt

### SOPs
1. Identify the **source of returns** in a portfolio segment (what "game" produces those returns).
2. Determine if a candidate strategy is **physically and stochastically independent** from that source (not just diversification — true independence).
3. Run a CAPM regression of the strategy returns on the market returns; R² ≈ 0 confirms independence.
4. Construct a portfolio combining orthogonal return streams (e.g., 50% SPY + 50% managed futures ETF).
5. Compare Sharpe ratio, geometric growth rate, and max drawdown of the combined portfolio vs. each component alone.
6. Apply leverage to the hedged portfolio; the **volatility drag** advantage means leverage is safer than on an unhedged portfolio.
7. The objective: beat the market on **geometric growth rate** and **max drawdown**, not necessarily Sharpe.

### Fundamental Principles
- **Backtesting is overfitting historic data** — it answers "what worked before?" not "what will work?"
- **It was never about the players; it was always about the game.** Focus on the return-generating mechanism, not individual assets.
- Pricing models (CAPM, Fama-French, etc.) **do not predict** — they explain return streams.
- **Physical and stochastic independence** between return streams is what creates portfolio edge, not mere diversification.
- Diversification fails when you need it most (correlations explode to 1 in crises).
- **Volatility drag** makes leverage on unhedged portfolios extremely dangerous (50% drawdown at 2x on SPY).
- Leverage on a hedged portfolio is safer because lower drawdown → lower volatility drag → better geometric compounding.

### Key Concepts
- **Orthogonal Return Streams**: Return streams that are physically independent (unrelated to market beta). E.g., sports betting, prediction markets, managed futures, sentiment signals.
- **Volatility Drag**: The gap between arithmetic and geometric returns; grows nonlinearly with leverage.
- **Geometric Growth Rate**: The compounded long-run growth rate; the metric that actually determines wealth accumulation.
- **Physical Independence**: Two return streams that have no causal or structural relationship (unlike correlation which can spike).
- **Stochastic Independence**: Statistical independence of return processes.

### Named References
- CAPM (Capital Asset Pricing Model)
- Fama-French factor models
- SPY ETF (S&P 500 proxy)
- DBMF (Managed Futures ETF)
- Interactive Brokers / Trader Workstation

---

## 4. WHEN DOES A TRADING STRATEGY NEED TO BE SECRET
**Source**: WsEwKlr_1lA.txt

### SOPs
1. Classify a strategy by whether its returns depend on **market beta** (regress strategy on market; high R² = beta-dependent).
2. If R² is high → strategy is overexposure to market; **no secrecy needed** — it's just levered beta.
3. If R² ≈ 0 → strategy is orthogonal to market; assess whether it captures a **documented or undocumented risk premium**.
4. If the premium is **well-documented** and widely known → it will eventually dry up as capital crowds in.
5. If the premium is **undocumented/unexploited** (private data, novel inefficiency) → secrecy is required.
6. To maintain edge: continuously seek new orthogonal return streams; adapt to regime changes.

### Fundamental Principles
- Most strategies do NOT need to be secretive — they are just overexposure to market beta.
- **Allocation of risk is stepping up to the plate** — you don't choose the pitch, but you can position for different pitches.
- Factor models **explain** returns; they do **not predict** them.
- Strategies that depend on the market doing something are inherently non-secret.
- Strategies that capture a **systematic, undocumented market inefficiency** or provide **liquidity** (market making) need secrecy.
- Hedge fund strategies for positioning and survival are **not secretive** — they are portfolio engineering.

### Key Concepts
- **Undiversifiable Risk**: Market-wide risk factors that everyone is exposed to (beta). The "wind" blowing.
- **Risk Premiums**: Market risk premium, variance risk premium, small minus big, high minus low, momentum — documented return streams.
- **Alpha as Home Run**: Consistently generating unexplainable return (relative to a pricing model) is like consistently hitting home runs — rare and valuable.
- **Pitcher/Batter Analogy**: Market regime = pitcher; you = batter; you can't predict the pitch but can position for different ones.
- **Regime Classification**: Bull, bear, or sideways — knowing the "pitcher" helps position but doesn't guarantee outcomes.

### Named References
- Fama-McBeth regressions
- Variance Risk Premium (VRP)
- Market risk premium
- Small minus big (SMB), High minus low (HML), Momentum factors

---

## 5. WHAT THE F*CK IS ALPHA
**Source**: 21SONVlvkDQ.txt

### SOPs
1. Compute strategy returns and pair with market (S&P 500) returns.
2. Run linear regression: strategy returns = α + β × market returns + ε.
3. **β (beta)** = slope = how strategy moves with the market.
4. **α (alpha)** = intercept = return orthogonal to the pricing model; unexplained by beta.
5. If β neutralized (hedged out), α is the residual return — this is true alpha.
6. If α exists, investigate: is it capturing an undocumented risk premium, a mispricing, or is it just a statistical anomaly?
7. Alpha appears when **positioning pays off** relative to a pricing model (e.g., hedge sleeve activates during a crash).

### Fundamental Principles
- **Alpha is NOT "return above the S&P 500."** That is excess return, potentially just beta exposure.
- **Alpha is return orthogonal to a selected pricing model** — unexplained by systematic risk factors.
- The **joint hypothesis problem**: alpha may disappear if you add the right risk factors.
- **Everything is mispriced.** Law of one price fails in practice (car insurance quotes prove it).
- Mispricings create inefficiencies → those inefficiencies produce alpha.
- Hedging a portfolio can generate alpha when the hedge pays off during a crisis (positioning, not prediction).
- **Alpha ≠ stock picking success.** High-beta stock picks may show excess return but not alpha.

### Key Concepts
- **Alpha**: Intercept in a regression of strategy returns on a pricing model; return orthogonal to priced systematic risk.
- **Beta**: Slope of the regression; sensitivity to market returns.
- **Pricing Model**: A framework (CAPM, Fama-French, etc.) for explaining returns — NOT predicting them.
- **Joint Hypothesis Problem**: Alpha may be mispricing or may be unaccounted-for risk factors.
- **Excess Return**: Return above a benchmark — often confused with alpha but is frequently just beta.
- **Zero-Sum Game**: Fair game where neither party has an edge; real markets are NOT zero-sum because of mispricing.

### Named References
- CAPM
- Fama-French models
- VRP desk (referenced as colleague's role)
- Efficient Market Hypothesis (mentioned as incomplete)

---

## 6. ACADEMIA IS WRONG — MARKETS ARE NOT EFFICIENT
**Source**: EwRlKEjJcr0.txt

### SOPs
1. Understand that the Efficient Market Hypothesis (EMH) is a **framework for thinking**, not a description of reality.
2. Recognize that "priced in" means current equilibrium = market's best guess of fair value — **not the actual fair price**.
3. Identify mispricings by comparing equilibrium price to fundamental/quantitative analysis of expected value.
4. Build models from **first principles** — understand the trivial questions, not just the complex proofs.
5. Ask "if this already happened, why do you think it will happen again?" of any backtest result.
6. Accept that all models are wrong; the goal is to be **less wrong** than competitors.
7. Don't trivialize questions — the most basic questions often reveal the biggest logic gaps.

### Fundamental Principles
- **EMH does not mean everything is efficiently priced.** It means equilibrium = current expectation, not fair value.
- Fast price reaction to news ≠ rational pricing. Supply/demand drives ephemeral shocks.
- **Wealth is built through expectations and shattered expectations** — not through efficient pricing.
- "Why bother? It's priced in" is the most dangerous misconception in finance.
- **Alpha is return orthogonal to systematic risk** — not excess return above S&P 500.
- **Trivial questions are the most valuable** — ask them even if you look stupid.
- **Don't be afraid to look trivial** — being wrong is far more expensive.

### Key Concepts
- **Efficient Market Hypothesis (EMH)**: Framework stating markets incorporate available info into prices; NOT that prices are always "correct."
- **Equilibrium Price**: Current market consensus on fair value; changes as expectations change.
- **Shattered Expectations**: The mechanism by which wealth is created in markets.
- **First Principles Reasoning**: Building understanding from fundamentals rather than accepting textbook conclusions.
- **Alpha Decay**: The notion that alpha disappears when strategies become well-known — debated.
- **Joint Hypothesis Problem**: Any test of market efficiency is simultaneously a test of the asset pricing model used.

### Named References
- Efficient Market Hypothesis (EMH)
- CAPM, Fama-French models
- Quonkyld.com (Roman's educational platform)

---

## 7. STOCK PICKING IS WORSE THAN GAMBLING
**Source**: E2PuxT_SucA.txt

### SOPs
1. Recognize that any stock pick carries **beta exposure** to the market — returns are not purely idiosyncratic.
2. Compare max drawdown of stock pick vs. market over the same period; stock pick drawdown will be amplified by beta.
3. Compute volatility drag: measure the gap between arithmetic and geometric returns.
4. Condition on **bottom 10% of sample paths** to see worst-case outcomes.
5. Stock picking bottom 10%: ~80% max drawdown, negative CAGR (-1.9%).
6. Market holding bottom 10%: ~50% max drawdown, positive CAGR (10%).
7. Improve market portfolio by adding **hedge and monetization layers** to beat stock picking on both growth rate and worst-case drawdown.
8. Never chase ephemeral returns — you don't get to choose which sample path you walk.

### Fundamental Principles
- **Stock picking is worse than gambling** because it can appear to work then blow out your account.
- A significant portion of stock picking returns come from **passive beta exposure**, not idiosyncratic outperformance.
- **You don't get to choose which sample path you walk** — this is the fundamental constraint of risk.
- **You don't get something for nothing** — higher expected returns come with higher volatility drag.
- **Volatility drag** is the gap between arithmetic and geometric returns; it compounds against high-vol strategies.
- Bottom 10% of stock-picking paths: 80% max drawdown, negative CAGR.
- Bottom 10% of market holding paths: 50% max drawdown, positive CAGR.
- Survivorship bias is the argument "it came back" — what about when it doesn't?

### Key Concepts
- **Volatility Drag**: Nonlinear amplification of losses through compounding; the difference between arithmetic and geometric mean returns.
- **Sample Path**: The specific trajectory of returns an investor walks; you don't choose it — probability does.
- **Beta Exposure**: Sensitivity to market returns; present in all stock picks regardless of quality.
- **Geometric Return Compounding**: Growth on growth; the actual long-run wealth trajectory.
- **Bottom 10% Path Analysis**: Conditioning simulation on worst-case outcomes to assess survival probability.
- **No Free Lunch**: You never get something for nothing; higher returns always carry higher risk.

### Named References
- VRT (example stock: 3000% gain, 61% drawdown, beta 2.22)
- S&P 500 (benchmark)
- Quonkyld.com (educational platform)

---

## 8. HOW TO THINK ABOUT STOCK MARKET BUBBLES
**Source**: A6QWWrhDJTc.txt

### SOPs
1. Reject the word "bubble" as a label — reframe in terms of **expectations**.
2. Assess current market as the equilibrium of current expectations (whether rational or not).
3. Identify potential **catalysts** that could shatter expectations (geopolitics, regulation, technology failure, policy change).
4. Stress-test portfolio: what happens if this asset drops 40%, 80%?
5. Position for survival: hold hedge/insurance so that during a crisis you have cash to buy the fire sale.
6. Do NOT be a liquidity provider during a fire sale — selling in a 40% drawdown is catastrophic.
7. Monitor for slow bleeds vs. violent crashes — different responses to shattered expectations.
8. Think in terms of **compound annual growth rate over 10-40 years**, not next quarter's return.

### Fundamental Principles
- **Reject the "bubble" label** — it's doomsaying without analytical value.
- Reframe everything as **expectations and shattered expectations** — this is how markets work.
- **There will be another crisis** — on average, one every ~10 years with 20-80% drawdowns.
- It is **not about prediction** — it is about positioning for survival.
- Market equilibrium = current consensus expectations; whether rational is subject to discussion.
- When expectations shatter, market responds with either a violent crash or slow bleed.
- After repricing, assets find a new floor → often severely underpriced → opportunity to buy.
- **Long-term CAGR** is the true measure, not short-term returns.
- Irresponsible monetary/fiscal policy + inflated expectations = inevitable corrections.

### Key Concepts
- **Bubble (reframed)**: Not a predictive label but a description of shattered expectations and subsequent repricing.
- **Expectations Framework**: Markets price in current consensus; risk = deviation from expectations.
- **Shattered Expectations**: The catalyst-driven transition from one equilibrium to another (crash or slow bleed).
- **Fire Sale**: Market-wide liquidation during a crisis; opportunity for positioned investors to buy cheaply.
- **Liquidity Provider in Crisis**: Selling assets during a drawdown — the worst position to be in.
- **Volatility Drag on Long Horizons**: Overexposure to high-beta strategies compounds losses over 10-40 year horizons.
- **Survival Probability**: The probability of weathering a worst-case scenario without catastrophic loss.

### Named References
- Great Depression, post-WWII adjustment, Vietnam/OPEC inflation, Bretton Woods, GFC, COVID, 2025 terror shock
- Japan's lost decades (1989–2024)
- AI bubble discussion (2024-2025)
- MIT study on AI productivity (dismissed as outdated)
- Dot-com bubble (2001)

---

## CROSS-CUTTING PRINCIPLES (Across All 8 Transcripts)

### Universal Decision Logic
1. **Position for survival, never predict.** — No crystal ball exists; optimize for worst-case scenarios.
2. **Volatility drag destroys wealth nonlinearly.** — High-vol strategies compound against you; minimize drawdowns to maximize geometric growth.
3. **The game, not the players.** — Understand the return-generating mechanism, not individual assets.
4. **Physical independence > diversification.** — True orthogonal return streams, not just uncorrelated stocks.
5. **All models are wrong.** — Accept model/parameter risk; be less wrong than competitors.
6. **Everything is mispriced.** — Law of one price fails; mispricings = opportunity = potential alpha.
7. **Ask trivial questions.** — The most basic questions reveal the deepest logic gaps.
8. **You don't get something for nothing.** — Every return has a cost; every edge has a limitation.
9. **Equilibrium ≠ fair price.** — Market consensus can be wrong; shattered expectations create wealth.
10. **Survival first, growth second.** — A 50% loss requires a 100% gain to recover; a 20% loss only needs 25%.

### Recurring Framework
- **Car Insurance Analogy**: You pay premiums for protection you hope not to use; same logic applies to portfolio hedging.
- **Casino Analogy**: You are the casino — you need multiple games (orthogonal return streams) and a house edge (statistical advantage).
- **Baseball Analogy**: You step up to the plate (allocate risk); you don't choose the pitch (market regime); you position for different pitches.
- **Japan Lost Decades**: The cautionary example — US equities could underperform for decades; never assume past performance continues.

### Named References (Cumulative)
- **Models**: Black-Scholes, CAPM, Fama-French (3-factor, 5-factor), GARCH(1,1)
- **Markets/Instruments**: S&P 500, SPY ETF, VIX, SPX, VRT, DBMF (Managed Futures ETF)
- **Concepts**: Volatility Risk Premium, Volatility Drag, Alpha, Beta, Regime Modeling, Walk-Forward Validation
- **Platform**: Quonkyld.com (Roman's educational platform)
- **Broker**: Interactive Brokers / Trader Workstation
- **Historical Events**: Great Depression, Vietnam/OPEC, Bretton Woods, Dot-com (2001), GFC (2008), COVID (2020), 2025 terror shock, Japan lost decades (1989-2024)
