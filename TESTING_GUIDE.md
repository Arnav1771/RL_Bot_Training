# Testing Against Pro Bots

This branch (`pro_necto`) includes comparison setups against various opponents.

## Available Comparison Matches

### 1. Stealth vs **AllStar AI** (Built-in, Works Immediately)
- **Config:** `vs_allstar.cfg`
- **Bot:** Rocket League's built-in AllStar bot (hardest AI)
- **Run:** `python run.py -c vs_allstar.cfg`
- **✅ Recommended for testing** - No setup required

### 2. Stealth vs **Necto** (Hybrid ML + Rules)
- **Config:** `compare_vs_necto.cfg`
- **Bot:** World champion, hybrid approach (ML mechanics + rule-based strategy)
- **⚠️ Requires old PyTorch** - Installation issues with modern Python
- **Alternative:** Use RLBot GUI to download working version

### 3. Stealth vs **Nexto** (Pure ML)
- **Config:** `compare_vs_nexto.cfg`
- **Bot:** Pure reinforcement learning (PPO trained)
- **⚠️ Requires old PyTorch** - Installation issues with modern Python

## Quick Start

**Option A: Test vs AllStar (Easiest)**
```bash
python run.py -c vs_allstar.cfg
```

**Option B: Test vs yourself**
```bash
python run.py
# Runs 2 copies of Stealth against each other
```

**Option C: RLBot GUI** (Best for pro bots)
1. Open RLBot GUI
2. Click **"Download Bot Pack"** (downloads pre-configured bots)
3. Click **"Add"** → Load `Stealth/src/bot.cfg` (your bot)
4. Click **"Add"** → Pick any bot from the bot pack
5. Assign to opposite teams (Blue vs Orange)
6. **Start Match**

## What to Watch For

### Your Bot (Stealth)
- **SHOOT** label = Positioning to shoot at goal
- **INTERCEPT** = Leading the ball's path
- **CHASE** = Direct ball pursuit
- **BOOST** = Getting boost pads

### Necto/Nexto
- Fast aerials and wall play
- Better recovery mechanics
- Smarter positioning and rotation
- More consistent power shots

## Performance Expectations

- **Necto:** Expect to lose 0-10+ (it's a world champion)
- **Nexto:** Slightly easier but still very strong
- **Goal:** Get 1-2 touches on goal, score once = success for now

## Improving Your Bot

After watching the pros, focus on:
1. **Faster movement** - Necto is always supersonic
2. **Aerials** - They hit balls in the air
3. **Recovery** - They land on wheels instantly
4. **Positioning** - They predict where ball will be
