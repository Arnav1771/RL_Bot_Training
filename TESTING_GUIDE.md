# Testing Against Pro Bots

This branch (`pro_necto`) includes comparison setups against world-class ML bots.

## Available Comparison Matches

### 1. Stealth vs **Necto** (Hybrid ML + Rules)
- **Config:** `compare_vs_necto.cfg`
- **Bot:** World champion, hybrid approach (ML mechanics + rule-based strategy)
- **Run:** `python run.py -c compare_vs_necto.cfg`

### 2. Stealth vs **Nexto** (Pure ML)
- **Config:** `compare_vs_nexto.cfg`
- **Bot:** Pure reinforcement learning (PPO trained)
- **Run:** `python run.py -c compare_vs_nexto.cfg`

## Quick Start

**Option A: Command Line**
```bash
# vs Necto (hardest)
python run.py -c compare_vs_necto.cfg

# vs Nexto (pure ML)
python run.py -c compare_vs_nexto.cfg
```

**Option B: RLBot GUI**
1. Open RLBot GUI
2. Click **"Add"** → **"Load folder"**
3. Navigate to `Stealth/src/bot.cfg` (your bot)
4. Click **"Add"** again → **"Load folder"**
5. Navigate to `Necto/rlbot-support/Necto/bot.cfg` (or Nexto)
6. Assign to opposite teams (Blue vs Orange)
7. **Start Match**

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
