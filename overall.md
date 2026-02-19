# Stealth overall notes

## RLBot GUI quick run checklist
1. **Install / update RLBotGUI** – grab the latest release from https://github.com/RLBot/RLBotGUI and install it; the GUI automatically detects Rocket League via Steam or Epic.
2. **Activate the bundled Python env** – in PowerShell run `cd C:\Users\arnav.STEALTH\AppData\Local\RLBotGUIX\MyBots\Stealth; .\rll\Scripts\activate` so that dependencies from `requirements.txt` stay in sync with RLBot.
3. **Launch RLBotGUI** – start the app, go to the *Local Bots* tab, and click **Add Existing Bot**.
4. **Point RLBotGUI at this folder** – select `C:\Users\arnav.STEALTH\AppData\Local\RLBotGUIX\MyBots\Stealth\rlbot.cfg`. RLBotGUI will read the Python agent definition straight from that config.
5. **Set the interpreter once** – in the bot card, open *Advanced Settings ▸ Python executable* and browse to `...\Stealth\rll\Scripts\python.exe`. RLBotGUI will re-use this interpreter for future launches.
6. **Queue matches** – hit *Launch Rocket League* (if it is not already running), select the Stealth bot in the GUI, choose an opponent (e.g., `vs_allstar.cfg` or `compare_vs_nexto.cfg`), then press **Start Match**. The GUI will call `python run.py -c <cfg>` behind the scenes using the interpreter you configured.

## Feature log (implemented improvements)

### Anti-ball-chasing behavior (v2.0)
- **Smart game state detection**: The bot now identifies when it has ball possession vs when teammates are closer, preventing double-commits via `_has_ball_possession()` and `_teammate_has_priority()` functions.
- **Situational positioning**: Instead of always chasing the ball, the bot uses `_get_positioning_target()` to predict ball movement and position strategically.
- **Defensive awareness**: `_should_prioritize_defense()` detects dangerous situations where the bot should rotate back instead of continuing to attack.

### Fixed dribbling boost usage
- **Dribbling-specific boost logic**: `_should_boost_while_dribbling()` allows boost usage with wider angle tolerance (0.8 radians vs 0.35) when the ball is close (<250uu).
- **Speed maintenance**: The bot now boosts during dribbles to maintain ball control when speed drops below 800-1100 uu/s.
- **Conservative boost management**: Only boosts when sufficient boost remains (>5 for basic, >20 for sustained control).

### Enhanced game state branches
- **DRIBBLE/DRIBBLE_SHOOT**: Active when the bot controls the ball (close, slow-moving, ground-level).
- **DEFEND**: Triggered when ball is behind the bot or opponents are threatening.
- **POSITION**: Smart positioning instead of blind ball chasing when no clear shot exists.
- **SUPPORT**: Cooperative rotation when teammates have better positioning.

### Cooperative rotations (enhanced)
- The bot yields possession when teammates are 350+ uu closer and not behind the play.
- Supports back-post rotation during opponent pressure via `_defensive_rotation_target()`.

### Boost conservation + pad priority (enhanced) 
- Prioritizes small pads when boost <35, escalates to full pads only when urgent (<8) or no small pads available.
- Prevents boost waste while chasing pads via `conserve_boost` flag.
- Enhanced scoring algorithm considers distance, alignment, and pad type.

## Technical improvements

### Better angle tolerance for boost
- General boost usage now allows up to 0.6 radians deviation (was 0.35) for more responsive play.
- Dribbling mode allows up to 0.8 radians for ball control situations.

### Ball possession detection
- Distance check: <200uu from ball
- Speed check: Ball moving <1200uu/s (controllable)  
- Height check: Ball <150uu high (dribbleable)

### Defensive triggers
- Ball on own side of field AND behind car position
- OR opponent significantly closer (400+uu) to ball on own side

## References used (with GitHub links)
- RLBot core API – https://github.com/RLBot/RLBot (used for BaseAgent, `GameTickPacket`, and ball prediction helpers).
- RLBotGUI project – https://github.com/RLBot/RLBotGUI (source of the GUI workflow described above).
- RLBot Quick Start wiki – https://github.com/RLBot/RLBot/wiki/Quick-Start (referenced for config names and interpreter wiring).
