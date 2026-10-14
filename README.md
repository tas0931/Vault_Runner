# Vault Runner
 
Vault Runner is a single-player 3D stealth game developed entirely in **PyOpenGL** using the **GLUT** toolkit. Players take on the role of an infiltrator tasked with stealing valuables from a heavily guarded vault facility and escaping before time runs out.
 
## Features
 
- 3D stealth-based gameplay
- Collect valuables and reach the extraction point before the timer expires
- Patrol guards with dynamic AI behaviour
- Rotating security cameras
- Timed laser tripwire system
- Suspicion and detection mechanics
- Noise-based stealth interactions
- Countdown timer and mission objectives
 
## Gameplay
 
Unlike traditional action games, Vault Runner provides **no weapons**. Success depends entirely on:
 
- Strategic movement
- Timing and positioning
- Avoiding enemy vision
- Managing noise levels
- Reading patrol patterns
 
Players must collect all required valuables while remaining undetected and then reach the extraction door before the countdown reaches zero.
 
## Guard AI System
 
The game's core mechanic is a four-state guard AI system:
 
1. **Patrol** – Guards follow predefined routes.
2. **Suspicious** – Guards become alerted by unusual activity.
3. **Investigate** – Guards move to the last known location of the disturbance.
4. **Search/Alert** – Guards actively search for the player and can call for backup.
 
Detection is implemented using:
 
- Vision cone geometry
- Dot-product based angle checks
- Distance validation
- Line-of-sight style behaviour
 
This creates dynamic and emergent stealth gameplay where guards react intelligently to player actions.
 
## Technologies Used
 
- Python
- PyOpenGL
- GLUT (OpenGL Utility Toolkit)
- Object-Oriented Programming
- Vector Mathematics
- State Machine AI
 
## Controls
 
| Key | Action |
|------|---------|
| W/A/S/D | Move |
| Mouse | Look Around |
| Shift | Sprint |
| E | Interact / Collect |
| Esc | Pause / Exit |
 
*(Update controls according to your implementation.)*
 
## Project Structure
 
```text
Vault_Runner/
│
├── assets/
├── textures/
├── models/
├── sounds/
├── src/
│ ├── player.py
│ ├── guard.py
│ ├── camera.py
│ ├── world.py
│ └── main.py
│
├── screenshots/
└── README.md
```
 
## Learning Objectives
 
This project demonstrates:
 
- Real-time 3D rendering with OpenGL
- AI state machine implementation
- Geometric visibility detection
- Event-driven game programming
- Interactive gameplay design
- Stealth game mechanics
 
 
## Future Improvements
 
- Multiple levels
- Improved pathfinding
- Dynamic lighting and shadows
- Save/load system
- Difficulty modes
- Sound propagation system
 
## Authors
 
Developed as part of **CSE423: Computer Graphics**.
 
---
 
**Vault Runner** transforms the traditional action game formula into a pure stealth experience where observation, patience, and strategy are the player's only weapons.
``
