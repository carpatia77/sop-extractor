# Quant Guild Knowledge Compilation: Career, Mindset & Portfolio Construction

---

## 1. Why I Quit Being a Quant Researcher
### SOPs
- [None explicitly taught - this is a personal narrative]

### Fundamental Principles
- Mental health is not optional - neglecting it creates career-ending problems just like physical neglect
- Vulnerability and transparency are necessary - emotional suppression compounds like debt with interest
- Comparison is the thief of joy - your struggles are valid regardless of others' situations
- You don't get something for nothing - there's always a cost, especially when deferred

### Key Concepts
- Imposter syndrome: Psychological state of feeling inadequate despite evidence of competence
- Isolation in quant work: Remote coding/paper reading for 12-16 hours daily without human contact
- Mental health debt: Suppressing emotional problems creates compounding interest-like costs
- Academic gaming: Publication points over genuine research in some PhD programs

### Named References
- Bloomberg (Bruno's team)
- Columbia University (MSOR program)
- PhD programs in Tennessee
- CAPM, diversifiable vs undiversifiable risk

---

## 2. Projects to Help you Become a Quant Intermediate
### SOPs
**Market Making Project:**
1. Select underlying model (GBM, Merton Jump Diffusion)
2. Use matching pricing model (Black-Scholes for GBM)
3. Quote bid-ask spread around mid price
4. Monitor cumulative PnL vs expected edge
5. Assess model risk impact on equity curve

**PDE Solver Project:**
1. Select option type (vanilla, barrier, digital, American)
2. Derive pricing PDE from assumptions
3. Determine if analytically tractable
4. If closed form exists → use analytical solution
5. If not → use Monte Carlo (Feynman-Kac) or finite differences
6. Understand when to use each method

**Order Book Simulator:**
1. Understand price priority (best bid/ask first)
2. Understand time priority (FIFO at same price)
3. Place limit orders and observe placement
4. Monitor spread, mid price, slippage
5. Identify simplifying assumptions vs live market

### Fundamental Principles
- If model matches true market dynamics → accumulate spread asymptotically
- GBM pricing in jumpy world = pennies in front of steam roller
- 80% of quant work is data cleaning/preparation, not backtesting
- Models don't need to be correct, just sufficiently not wrong

### Key Concepts
- Model risk: Risk that pricing model doesn't match true market dynamics
- Ladder risk: Risk from the true process the market follows
- Geometric Brownian Motion (GBM): Continuous random walk assumption for asset prices
- Merton Jump Diffusion: Model incorporating gap risk/jumps
- Price priority: Orders matched at best price first
- Time priority: Orders at same price matched FIFO
- Feynman-Kac theorem: Links PDEs to probabilistic expectations
- Risk neutrality: Pricing framework where expected return = risk-free rate

### Named References
- Black-Scholes model
- Merton Jump Diffusion model
- Geometric Brownian Motion
- Feynman-Kac law of large numbers
- Finite differences method

---

## 3. Live Capital Management: My 2025 Crisis Alpha
### SOPs
**Crisis Alpha Monetization:**
1. Identify drawdown depth (S&P % decline)
2. Assess volatility persistence vs collapse
3. If V-shaped recovery expected → hold cash for allocation
4. Allocate to overexposure beta or tech during drawdown
5. Monetize via profit-taking on long convexity or margin call cash
6. Target assets with aggressive rally response

**Insurance Selection:**
1. Identify points on volatility surface offering protection
2. Compare coverage quality across different strike/time combinations
3. Select insurance with lowest negative carry for equivalent coverage
4. Account for path dependency in entry timing
5. Consider ratio spreads (finance protection with upside calls)

### Fundamental Principles
- Markets are violently inefficient - V-shaped recoveries create alpha opportunities
- Real wealth is built in the right tail through proper position sizing
- Volatility must be mean reverting - it measures expected deviation from expectation
- You don't need to time bottoms - monetize over entire recovery window
- Positioning and survival > raw PnL

### Key Concepts
- Volatility drag: Difference between arithmetic and geometric means due to variance
- Crisis alpha: Returns generated specifically during market dislocations
- Long convexity: Positions that benefit disproportionately from large moves
- Monetization window: Period available to allocate capital during recovery
- Leverage effect: Disproportionate return decrease when volatility spikes
- Path dependency: Entry timing affects equity curve even with same convexity

### Named References
- Interactive Brokers (brokerage)
- GARCH volatility forecasting
- S&P 500 benchmark
- VIX (volatility index)
- Tariffs (2025 policy event)

---

## 4. A REAL Quant Debunks the Day Trading Scam
### SOPs
**Position Sizing Framework:**
1. Calculate win rate from historical data
2. Determine average win size vs loss size
3. If win rate × win size > loss rate × loss size → positive edge
4. Size positions to survive drawdowns
5. Never risk account on single trades

**Hedged Portfolio Construction:**
1. Hold core beta exposure (S&P 500)
2. Add hedge sleeve (puts, alternatives)
3. Accept lower upside in good years
4. Capture downside protection in bad years
5. Let compound growth work over 5+ year periods

### Fundamental Principles
- No free lunch - you never get something for nothing
- Lottery ticket effect: People need cash quickly, don't understand risk
- Statistics don't converge in real markets - no counterfactuals
- All models are wrong, some are useful
- Positioning and survival > ephemeral gains
- Learning compounds like returns - stay for long-term payoff

### Key Concepts
- Volatility drag: High variance destroys compound growth
- Rule of 72: Years to double = 72 / CAGR%
- Counterfactual: What would have happened if - impossible in markets
- Regime change: Market dynamics shift, breaking historical patterns
- Edge decay: Win rate degrades out of sample
- Convexity: Growth on growth - the real wealth builder

### Named References
- Rule of 72
- Sharpe ratio
- Geometric mean vs arithmetic mean
- CAPM
- Citadel, Jane Street (as industry benchmarks)

---

## 5. Quant Explains Investing at 5 Different Levels
### SOPs
**Risk Assessment Framework:**
1. Identify all risks for investment (idiosyncratic + market)
2. Check weather forecast equivalent (macro conditions)
3. Assess information advantage vs crowd
4. Determine if price reflects fair value given information
5. Sleep test: Can you hold through adverse scenarios

**Portfolio Diversification Check:**
1. List all holdings
2. Conduct principal component analysis mentally
3. Identify which "basket" each stock belongs to
4. Check if看似 diversified but actually correlated
5. Add orthogonal return streams if needed

### Fundamental Principles
- Without risk, no potential for reward
- Not all risks are created equally
- Efficient markets: Supply/demand produces fair price given information
- Diversification fails when you need it most (correlations → 1 in crisis)
- Principal directions of risk determine true portfolio exposure

### Key Concepts
- Idiosyncratic risk: Firm-specific business risk
- Market risk: Broader economic risk affecting all equities
- Undiversifiable risk: Systematic risk you cannot escape within an asset class
- Principal Component Analysis: Statistical method to find hidden correlation structures
- Equilibrium price: Fair value from supply/demand with many informed participants
- Efficient Market Hypothesis: Prices reflect all available information

### Named References
- Efficient Market Hypothesis
- Principal Component Analysis
- Supply and demand mechanics
- Diversifiable vs undiversifiable risk

---

## 6. I Met a Jane Street Quant at the Gym
### SOPs
**Structural Diversification:**
1. Identify statistical diversification (correlation-based)
2. Recognize it fails in crises (correlations → 1)
3. Add structurally independent return streams
4. Ensure physical/stochastic independence
5. Verify independence holds during market stress

**Hedging Protocol:**
1. Identify uncertainty to trade for certainty
2. Select appropriate derivative (put option example)
3. Calculate negative correlation with portfolio
4. Ensure structural (contractual) independence
5. Monitor for persistent anti-correlation

### Fundamental Principles
- Diversification is statistical mechanism - fails in crises
- Hedging trades uncertainty for certainty via contractual payout
- Structural diversification > statistical diversification
- Negative correlation from contracts is guaranteed, not estimated
- Purpose of hedging: reduce volatility drag, improve CAGR

### Key Concepts
- Statistical diversification: Reducing variance through uncorrelated assets (breaks in crisis)
- Structural diversification: Physically/stochastically independent return streams
- Non-stationary correlations: Correlation structures change over time
- Anti-correlation: Negative relationship guaranteed by contract terms
- Volatility drag reduction: Primary benefit of effective hedging

### Named References
- Jane Street (quant firm)
- Put option on NVIDIA (example)
- Black-Scholes (pricing framework)
- Sharpe ratio, Sortino ratio

---

## 7. I Want the Market to Crash
### SOPs
**Long Black Swan Positioning:**
1. Accept lower upside in normal markets
2. Build convexity layer (long volatility/puts)
3. Identify overpriced vs underpriced insurance on volatility surface
4. Minimize negative carry while maintaining coverage
5. Monetize during crises for outsized returns
6. Allocate to assets that recover aggressively

**Casino vs Player Framework:**
1. Think about the game, not individual outcomes
2. Backtesting = looking at player outcomes (incomplete)
3. Analyze game structure for edge
4. Set up favorable positioning for different states of world
5. Accept uncertainty - no crystal ball exists

### Fundamental Principles
- Nobody knows what will happen - not you, not Citadel, not Jane Street
- Be the casino, not the player
- Portfolio insurance is expensive but invaluable when needed
- Triple loss scenario: lose job + home equity + portfolio = catastrophe
- Positioning and survival > predicting

### Key Concepts
- Black swan events: Rare, high-impact market dislocations
- Convexity: Asymmetric payoff - limited downside, unlimited upside
- Portfolio insurance: Long volatility positions that pay in crises
- Negative carry: Cost of holding protective positions
- Triple loss: Simultaneous job loss + home equity decline + portfolio crash

### Named References
- Ryan Gosling in The Big Short (analogy)
- Michael Burry
- Citadel, Jane Street
- Japan 20-year equity winter
- CAPM, Fama-French factors

---

## 8. Why You Should Not Be a Quant
### SOPs
**Career Reality Check:**
1. Assess if you truly love math/probability/statistics/finance
2. Accept 80% of work is boring tasks (data cleaning, preprocessing)
3. Accept 95% of work product gets thrown out
4. Prepare for social dynamics and gatekeeping
5. Commit to years of study for seat at table

**Social Navigation:**
1. Ignore title wars (who's a "real" quant)
2. Accept colleagues will be intense/solitary types
3. Recognize soft skills earners make more with less math
4. Focus on love of work, not money
5. Build resilience to industry politics

### Fundamental Principles
- You won't be rich - you'll be comfortable but not rich
- Free time is a fallacy - all time goes to firm work
- 80% of time spent on tasks you don't want to do
- 95% of work product amounts to nothing (but builds experience)
- If you go in for money, you'll be miserable
- It takes insane amount of time to get seat at table

### Key Concepts
- Gatekeeping: Vile politics around who qualifies as a "quant"
- Pedigree obsession: Academic background, institution, advisor matter politically
- Research as stepping stones: Most paths are dead ends but build experience
- Soft skills premium: Business/communication skills earn more than pure math
- Opportunity cost: Years of study for uncertain outcome

### Named References
- Black-Scholes (founders' successor)
- Bloomberg
- Ivy League institutions

---

## 9. CAGR for Quant Finance
### SOPs
**CAGR Calculation:**
1. Identify initial principal
2. Identify final value
3. Apply formula: CAGR = (Final/Initial)^(1/years) - 1
4. Use for comparing strategies on equal footing
5. Apply Rule of 72 for quick doubling estimates

**BS Test for Strategies:**
1. Take claimed annual return
2. Apply to $100,000 over 30 years
3. If result exceeds world's wealth → strategy is false
4. Use CAGR to test feasibility of returns

### Fundamental Principles
- Geometric growth produces convexity (growth on growth)
- Arithmetic mean ≠ geometric mean when variance exists
- Volatility drag = Arithmetic mean - Geometric mean
- CAGR is backward-looking proxy, not forward guarantee
- Rule of 72: Years to double ≈ 72 / CAGR%

### Key Concepts
- CAGR: Fixed rate that would produce same terminal value via compound growth
- Geometric compounding: Multiplicative growth (multiplying by returns each period)
- Arithmetic growth: Additive growth (linear, straight line)
- Convexity: Curvature from compound growth - growing at growing rate
- Rule of 72: Quick estimate for doubling time

### Named References
- S&P 500 (7.5% inflation-adjusted CAGR)
- Rule of 72

---

## 10. The Quant Case for Bitcoin
### SOPs
**Monetary Asset Analysis:**
1. Identify price discovery process type (top-down vs bottom-up)
2. Compare to historical parallels (Bretton Woods collapse)
3. Assess attention mechanism impact on volatility
4. Evaluate retail vs institutional participation
5. Determine if volatility reflects asset viability or discovery process

**Bitcoin Volatility Framework:**
1. Acknowledge extreme drawdowns (120k → 60k)
2. Recognize bottom-up discovery magnifies volatility
3. Account for retail derivatives access
4. Factor in social sentiment as undiversifiable risk
5. Separate discovery volatility from fundamental viability

### Fundamental Principles
- Volatility during price discovery is expected, not a flaw
- Bottom-up discovery (Bitcoin) more volatile than top-down (gold)
- Social sentiment is undiversifiable risk for crypto
- Drawdowns don't justify asset failure - they're part of discovery
- Institutional vs retail participation changes volatility profile

### Key Concepts
- Price discovery: Process of finding fair value for new monetary asset
- Top-down discovery: Pegged system collapse (Bretton Woods → gold)
- Bottom-up discovery: Peer-to-peer distribution network (Bitcoin)
- Attention mechanism: Social media/retail amplifying volatility
- Undiversifiable risk: Systematic risk that cannot be diversified away

### Named References
- Bretton Woods (1970s collapse)
- Gold price discovery post-1970s
- GameStop (retail involvement example)
- Social sentiment research

---

# Cross-Cutting Principles

## Universal Rules
1. **No free lunch** - Nothing comes without cost
2. **Volatility drag destroys** - High variance kills compound growth
3. **Positioning > Prediction** - Nobody knows what happens next
4. **Structural > Statistical** - Guaranteed relationships beat estimated ones
5. **Survive first** - Can't compound if you blow out
6. **Learning compounds** - Stay for long-term payoff
7. **80/20 rule of work** - Most work is boring, most product gets discarded
8. **Mental health matters** - Neglect compounds like financial debt
9. **Be the casino** - Set up games with edge, don't be the player
10. **Convexity is king** - Real wealth built in right tail

## Key Formulas
- **Rule of 72**: Years to double = 72 / CAGR%
- **Volatility Drag**: Arithmetic Mean - Geometric Mean ≈ σ²/2
- **CAGR**: (Final/Initial)^(1/years) - 1
- **Sharpe Ratio**: (Return - Risk-free) / Volatility

## Career Reality
- 80% of time on unwanted tasks
- 95% of work gets thrown out
- Years to get seat at table
- Soft skills earn more than pure math
- Mental health neglect creates career-ending problems
- Gatekeeping and title politics are rampant
