#Vault Runner
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import math
import random
import time


#  SECTION 1 - CONSTANTS

# Camera-related variables 
camera_pos = (0, 500, 500)

fovY = 100                 # Field of view
GRID_LENGTH = 600          # Length of grid lines (floor spans -600 .. +600)
rand_var = 423

WIN_W, WIN_H = 1000, 800

#  level geometry 
CELL = 400                 # size of one room cell
ROOMS = 3                  # facility is ROOMS x ROOMS cells
WALL_H = 130               # height of every wall
WALL_T = 14                # half thickness of a wall
DOOR_HALF = 70             # half width of a doorway gap

#  player 
PLAYER_R = 26              # collision radius
STEP_WALK = 15.0
STEP_CROUCH = 8.0
STEP_SPRINT = 26.0
NOISE_WALK = 210.0
NOISE_CROUCH = 45.0
NOISE_SPRINT = 400.0
MOVE_MEMORY = 0.16         # seconds a keypress counts as "still moving"

#  guards 
GUARD_COUNT = 3
CONE_HALF_ANGLE = 34.0     # half angle of the vision cone in degrees
CONE_RANGE = 340.0         # base sight range
GUARD_SPEED = 78.0
CHASE_SPEED = 132.0
WP_TOLERANCE = 30.0
SUSPICION_MAX = 100.0
SUSPICION_RISE = 96.0      # per second at point blank range
SUSPICION_FALL = 26.0      # per second when unseen
HIDE_FALL_BONUS = 3.0      # decay multiplier while inside a hiding zone
S_SUSPICIOUS = 30.0        # state thresholds
S_ALERT = 70.0
S_CHASE = 100.0
S_CALM = 15.0
SEARCH_TIME = 4.0
CATCH_RADIUS = 46.0

#  security cameras 
CAM_COUNT = 4
CAM_CONE_HALF = 22.0
CAM_RANGE = 300.0
CAM_SWEEP = 55.0           # degrees either side of the base angle
CAM_SPEED = 26.0           # degrees per second

#  lasers 
LASER_ON_RATIO = 0.55      # fraction of each cycle the beam is armed

#  loot 
LOOT_COUNT = 10
TIER_VALUE = {0: 100, 1: 250, 2: 500}
TIER_COLOR = {0: (0.80, 0.49, 0.20),      # bronze
              1: (0.75, 0.78, 0.82),      # silver
              2: (0.95, 0.80, 0.15)}      # gold
TIER_NAME = {0: "Bronze", 1: "Silver", 2: "Gold"}

#  mission 
MISSION_TIME = 210.0
ALARM_MAX = 100.0
ALARM_DECAY = 3.4          # per second
ALARM_T_FAST = 40.0        # guards speed up past this
ALARM_T_RANGE = 70.0       # guards see further past this
OVERLAY_DRAIN = 22.0       # battery units per second while overlay is on
OVERLAY_CHARGE = 9.0       # units per second while it is off

# camera
CAM_MIN_H, CAM_MAX_H = 160.0, 900.0
CAM_ORBIT_R = 520.0


#  SECTION 2 - GAME STATE

quadric = None
last_time = 0.0
anim_time = 0.0

# view
cam_angle = 55.0
cam_height = 430.0
first_person = False

# level containers
walls = []          # {'x1','y1','x2','y2'}
doorways = []       # {'x','y','vertical'}
guards = []
cameras = []
lasers = []
loot = []
hide_zones = []
room_centers = []
sparks = []         # transient particles

# player
player = {}
mission = {}

# input echo for the on screen message line
message = ""
message_timer = 0.0



#  SECTION 3 - SMALL MATH HELPERS


def unit_from_angle(deg):
    """Unit direction vector for an angle given in degrees."""
    r = math.radians(deg)
    return math.cos(r), math.sin(r)


def angle_diff(a, b):
    """Signed smallest difference a - b, wrapped to [-180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


def turn_towards(current, target, max_step):
    """Rotate current towards target by at most max_step degrees."""
    d = angle_diff(target, current)
    if abs(d) <= max_step:
        return target % 360.0
    return (current + max_step * (1.0 if d > 0 else -1.0)) % 360.0


def point_seg_dist(px, py, x1, y1, x2, y2):
    """Shortest distance from a point to a line segment."""
    vx, vy = x2 - x1, y2 - y1
    wx, wy = px - x1, py - y1
    L2 = vx * vx + vy * vy
    if L2 < 1e-9:
        return math.hypot(wx, wy)
    t = (wx * vx + wy * vy) / L2
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))


def _orient(ax, ay, bx, by, cx, cy):
    return (by - ay) * (cx - bx) - (bx - ax) * (cy - by)


def segments_cross(ax, ay, bx, by, cx, cy, dx, dy):
    """True when segment AB properly intersects segment CD."""
    d1 = _orient(ax, ay, bx, by, cx, cy)
    d2 = _orient(ax, ay, bx, by, dx, dy)
    d3 = _orient(cx, cy, dx, dy, ax, ay)
    d4 = _orient(cx, cy, dx, dy, bx, by)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def wall_blocks(x1, y1, x2, y2):
    """F7 - line of sight test. True when any wall interrupts the segment."""
    for w in walls:
        if segments_cross(x1, y1, x2, y2, w['x1'], w['y1'], w['x2'], w['y2']):
            return True
    return False


def blocked_by_wall(px, py, radius):
    """Circle versus wall collision used for player and guard movement."""
    if abs(px) > GRID_LENGTH - radius or abs(py) > GRID_LENGTH - radius:
        return True
    for w in walls:
        if point_seg_dist(px, py, w['x1'], w['y1'], w['x2'], w['y2']) < radius + WALL_T:
            return True
    return False


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)



#  SECTION 4 - F1  PROCEDURAL FACILITY GENERATION


def cell_of(x, y):
    """Return the (col, row) room index containing a world position."""
    c = int((x + GRID_LENGTH) // CELL)
    r = int((y + GRID_LENGTH) // CELL)
    return clamp(c, 0, ROOMS - 1), clamp(r, 0, ROOMS - 1)


def build_walls():
    """
    Generate the facility. Outer boundary plus interior dividers, each
    divider carrying one randomly placed doorway so every room stays
    reachable. Nothing here is hardcoded: all extents derive from
    GRID_LENGTH, CELL and ROOMS.
    """
    global walls, doorways
    walls = []
    doorways = []
    g = GRID_LENGTH

    #  outer boundary (four vertical walls around the floor) 
    walls.append({'x1': -g, 'y1': g, 'x2': g, 'y2': g})
    walls.append({'x1': -g, 'y1': -g, 'x2': g, 'y2': -g})
    walls.append({'x1': g, 'y1': -g, 'x2': g, 'y2': g})
    walls.append({'x1': -g, 'y1': -g, 'x2': -g, 'y2': g})

    #  interior vertical dividers 
    for i in range(1, ROOMS):
        dx = -g + i * CELL
        for r in range(ROOMS):
            y0 = -g + r * CELL
            y1 = y0 + CELL
            gc = random.uniform(y0 + DOOR_HALF + 40, y1 - DOOR_HALF - 40)
            walls.append({'x1': dx, 'y1': y0, 'x2': dx, 'y2': gc - DOOR_HALF})
            walls.append({'x1': dx, 'y1': gc + DOOR_HALF, 'x2': dx, 'y2': y1})
            doorways.append({'x': dx, 'y': gc, 'vertical': True})

    #  interior horizontal dividers 
    for j in range(1, ROOMS):
        dy = -g + j * CELL
        for c in range(ROOMS):
            x0 = -g + c * CELL
            x1 = x0 + CELL
            gc = random.uniform(x0 + DOOR_HALF + 40, x1 - DOOR_HALF - 40)
            walls.append({'x1': x0, 'y1': dy, 'x2': gc - DOOR_HALF, 'y2': dy})
            walls.append({'x1': gc + DOOR_HALF, 'y1': dy, 'x2': x1, 'y2': dy})
            doorways.append({'x': gc, 'y': dy, 'vertical': False})


def rooms_connected():
    """
    Flood fill across room cells, crossing only where a doorway exists.
    Every generated layout should pass; the check guards against a future
    change to the generator silently producing an unreachable room.
    """
    seen = set()
    stack = [(0, 0)]
    while stack:
        c, r = stack.pop()
        if (c, r) in seen:
            continue
        seen.add((c, r))
        cx = -GRID_LENGTH + c * CELL + CELL * 0.5
        cy = -GRID_LENGTH + r * CELL + CELL * 0.5
        for nc, nr in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
            if not (0 <= nc < ROOMS and 0 <= nr < ROOMS) or (nc, nr) in seen:
                continue
            nx = -GRID_LENGTH + nc * CELL + CELL * 0.5
            ny = -GRID_LENGTH + nr * CELL + CELL * 0.5
            if not wall_blocks(cx, cy, nx, ny):
                stack.append((nc, nr))
    return len(seen) == ROOMS * ROOMS


def free_spot_in_room(c, r, margin=90):
    """Random position inside room (c, r) that is clear of walls."""
    x0 = -GRID_LENGTH + c * CELL
    y0 = -GRID_LENGTH + r * CELL
    for _ in range(60):
        x = random.uniform(x0 + margin, x0 + CELL - margin)
        y = random.uniform(y0 + margin, y0 + CELL - margin)
        if not blocked_by_wall(x, y, 42):
            return x, y
    return x0 + CELL * 0.5, y0 + CELL * 0.5


def build_entities():
    """
    Populate the generated facility. Guard waypoints are assigned first so
    that loot tiers and hiding zones can be placed relative to patrol
    density: the most valuable loot goes where guards are thickest.
    """
    global guards, cameras, lasers, loot, hide_zones, room_centers

    room_centers = []
    for r in range(ROOMS):
        for c in range(ROOMS):
            room_centers.append((-GRID_LENGTH + c * CELL + CELL * 0.5,
                                 -GRID_LENGTH + r * CELL + CELL * 0.5, c, r))

    #  F3  guards and their patrol waypoints 
    guards = []
    density = {}
    for i in range(GUARD_COUNT):
        picks = random.sample(room_centers, random.randint(3, 4))
        wps = []
        for (cx, cy, c, r) in picks:
            density[(c, r)] = density.get((c, r), 0) + 1
            wx, wy = free_spot_in_room(c, r, 110)
            wps.append((wx, wy))
        guards.append({
            'x': wps[0][0], 'y': wps[0][1],
            'angle': random.uniform(0, 360),
            'state': 'PATROL',
            'suspicion': 0.0,
            'waypoints': wps,
            'wp': 1 % len(wps),
            'seen_x': 0.0, 'seen_y': 0.0,
            'search': 0.0,
            'lost': 0.0,
            'bob': random.uniform(0, 6.28)
        })

    #  F10  rotating security cameras 
    cameras = []
    cam_rooms = random.sample(room_centers, CAM_COUNT)
    for (cx, cy, c, r) in cam_rooms:
        x, y = free_spot_in_room(c, r, 150)
        cameras.append({
            'x': x, 'y': y,
            'base': random.uniform(0, 360),
            'phase': random.uniform(0, 6.28),
            'angle': 0.0,
            'hot': False
        })

    #  F11  timed laser tripwires 
    lasers = []
    for d in doorways:
        if random.random() < 0.6:
            if d['vertical']:
                seg = (d['x'], d['y'] - DOOR_HALF, d['x'], d['y'] + DOOR_HALF)
            else:
                seg = (d['x'] - DOOR_HALF, d['y'], d['x'] + DOOR_HALF, d['y'])
            lasers.append({
                'x1': seg[0], 'y1': seg[1], 'x2': seg[2], 'y2': seg[3],
                'period': random.uniform(3.0, 6.0),
                'phase': random.uniform(0.0, 6.0),
                'armed': True,
                'cooldown': 0.0
            })

    #  F14  tiered loot 
    # rooms ranked by how many guard waypoints they contain
    ranked = sorted(room_centers,
                    key=lambda rc: -density.get((rc[2], rc[3]), 0))
    loot = []
    for i in range(LOOT_COUNT):
        # the first third of the loot goes into the busiest rooms as gold
        if i < LOOT_COUNT // 3:
            rc = ranked[i % max(1, ROOMS)]
            tier = 2
        elif i < (2 * LOOT_COUNT) // 3:
            rc = random.choice(ranked[ROOMS:2 * ROOMS] or ranked)
            tier = 1
        else:
            rc = random.choice(ranked[-ROOMS:])
            tier = 0
        x, y = free_spot_in_room(rc[2], rc[3], 105)
        loot.append({'x': x, 'y': y, 'tier': tier,
                     'value': TIER_VALUE[tier], 'taken': False,
                     'spin': random.uniform(0, 360), 'pop': 0.0})

    #  F12  hiding zones 
    # placed in the calmest rooms so there is always somewhere to retreat to
    hide_zones = []
    for rc in ranked[-(ROOMS + 1):]:
        x, y = free_spot_in_room(rc[2], rc[3], 120)
        hide_zones.append({'x': x, 'y': y, 'r': 78.0})


def reset_game():
    """
    Full mission reset. Called once at startup and again on every R press so
    that the initial state and the restart state can never diverge.
    """
    global player, mission, sparks, message, message_timer
    global cam_angle, cam_height, first_person

    for _ in range(30):
        build_walls()
        if rooms_connected():
            break
    build_entities()

    # the player always starts in the corner room furthest from the exit
    px, py = free_spot_in_room(0, 0, 110)
    player = {
        'x': px, 'y': py,
        'angle': 45.0,
        'crouch': False,
        'sprint': False,
        'noise': 0.0,
        'value': 0,
        'moving': 0.0,
        'stride': 0.0
    }

    total = sum(l['value'] for l in loot)
    mission = {
        'time': MISSION_TIME,
        'alarm': 0.0,
        'battery': 100.0,
        'overlay': False,
        'paused': False,
        'state': 'RUN',            # RUN | WIN | LOSE
        'reason': '',
        'score': 0,
        'target': int(total * 0.45),
        'exit_x': random.uniform(-CELL * 0.4, CELL * 0.4),
        'exit_y': GRID_LENGTH - 30.0,
        'collected': 0,
        'spotted': 0
    }

    sparks = []
    message = "Mission start. Collect the target value and reach the exit."
    message_timer = 4.0
    cam_angle = 55.0
    cam_height = 430.0
    first_person = False



#  SECTION 5 - LOW LEVEL DRAWING


def draw_text(x, y, text, font=GLUT_BITMAP_HELVETICA_18):
    glColor3f(1, 1, 1)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()

    # Set up an orthographic projection that matches window coordinates
    gluOrtho2D(0, 1000, 0, 800)  # left, right, bottom, top

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    # Draw text at (x, y) in screen coordinates
    glRasterPos2f(x, y)
    for ch in text:
        glutBitmapCharacter(font, ord(ch))

    # Restore original projection and modelview matrices
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


def draw_text_col(x, y, text, r, g, b, font=GLUT_BITMAP_HELVETICA_18):
    """Same as draw_text but with a colour, used for the heads up display."""
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, 1000, 0, 800)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glColor3f(r, g, b)
    glRasterPos2f(x, y)
    for ch in text:
        glutBitmapCharacter(font, ord(ch))
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


# Per face brightness multipliers. With no lighting available this is what
# gives every solid a sense of volume.
FACE_TOP, FACE_BOT = 1.00, 0.42
FACE_PX, FACE_NX = 0.78, 0.60
FACE_PY, FACE_NY = 0.88, 0.52


def box(hx, hy, hz, r, g, b):
    """
    Axis aligned shaded box centred on the current origin, drawn as six
    quads so each face can carry its own brightness (fake directional light).
    """
    glBegin(GL_QUADS)
    glColor3f(r * FACE_TOP, g * FACE_TOP, b * FACE_TOP)
    glVertex3f(-hx, -hy, hz); glVertex3f(hx, -hy, hz)
    glVertex3f(hx, hy, hz);   glVertex3f(-hx, hy, hz)

    glColor3f(r * FACE_BOT, g * FACE_BOT, b * FACE_BOT)
    glVertex3f(-hx, -hy, -hz); glVertex3f(-hx, hy, -hz)
    glVertex3f(hx, hy, -hz);   glVertex3f(hx, -hy, -hz)

    glColor3f(r * FACE_PX, g * FACE_PX, b * FACE_PX)
    glVertex3f(hx, -hy, -hz); glVertex3f(hx, hy, -hz)
    glVertex3f(hx, hy, hz);   glVertex3f(hx, -hy, hz)

    glColor3f(r * FACE_NX, g * FACE_NX, b * FACE_NX)
    glVertex3f(-hx, -hy, -hz); glVertex3f(-hx, -hy, hz)
    glVertex3f(-hx, hy, hz);   glVertex3f(-hx, hy, -hz)

    glColor3f(r * FACE_PY, g * FACE_PY, b * FACE_PY)
    glVertex3f(-hx, hy, -hz); glVertex3f(-hx, hy, hz)
    glVertex3f(hx, hy, hz);   glVertex3f(hx, hy, -hz)

    glColor3f(r * FACE_NY, g * FACE_NY, b * FACE_NY)
    glVertex3f(-hx, -hy, -hz); glVertex3f(hx, -hy, -hz)
    glVertex3f(hx, -hy, hz);   glVertex3f(-hx, -hy, hz)
    glEnd()


def box_at(cx, cy, cz, hx, hy, hz, r, g, b):
    glPushMatrix()
    glTranslatef(cx, cy, cz)
    box(hx, hy, hz, r, g, b)
    glPopMatrix()


def floor_disc(cx, cy, radius, r, g, b, z=1.2, seg=22):
    """A filled ring on the floor plane, built from quads."""
    glBegin(GL_QUADS)
    glColor3f(r, g, b)
    for i in range(seg):
        a0 = 2.0 * math.pi * i / seg
        a1 = 2.0 * math.pi * (i + 1) / seg
        glVertex3f(cx, cy, z)
        glVertex3f(cx + radius * math.cos(a0), cy + radius * math.sin(a0), z)
        glVertex3f(cx + radius * math.cos(a1), cy + radius * math.sin(a1), z)
        glVertex3f(cx, cy, z)
    glEnd()


def floor_ring(cx, cy, radius, thick, r, g, b, z=1.6, seg=30):
    """An outlined ring on the floor plane, used for the noise indicator."""
    glBegin(GL_QUADS)
    glColor3f(r, g, b)
    ri, ro = radius - thick, radius + thick
    for i in range(seg):
        a0 = 2.0 * math.pi * i / seg
        a1 = 2.0 * math.pi * (i + 1) / seg
        glVertex3f(cx + ri * math.cos(a0), cy + ri * math.sin(a0), z)
        glVertex3f(cx + ro * math.cos(a0), cy + ro * math.sin(a0), z)
        glVertex3f(cx + ro * math.cos(a1), cy + ro * math.sin(a1), z)
        glVertex3f(cx + ri * math.cos(a1), cy + ri * math.sin(a1), z)
    glEnd()


def draw_cone(cx, cy, facing, half_angle, rng, r, g, b, z=1.0):
    """
    F5 - the vision cone drawn flat on the floor as a fan of quads. Each
    radial slice is shortened by the first wall it meets so the cone visibly
    stops at cover instead of passing through it.
    """
    seg = 14
    # Each boundary ray is shared by two neighbouring slices, so the edge
    # points are computed once up front rather than twice inside the loop.
    edge = []
    for i in range(seg + 1):
        t = -half_angle + (2.0 * half_angle) * i / seg
        d = ray_len(cx, cy, facing + t, rng)
        a = math.radians(facing + t)
        edge.append((cx + d * math.cos(a), cy + d * math.sin(a)))

    glBegin(GL_QUADS)
    glColor3f(r, g, b)
    for i in range(seg):
        x0, y0 = edge[i]
        x1, y1 = edge[i + 1]
        glVertex3f(cx, cy, z)
        glVertex3f(x0, y0, z)
        glVertex3f(x1, y1, z)
        glVertex3f(cx, cy, z)
    glEnd()


def ray_len(cx, cy, deg, maxlen):
    """Distance from a point to the nearest wall along a direction."""
    ux, uy = unit_from_angle(deg)
    ex, ey = cx + ux * maxlen, cy + uy * maxlen
    best = maxlen
    for w in walls:
        if not segments_cross(cx, cy, ex, ey, w['x1'], w['y1'], w['x2'], w['y2']):
            continue
        # parametric intersection along the ray
        rx, ry = ex - cx, ey - cy
        sx, sy = w['x2'] - w['x1'], w['y2'] - w['y1']
        den = rx * sy - ry * sx
        if abs(den) < 1e-9:
            continue
        t = ((w['x1'] - cx) * sy - (w['y1'] - cy) * sx) / den
        if 0.0 <= t <= 1.0:
            best = min(best, t * maxlen)
    return best



#  SECTION 6 - ENTITY DRAWING


def draw_floor():
    """F1 - the floor is generated with nested loops, never hardcoded."""
    tiles = ROOMS * 4
    step = (2.0 * GRID_LENGTH) / tiles
    glBegin(GL_QUADS)
    for i in range(tiles):
        for j in range(tiles):
            x0 = -GRID_LENGTH + i * step
            y0 = -GRID_LENGTH + j * step
            if (i + j) % 2 == 0:
                glColor3f(0.20, 0.22, 0.27)
            else:
                glColor3f(0.15, 0.17, 0.21)
            glVertex3f(x0, y0, 0)
            glVertex3f(x0 + step, y0, 0)
            glVertex3f(x0 + step, y0 + step, 0)
            glVertex3f(x0, y0 + step, 0)
    glEnd()


def draw_wall(w):
    """One wall segment drawn as a shaded box, plus a lighter cap strip."""
    cx = (w['x1'] + w['x2']) * 0.5
    cy = (w['y1'] + w['y2']) * 0.5
    hx = max(abs(w['x2'] - w['x1']) * 0.5, WALL_T)
    hy = max(abs(w['y2'] - w['y1']) * 0.5, WALL_T)
    box_at(cx, cy, WALL_H * 0.5, hx, hy, WALL_H * 0.5, 0.34, 0.36, 0.44)
    box_at(cx, cy, WALL_H + 4, hx, hy, 4, 0.52, 0.55, 0.64)


def draw_limb(x, y, z, pitch, yaw, radius, length, r, g, b):
    """A cylinder limb rotated into place."""
    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(yaw, 0, 0, 1)
    glRotatef(pitch, 0, 1, 0)
    glColor3f(r, g, b)
    gluCylinder(quadric, radius, radius * 0.86, length, 8, 2)
    glPopMatrix()


def draw_humanoid(x, y, angle, stride, skin, cloth, fallen=False, crouch=False):
    """
    F2 - articulated figure assembled from a sphere, cuboids and cylinders.
    The stride value drives a sine walk cycle, so the legs swing wider when
    moving fast and barely move when crouched or standing still.
    """
    glPushMatrix()
    glTranslatef(x, y, 0)
    glRotatef(angle, 0, 0, 1)

    if fallen:
        glTranslatef(0, 0, 26)
        glRotatef(90, 0, 1, 0)

    squash = 0.72 if crouch else 1.0
    swing = math.sin(stride) * 34.0
    hip = 62.0 * squash

    # legs (cylinders) swinging out of phase
    draw_limb(0, -15, hip, 180 - swing, 0, 11, hip, cloth[0] * 0.6, cloth[1] * 0.6, cloth[2] * 0.6)
    draw_limb(0, 15, hip, 180 + swing, 0, 11, hip, cloth[0] * 0.6, cloth[1] * 0.6, cloth[2] * 0.6)

    # torso (cuboid)
    box_at(0, 0, (hip + 36 * squash), 15, 26, 36 * squash, cloth[0], cloth[1], cloth[2])

    # satchel on the back (cuboid)
    box_at(-19, 0, hip + 34 * squash, 7, 17, 20 * squash,
           cloth[0] * 0.5, cloth[1] * 0.5, cloth[2] * 0.5)

    # arms (cylinders) counter swinging
    sh = hip + 58 * squash
    draw_limb(0, -30, sh, 150 + swing * 0.7, 0, 8, 50, skin[0], skin[1], skin[2])
    draw_limb(0, 30, sh, 150 - swing * 0.7, 0, 8, 50, skin[0], skin[1], skin[2])

    # head (sphere) and a small visor cuboid so facing is readable
    glPushMatrix()
    glTranslatef(0, 0, hip + 88 * squash)
    glColor3f(skin[0], skin[1], skin[2])
    gluSphere(quadric, 17, 12, 10)
    glPopMatrix()
    box_at(13, 0, hip + 90 * squash, 5, 12, 5, 0.09, 0.10, 0.13)

    glPopMatrix()


def guard_colour(g):
    """F4 - the body colour of a guard encodes its AI state."""
    return {
        'PATROL':     (0.20, 0.62, 0.32),
        'SUSPICIOUS': (0.85, 0.76, 0.16),
        'ALERT':      (0.92, 0.52, 0.12),
        'CHASE':      (0.90, 0.16, 0.16)
    }[g['state']]


def draw_guard(g):
    c = guard_colour(g)
    draw_humanoid(g['x'], g['y'], g['angle'], anim_time * 7.0 + g['bob'],
                  (0.92, 0.78, 0.62), c)
    # a suspicion pip floating above the head, height scaled by the meter
    if g['suspicion'] > 4.0:
        h = 236 + 4.0 * math.sin(anim_time * 5.0)
        frac = g['suspicion'] / SUSPICION_MAX
        box_at(g['x'], g['y'], h, 5, 5, 5 + 18 * frac,
               0.95, 0.95 - 0.75 * frac, 0.18)


def draw_camera(cam):
    """F10 - wall mounted sweeping camera: cuboid housing, cylinder lens."""
    glPushMatrix()
    glTranslatef(cam['x'], cam['y'], 118)
    glRotatef(cam['angle'], 0, 0, 1)
    if cam['hot']:
        box(16, 12, 10, 0.90, 0.20, 0.18)
    else:
        box(16, 12, 10, 0.42, 0.44, 0.52)
    glPushMatrix()
    glTranslatef(14, 0, 0)
    glRotatef(90, 0, 1, 0)
    glColor3f(0.12, 0.13, 0.17)
    gluCylinder(quadric, 7, 5, 16, 10, 2)
    glPopMatrix()
    glPopMatrix()
    # mounting post
    box_at(cam['x'], cam['y'], 60, 5, 5, 58, 0.30, 0.32, 0.38)


def draw_laser(lz):
    """F11 - the beam itself plus its two emitter posts."""
    for (ex, ey) in ((lz['x1'], lz['y1']), (lz['x2'], lz['y2'])):
        box_at(ex, ey, 30, 9, 9, 30, 0.28, 0.30, 0.36)
    if lz['armed']:
        cx = (lz['x1'] + lz['x2']) * 0.5
        cy = (lz['y1'] + lz['y2']) * 0.5
        hx = max(abs(lz['x2'] - lz['x1']) * 0.5, 3)
        hy = max(abs(lz['y2'] - lz['y1']) * 0.5, 3)
        pulse = 0.75 + 0.25 * math.sin(anim_time * 12.0)
        box_at(cx, cy, 52, hx, hy, 3, pulse, 0.12, 0.12)


def draw_loot(l):
    """F14 - pedestal plus a spinning tiered prize."""
    r, g, b = TIER_COLOR[l['tier']]
    box_at(l['x'], l['y'], 16, 20, 20, 16, 0.26, 0.27, 0.33)
    glPushMatrix()
    glTranslatef(l['x'], l['y'], 52 + 5 * math.sin(anim_time * 2.4 + l['spin'] * 0.02))
    glRotatef(l['spin'], 0, 0, 1)
    glRotatef(28, 1, 0, 0)
    if l['tier'] == 2:
        glColor3f(r, g, b)
        gluSphere(quadric, 17, 10, 8)
    elif l['tier'] == 1:
        box(15, 15, 15, r, g, b)
    else:
        glColor3f(r, g, b)
        gluCylinder(quadric, 15, 3, 26, 8, 2)
    glPopMatrix()


def draw_exit():
    """F15 - the extraction door, red while locked and green once unlocked."""
    unlocked = player['value'] >= mission['target']
    if unlocked:
        col = (0.16, 0.82, 0.34)
    else:
        col = (0.82, 0.18, 0.18)
    ex, ey = mission['exit_x'], mission['exit_y']
    box_at(ex - 70, ey, 60, 12, 16, 60, col[0], col[1], col[2])
    box_at(ex + 70, ey, 60, 12, 16, 60, col[0], col[1], col[2])
    box_at(ex, ey, 116, 82, 16, 10, col[0], col[1], col[2])
    if not unlocked:
        # the physical barrier is only drawn while the door is sealed
        box_at(ex, ey, 52, 58, 8, 50, 0.46, 0.16, 0.16)


def draw_sparks():
    """Collection particles, drawn with GL_POINTS."""
    if not sparks:
        return
    glPointSize(6)
    glBegin(GL_POINTS)
    for s in sparks:
        glColor3f(s['r'], s['g'], s['b'])
        glVertex3f(s['x'], s['y'], s['z'])
    glEnd()


#  SECTION 7 - DETECTION AND ARTIFICIAL INTELLIGENCE


def in_hide_zone():
    """F12 - true while the player stands inside any hiding zone."""
    for h in hide_zones:
        if math.hypot(player['x'] - h['x'], player['y'] - h['y']) < h['r']:
            return True
    return False


def sees_player(ox, oy, facing, half_angle, rng):
    """
    F5 + F7 - the core detection test.
      1. reject beyond sight range
      2. reject outside the cone using a dot product against the facing vector
      3. reject when a wall interrupts the line of sight
    Returns the distance when detected, otherwise None.
    """
    dx = player['x'] - ox
    dy = player['y'] - oy
    dist = math.hypot(dx, dy)
    if dist > rng or dist < 1e-6:
        return None
    fx, fy = unit_from_angle(facing)
    if (dx / dist) * fx + (dy / dist) * fy < math.cos(math.radians(half_angle)):
        return None
    if wall_blocks(ox, oy, player['x'], player['y']):
        return None
    return dist


def raise_alarm(amount):
    """F13 - push the facility wide alarm level up."""
    mission['alarm'] = clamp(mission['alarm'] + amount, 0.0, ALARM_MAX)


def alert_guards_at(x, y, radius, amount):
    """
    F9 - any guard within the radius gains suspicion and turns to face the
    stimulus. This is how noise reaches guards that cannot see the player.
    """
    for g in guards:
        if math.hypot(g['x'] - x, g['y'] - y) < radius:
            g['suspicion'] = clamp(g['suspicion'] + amount, 0.0, SUSPICION_MAX)
            g['seen_x'], g['seen_y'] = x, y
            if g['state'] == 'PATROL' and g['suspicion'] >= S_SUSPICIOUS:
                g['state'] = 'SUSPICIOUS'


def update_guard(g, dt):
    """F4 + F6 - one guard: detection, suspicion, state machine, movement."""
    hidden = in_hide_zone()

    # alarm level modifies guard capability (F13 thresholds)
    rng = CONE_RANGE * (1.22 if mission['alarm'] >= ALARM_T_RANGE else 1.0)
    spd = GUARD_SPEED * (1.30 if mission['alarm'] >= ALARM_T_FAST else 1.0)

    dist = sees_player(g['x'], g['y'], g['angle'], CONE_HALF_ANGLE, rng)

    # ---- F6 graduated suspicion ----
    if dist is not None and not hidden:
        # closer sightings escalate much faster than distant sightings
        near = 1.0 - (dist / rng)
        rate = SUSPICION_RISE * (0.25 + 0.75 * near)
        if player['crouch']:
            rate *= 0.45
        g['suspicion'] = clamp(g['suspicion'] + rate * dt, 0.0, SUSPICION_MAX)
        g['seen_x'], g['seen_y'] = player['x'], player['y']
        g['lost'] = 0.0
    else:
        fall = SUSPICION_FALL * (HIDE_FALL_BONUS if hidden else 1.0)
        g['suspicion'] = clamp(g['suspicion'] - fall * dt, 0.0, SUSPICION_MAX)
        g['lost'] += dt

    s = g['suspicion']
    st = g['state']

    # ---- F4 state transitions ----
    if st == 'PATROL':
        if s >= S_SUSPICIOUS:
            g['state'] = 'SUSPICIOUS'
    elif st == 'SUSPICIOUS':
        if s >= S_ALERT:
            g['state'] = 'ALERT'
            g['search'] = SEARCH_TIME
        elif s <= S_CALM:
            g['state'] = 'PATROL'
    elif st == 'ALERT':
        if s >= S_CHASE:
            g['state'] = 'CHASE'
        elif g['search'] <= 0.0:
            g['state'] = 'PATROL'
    elif st == 'CHASE':
        if g['lost'] > 2.0:
            g['state'] = 'ALERT'
            g['search'] = SEARCH_TIME

    st = g['state']

    # ---- behaviour per state ----
    if st == 'PATROL':
        tx, ty = g['waypoints'][g['wp']]
        hx, hy = next_hop(g['x'], g['y'], tx, ty)
        step_guard(g, hx, hy, spd, dt)
        if math.hypot(tx - g['x'], ty - g['y']) < WP_TOLERANCE:
            g['wp'] = (g['wp'] + 1) % len(g['waypoints'])

    elif st == 'SUSPICIOUS':
        want = math.degrees(math.atan2(g['seen_y'] - g['y'], g['seen_x'] - g['x']))
        g['angle'] = turn_towards(g['angle'], want, 150.0 * dt)

    elif st == 'ALERT':
        g['search'] -= dt
        d = math.hypot(g['seen_x'] - g['x'], g['seen_y'] - g['y'])
        if d > 40.0:
            hx, hy = next_hop(g['x'], g['y'], g['seen_x'], g['seen_y'])
            step_guard(g, hx, hy, spd * 1.15, dt)
        else:
            # sweep the area while searching
            g['angle'] = (g['angle'] + 95.0 * dt) % 360.0
        raise_alarm(1.6 * dt)

    elif st == 'CHASE':
        hx, hy = next_hop(g['x'], g['y'], player['x'], player['y'])
        step_guard(g, hx, hy, CHASE_SPEED, dt)
        raise_alarm(7.0 * dt)
        if math.hypot(g['x'] - player['x'], g['y'] - player['y']) < CATCH_RADIUS:
            lose("You were caught by a guard.")


def door_between(ca, ra, cb, rb):
    """The doorway joining two adjacent rooms, or None if there is none."""
    for d in doorways:
        if d['vertical']:
            # a vertical divider joins the rooms left and right of it
            c_left = int((d['x'] + GRID_LENGTH) // CELL) - 1
            r = int((d['y'] + GRID_LENGTH) // CELL)
            pair = ((c_left, r), (c_left + 1, r))
        else:
            c = int((d['x'] + GRID_LENGTH) // CELL)
            r_low = int((d['y'] + GRID_LENGTH) // CELL) - 1
            pair = ((c, r_low), (c, r_low + 1))
        if ((ca, ra), (cb, rb)) == pair or ((cb, rb), (ca, ra)) == pair:
            return d
    return None


def next_hop(gx, gy, tx, ty):
    """
    Route a guard from its room to the target room through doorways.
    Breadth first search over the room grid returns the next room to enter;
    the guard then steers at that room's doorway rather than at the wall.
    Without this a guard walks straight into the divider and jams.
    """
    ca, ra = cell_of(gx, gy)
    cb, rb = cell_of(tx, ty)
    if (ca, ra) == (cb, rb):
        return tx, ty

    prev = {(ca, ra): None}
    queue = [(ca, ra)]
    head = 0
    while head < len(queue):
        cur = queue[head]; head += 1
        if cur == (cb, rb):
            break
        c, r = cur
        for nb in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
            if not (0 <= nb[0] < ROOMS and 0 <= nb[1] < ROOMS) or nb in prev:
                continue
            if door_between(c, r, nb[0], nb[1]) is None:
                continue
            prev[nb] = cur
            queue.append(nb)

    if (cb, rb) not in prev:
        return tx, ty

    # walk the chain back to find the first room after the guard's own
    node = (cb, rb)
    while prev[node] is not None and prev[node] != (ca, ra):
        node = prev[node]
    d = door_between(ca, ra, node[0], node[1])
    if d is None:
        return tx, ty
    return d['x'], d['y']


def step_guard(g, tx, ty, speed, dt):
    """
    Move a guard toward a target, turning to face the direction of travel.
    A simple wall slide keeps guards from sticking on corners.
    """
    dx, dy = tx - g['x'], ty - g['y']
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return
    want = math.degrees(math.atan2(dy, dx))
    g['angle'] = turn_towards(g['angle'], want, 220.0 * dt)

    ux, uy = dx / d, dy / d
    nx = g['x'] + ux * speed * dt
    ny = g['y'] + uy * speed * dt
    if not blocked_by_wall(nx, ny, 24):
        g['x'], g['y'] = nx, ny
    elif not blocked_by_wall(nx, g['y'], 24):
        g['x'] = nx
    elif not blocked_by_wall(g['x'], ny, 24):
        g['y'] = ny


def update_cameras(dt):
    """F10 - sweeping cameras raise the alarm and mark the player position."""
    for cam in cameras:
        cam['phase'] += dt
        cam['angle'] = cam['base'] + CAM_SWEEP * math.sin(
            math.radians(cam['phase'] * CAM_SPEED))
        hit = sees_player(cam['x'], cam['y'], cam['angle'],
                          CAM_CONE_HALF, CAM_RANGE)
        cam['hot'] = hit is not None and not in_hide_zone()
        if cam['hot']:
            raise_alarm(11.0 * dt)
            alert_guards_at(player['x'], player['y'], 460.0, 34.0 * dt)


def update_lasers(dt):
    """F11 - each emitter cycles on its own period and phase."""
    for lz in lasers:
        lz['phase'] += dt
        cycle = (lz['phase'] % lz['period']) / lz['period']
        lz['armed'] = cycle < LASER_ON_RATIO
        if lz['cooldown'] > 0.0:
            lz['cooldown'] -= dt
            continue
        if not lz['armed']:
            continue
        d = point_seg_dist(player['x'], player['y'],
                           lz['x1'], lz['y1'], lz['x2'], lz['y2'])
        if d < PLAYER_R:
            lz['cooldown'] = 2.5
            raise_alarm(20.0)
            alert_guards_at(player['x'], player['y'], 620.0, 55.0)
            mission['spotted'] += 1
            say("Tripwire triggered. Guards alerted.", 2.4)


def update_noise(dt):
    """F9 - movement noise, drawn as a ring and heard by nearby guards."""
    if player['moving'] > 0.0:
        if player['crouch']:
            player['noise'] = NOISE_CROUCH
        elif player['sprint']:
            player['noise'] = NOISE_SPRINT
        else:
            player['noise'] = NOISE_WALK
        alert_guards_at(player['x'], player['y'], player['noise'], 26.0 * dt)
    else:
        player['noise'] = max(0.0, player['noise'] - 420.0 * dt)



#  SECTION 8 - MISSION SYSTEMS


def say(text, seconds=2.2):
    global message, message_timer
    message = text
    message_timer = seconds


def lose(reason):
    if mission['state'] == 'RUN':
        mission['state'] = 'LOSE'
        mission['reason'] = reason
        mission['score'] = player['value'] // 2


def win():
    if mission['state'] == 'RUN':
        mission['state'] = 'WIN'
        bonus = int(mission['time'] * 12)
        mission['score'] = player['value'] + bonus
        mission['reason'] = "Extraction successful. Time bonus " + str(bonus) + "."


def spawn_sparks(x, y, col):
    for _ in range(16):
        sparks.append({
            'x': x, 'y': y, 'z': 55.0,
            'vx': random.uniform(-60, 60),
            'vy': random.uniform(-60, 60),
            'vz': random.uniform(40, 130),
            'life': random.uniform(0.4, 0.9),
            'r': col[0], 'g': col[1], 'b': col[2]
        })


def update_sparks(dt):
    for s in list(sparks):
        s['life'] -= dt
        if s['life'] <= 0.0:
            sparks.remove(s)
            continue
        s['x'] += s['vx'] * dt
        s['y'] += s['vy'] * dt
        s['z'] += s['vz'] * dt
        s['vz'] -= 260.0 * dt


def try_collect():
    """F14 - collect the nearest loot within reach."""
    for l in loot:
        if l['taken']:
            continue
        if math.hypot(player['x'] - l['x'], player['y'] - l['y']) < 62.0:
            l['taken'] = True
            player['value'] += l['value']
            mission['collected'] += 1
            spawn_sparks(l['x'], l['y'], TIER_COLOR[l['tier']])
            # lifting an item off its pedestal makes a small sound
            alert_guards_at(l['x'], l['y'], 190.0, 16.0)
            say(TIER_NAME[l['tier']] + " secured. Total " + str(player['value']), 2.0)
            return
    say("Nothing within reach.", 1.4)


def try_exit():
    """F15 - extraction only succeeds once the target value is carried."""
    d = math.hypot(player['x'] - mission['exit_x'], player['y'] - mission['exit_y'])
    if d > 110.0:
        return False
    if player['value'] >= mission['target']:
        win()
    else:
        need = mission['target'] - player['value']
        say("Door sealed. " + str(need) + " more in value required.", 2.4)
    return True


def move_player(sign):
    """W and S. A discrete step per key event, since key release callbacks
    are not available in the template."""
    if mission['state'] != 'RUN' or mission['paused']:
        return
    if player['crouch']:
        step = STEP_CROUCH
    elif player['sprint']:
        step = STEP_SPRINT
    else:
        step = STEP_WALK
    ux, uy = unit_from_angle(player['angle'])
    nx = player['x'] + ux * step * sign
    ny = player['y'] + uy * step * sign
    if not blocked_by_wall(nx, ny, PLAYER_R):
        player['x'], player['y'] = nx, ny
    elif not blocked_by_wall(nx, player['y'], PLAYER_R):
        player['x'] = nx
    elif not blocked_by_wall(player['x'], ny, PLAYER_R):
        player['y'] = ny
    player['moving'] = MOVE_MEMORY
    player['stride'] += 0.55 if not player['crouch'] else 0.3


#  SECTION 9 - MAIN UPDATE


def update_game(dt):
    global message_timer

    if message_timer > 0.0:
        message_timer -= dt

    update_sparks(dt)

    if mission['state'] != 'RUN' or mission['paused']:
        return

    # F16 mission countdown
    mission['time'] -= dt
    if mission['time'] <= 0.0:
        mission['time'] = 0.0
        lose("The mission timer expired.")
        return

    # F18 overlay battery
    if mission['overlay']:
        mission['battery'] -= OVERLAY_DRAIN * dt
        if mission['battery'] <= 0.0:
            mission['battery'] = 0.0
            mission['overlay'] = False
            say("Overlay battery depleted.", 2.0)
    else:
        mission['battery'] = clamp(mission['battery'] + OVERLAY_CHARGE * dt,
                                   0.0, 100.0)

    player['moving'] = max(0.0, player['moving'] - dt)

    update_noise(dt)
    update_lasers(dt)
    update_cameras(dt)

    prev_chasers = sum(1 for g in guards if g['state'] == 'CHASE')
    for g in guards:
        update_guard(g, dt)
    now_chasers = sum(1 for g in guards if g['state'] == 'CHASE')
    if now_chasers > prev_chasers:
        mission['spotted'] += 1
        say("Spotted. Break line of sight.", 2.0)

    # F13 - the lockdown test must run BEFORE decay. If decay were applied
    # first, an alarm sitting exactly at the maximum would be pulled just
    # below the threshold in the same frame and the run would never end.
    if mission['alarm'] >= ALARM_MAX:
        lose("Facility lockdown. The alarm reached maximum.")
        return
    if now_chasers == 0:
        mission['alarm'] = max(0.0, mission['alarm'] - ALARM_DECAY * dt)

    # loot spin animation
    for l in loot:
        if not l['taken']:
            l['spin'] = (l['spin'] + 52.0 * dt) % 360.0


def idle():
    """
    Idle function that runs continuously:
    - Measures elapsed time from the system clock (no GLUT timer is used)
    - Advances the simulation
    - Triggers screen redraw for real-time updates.
    """
    global last_time, anim_time

    now = time.time()
    dt = now - last_time
    last_time = now
    if dt > 0.05:
        dt = 0.05
    if dt < 0.0:
        dt = 0.0
    anim_time += dt

    update_game(dt)
    glutPostRedisplay()


#  SECTION 10 - CAMERA (F17)


def get_cam_pos():
    """The eye position for the current camera mode, also used for sorting."""
    if first_person:
        ux, uy = unit_from_angle(player['angle'])
        h = 118.0 if player['crouch'] else 150.0
        return (player['x'] + ux * 18.0, player['y'] + uy * 18.0, h)
    r = math.radians(cam_angle)
    return (player['x'] + CAM_ORBIT_R * math.cos(r),
            player['y'] + CAM_ORBIT_R * math.sin(r),
            cam_height)


def setupCamera():
    """
    Configures the camera's projection and view settings.
    Uses a perspective projection and positions the camera to look at the target.
    """
    glMatrixMode(GL_PROJECTION)  # Switch to projection matrix mode
    glLoadIdentity()  # Reset the projection matrix
    # Set up a perspective projection (field of view, aspect ratio, near clip, far clip)
    gluPerspective(fovY, 1.25, 0.1, 4000)
    glMatrixMode(GL_MODELVIEW)  # Switch to model-view matrix mode
    glLoadIdentity()  # Reset the model-view matrix

    ex, ey, ez = get_cam_pos()
    if first_person:
        ux, uy = unit_from_angle(player['angle'])
        gluLookAt(ex, ey, ez,
                  ex + ux * 300.0, ey + uy * 300.0, ez - 34.0,
                  0, 0, 1)
    else:
        gluLookAt(ex, ey, ez,
                  player['x'], player['y'], 60.0,
                  0, 0, 1)



#  SECTION 11 - HEADS UP DISPLAY AND TACTICAL OVERLAY


def hud_begin():
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, 1000, 0, 800)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()


def hud_end():
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


def hud_quad(x, y, w, h, r, g, b):
    glColor3f(r, g, b)
    glBegin(GL_QUADS)
    glVertex3f(x, y, 0)
    glVertex3f(x + w, y, 0)
    glVertex3f(x + w, y + h, 0)
    glVertex3f(x, y + h, 0)
    glEnd()


def hud_bar(x, y, w, h, frac, r, g, b):
    hud_quad(x - 2, y - 2, w + 4, h + 4, 0.12, 0.13, 0.17)
    hud_quad(x, y, w, h, 0.24, 0.26, 0.32)
    hud_quad(x, y, w * clamp(frac, 0.0, 1.0), h, r, g, b)


def draw_hud():
    """All bars and panels for the heads up display."""
    hud_begin()

    # alarm meter (F13)
    a = mission['alarm'] / ALARM_MAX
    if a < 0.4:
        col = (0.25, 0.78, 0.35)
    elif a < 0.7:
        col = (0.92, 0.76, 0.16)
    else:
        col = (0.92, 0.22, 0.18)
    hud_bar(120, 762, 220, 14, a, col[0], col[1], col[2])

    # loot progress toward the extraction threshold (F15)
    p = player['value'] / float(max(1, mission['target']))
    hud_bar(120, 736, 220, 14, p, 0.95, 0.80, 0.15)

    # overlay battery (F18)
    hud_bar(120, 710, 220, 14, mission['battery'] / 100.0, 0.30, 0.70, 0.95)

    hud_end()

    draw_text_col(14, 760, "ALARM", 0.85, 0.85, 0.90)
    draw_text_col(14, 734, "LOOT", 0.85, 0.85, 0.90)
    draw_text_col(14, 708, "SCAN", 0.85, 0.85, 0.90)

    draw_text_col(352, 760, str(int(mission['alarm'])) + " / 100",
                  0.85, 0.85, 0.90)
    draw_text_col(352, 734, str(player['value']) + " / " + str(mission['target']),
                  0.85, 0.85, 0.90)
    draw_text_col(352, 708, str(int(mission['battery'])) + "%", 0.85, 0.85, 0.90)

    # timer (F16), turning red in the closing seconds
    t = int(mission['time'])
    if mission['time'] < 30.0:
        tc = (0.95, 0.25, 0.20)
    else:
        tc = (0.90, 0.92, 0.96)
    draw_text_col(830, 760, "TIME  " + str(t // 60) + ":" + ("%02d" % (t % 60)),
                  tc[0], tc[1], tc[2])

    # movement state (F8)
    if player['crouch']:
        draw_text_col(830, 734, "CROUCHED", 0.35, 0.85, 0.95)
    elif player['sprint']:
        draw_text_col(830, 734, "SPRINTING", 0.95, 0.55, 0.20)
    else:
        draw_text_col(830, 734, "WALKING", 0.75, 0.78, 0.84)

    if in_hide_zone():
        draw_text_col(830, 710, "CONCEALED", 0.30, 0.90, 0.45)

    draw_text_col(830, 686, "LOOT " + str(mission['collected']) + " / " +
                  str(len(loot)), 0.80, 0.82, 0.88)

    # guard state readout
    counts = {'PATROL': 0, 'SUSPICIOUS': 0, 'ALERT': 0, 'CHASE': 0}
    for g in guards:
        counts[g['state']] += 1
    draw_text_col(14, 30, "GUARDS   patrol " + str(counts['PATROL']) +
                  "   suspicious " + str(counts['SUSPICIOUS']) +
                  "   alert " + str(counts['ALERT']) +
                  "   chase " + str(counts['CHASE']),
                  0.72, 0.75, 0.82)

    draw_text_col(14, 8, "W/S move   A/D turn   C crouch   SPACE sprint   "
                         "E collect   F use door   V scan   P pause   R restart",
                  0.52, 0.55, 0.62)

    if message_timer > 0.0:
        draw_text_col(300, 60, message, 0.95, 0.92, 0.60)

    if mission['paused']:
        draw_text_col(430, 420, "PAUSED", 1.0, 1.0, 1.0)

    if mission['state'] == 'WIN':
        draw_text_col(330, 460, "EXTRACTION SUCCESSFUL", 0.30, 0.95, 0.45)
        draw_text_col(330, 430, mission['reason'], 0.85, 0.90, 0.85)
        draw_text_col(330, 400, "Final score: " + str(mission['score']),
                      1.0, 1.0, 1.0)
        draw_text_col(330, 370, "Press R to run a new facility.", 0.8, 0.8, 0.9)
    elif mission['state'] == 'LOSE':
        draw_text_col(360, 460, "MISSION FAILED", 0.95, 0.28, 0.24)
        draw_text_col(330, 430, mission['reason'], 0.90, 0.80, 0.80)
        draw_text_col(330, 400, "Loot secured: " + str(player['value']) +
                      "   Score: " + str(mission['score']), 1.0, 1.0, 1.0)
        draw_text_col(330, 370, "Press R to run a new facility.", 0.8, 0.8, 0.9)


def draw_overlay():
    """
    F18 - orthographic tactical map in the screen corner. Drawn with the same
    push and pop pattern the template uses for text.
    """
    if not mission['overlay']:
        return
    ox, oy, size = 700, 60, 280
    scale = size / (2.0 * GRID_LENGTH)

    def mp(wx, wy):
        return ox + (wx + GRID_LENGTH) * scale, oy + (wy + GRID_LENGTH) * scale

    hud_begin()
    hud_quad(ox - 6, oy - 6, size + 12, size + 12, 0.10, 0.11, 0.15)
    hud_quad(ox, oy, size, size, 0.17, 0.19, 0.24)

    # walls
    glColor3f(0.45, 0.48, 0.58)
    glBegin(GL_QUADS)
    for w in walls:
        ax, ay = mp(w['x1'], w['y1'])
        bx, by = mp(w['x2'], w['y2'])
        if abs(bx - ax) < abs(by - ay):
            ax -= 1.2; bx += 1.2
        else:
            ay -= 1.2; by += 1.2
        glVertex3f(ax, ay, 0); glVertex3f(bx, ay, 0)
        glVertex3f(bx, by, 0); glVertex3f(ax, by, 0)
    glEnd()

    def blip(wx, wy, s, r, g, b):
        mx, my = mp(wx, wy)
        hud_quad(mx - s, my - s, s * 2, s * 2, r, g, b)

    for h in hide_zones:
        blip(h['x'], h['y'], 5, 0.20, 0.55, 0.40)
    for l in loot:
        if not l['taken']:
            c = TIER_COLOR[l['tier']]
            blip(l['x'], l['y'], 3.5, c[0], c[1], c[2])
    for cam in cameras:
        blip(cam['x'], cam['y'], 3, 0.55, 0.60, 0.72)
    for g in guards:
        c = guard_colour(g)
        blip(g['x'], g['y'], 4, c[0], c[1], c[2])
        # short facing tick so patrol direction is readable
        ux, uy = unit_from_angle(g['angle'])
        blip(g['x'] + ux * 55, g['y'] + uy * 55, 2, c[0], c[1], c[2])

    if player['value'] >= mission['target']:
        blip(mission['exit_x'], mission['exit_y'], 6, 0.20, 0.90, 0.35)
    else:
        blip(mission['exit_x'], mission['exit_y'], 6, 0.85, 0.25, 0.25)
    blip(player['x'], player['y'], 4.5, 0.30, 0.75, 1.0)

    hud_end()
    draw_text_col(ox, oy + size + 12, "TACTICAL SCAN", 0.55, 0.80, 0.95)


#  SECTION 12 - SCENE ASSEMBLY (PAINTER'S ALGORITHM)


def draw_floor_decals():
    """
    Everything that lives flat on the floor plane. Drawn immediately after
    the floor and before any solid, so ordering among these is fixed and
    they never need to enter the depth sort.
    """
    # F12 hiding zones
    for h in hide_zones:
        floor_disc(h['x'], h['y'], h['r'], 0.13, 0.34, 0.26)
        floor_ring(h['x'], h['y'], h['r'], 3.0, 0.22, 0.62, 0.45, z=1.4)

    # extraction pad
    if player['value'] >= mission['target']:
        floor_disc(mission['exit_x'], mission['exit_y'] - 40, 86,
                   0.12, 0.38, 0.20)
    else:
        floor_disc(mission['exit_x'], mission['exit_y'] - 40, 86,
                   0.34, 0.13, 0.13)

    # F5 vision cones for guards
    for g in guards:
        rng = CONE_RANGE * (1.22 if mission['alarm'] >= ALARM_T_RANGE else 1.0)
        if g['state'] == 'CHASE':
            c = (0.46, 0.10, 0.10)
        elif g['state'] == 'ALERT':
            c = (0.44, 0.24, 0.07)
        elif g['state'] == 'SUSPICIOUS':
            c = (0.42, 0.38, 0.10)
        else:
            c = (0.30, 0.31, 0.14)
        draw_cone(g['x'], g['y'], g['angle'], CONE_HALF_ANGLE, rng,
                  c[0], c[1], c[2], z=1.0)

    # F10 camera cones
    for cam in cameras:
        if cam['hot']:
            c = (0.48, 0.12, 0.12)
        else:
            c = (0.18, 0.26, 0.36)
        draw_cone(cam['x'], cam['y'], cam['angle'], CAM_CONE_HALF,
                  CAM_RANGE, c[0], c[1], c[2], z=1.1)

    # F9 noise ring
    if player['noise'] > 8.0:
        floor_ring(player['x'], player['y'], player['noise'], 3.5,
                   0.30, 0.62, 0.85, z=1.8)


def collect_solids():
    """
    Build the list of solid objects with their squared distance from the
    camera. Squared distance is enough for ordering and avoids the cost of
    a square root per object.
    """
    ex, ey, ez = get_cam_pos()
    items = []

    def add(x, y, z, fn):
        dx, dy, dz = x - ex, y - ey, z - ez
        items.append((dx * dx + dy * dy + dz * dz, fn))

    for w in walls:
        cx = (w['x1'] + w['x2']) * 0.5
        cy = (w['y1'] + w['y2']) * 0.5
        add(cx, cy, WALL_H * 0.5, (lambda ww: lambda: draw_wall(ww))(w))

    for lz in lasers:
        cx = (lz['x1'] + lz['x2']) * 0.5
        cy = (lz['y1'] + lz['y2']) * 0.5
        add(cx, cy, 40, (lambda l: lambda: draw_laser(l))(lz))

    for l in loot:
        if not l['taken']:
            add(l['x'], l['y'], 50, (lambda ll: lambda: draw_loot(ll))(l))

    for cam in cameras:
        add(cam['x'], cam['y'], 110, (lambda cc: lambda: draw_camera(cc))(cam))

    for g in guards:
        add(g['x'], g['y'], 90, (lambda gg: lambda: draw_guard(gg))(g))

    add(mission['exit_x'], mission['exit_y'], 80, draw_exit)

    if not first_person:
        add(player['x'], player['y'], 90, draw_player)

    return items


def draw_player():
    """F2 + F8 - the infiltrator, lying down once the mission is lost."""
    fallen = (mission['state'] == 'LOSE')
    draw_humanoid(player['x'], player['y'], player['angle'],
                  player['stride'], (0.94, 0.80, 0.64),
                  (0.16, 0.26, 0.52), fallen=fallen,
                  crouch=player['crouch'])


def showScreen():
    """
    Display function to render the game scene:
    - Clears the screen and sets up the camera.
    - Draws everything of the screen
    """
    # Clear color and depth buffers
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glLoadIdentity()  # Reset modelview matrix
    glViewport(0, 0, WIN_W, WIN_H)  # Set viewport size

    setupCamera()  # Configure camera perspective

    # 1. the static base layer, always behind everything else
    draw_floor()
    draw_floor_decals()

    # 2. solids, sorted far to near (painter's algorithm stands in for the
    #    depth test, which is not available in the permitted API)
    solids = collect_solids()
    solids.sort(key=lambda pair: pair[0], reverse=True)
    for _, fn in solids:
        fn()

    # 3. particles and the two dimensional layers on top
    draw_sparks()
    draw_hud()
    draw_overlay()

    # Swap buffers for smooth rendering (double buffering)
    glutSwapBuffers()


#  SECTION 13 - INPUT


def keyboardListener(key, x, y):
    """
    Handles keyboard inputs for player movement, crouch and sprint, loot
    collection, the tactical overlay, pause and restart.
    """
    global message_timer

    # Reset the mission if R key is pressed
    if key == b'r' or key == b'R':
        reset_game()
        glutPostRedisplay()
        return

    # Pause and resume (P key)
    if key == b'p' or key == b'P':
        mission['paused'] = not mission['paused']
        glutPostRedisplay()
        return

    if mission['state'] != 'RUN':
        return

    # Move forward (W key)
    if key == b'w' or key == b'W':
        move_player(1.0)

    # Move backward (S key)
    if key == b's' or key == b'S':
        move_player(-1.0)

    # Rotate left (A key)
    if key == b'a' or key == b'A':
        if not mission['paused']:
            player['angle'] = (player['angle'] + 6.0) % 360.0

    # Rotate right (D key)
    if key == b'd' or key == b'D':
        if not mission['paused']:
            player['angle'] = (player['angle'] - 6.0) % 360.0

    # Toggle crouch (C key). SHIFT cannot be used because modifier key
    # queries are not part of the permitted template API.
    if key == b'c' or key == b'C':
        player['crouch'] = not player['crouch']
        if player['crouch']:
            player['sprint'] = False
        say("Crouched." if player['crouch'] else "Standing.", 1.2)

    # Toggle sprint (SPACE)
    if key == b' ':
        player['sprint'] = not player['sprint']
        if player['sprint']:
            player['crouch'] = False
        say("Sprinting. This is loud." if player['sprint'] else "Walking.", 1.4)

    # Collect loot (E key)
    if key == b'e' or key == b'E':
        try_collect()

    # Use the extraction door (F key)
    if key == b'f' or key == b'F':
        if not try_exit():
            say("No door within reach.", 1.4)

    # Toggle the tactical overlay (V key)
    if key == b'v' or key == b'V':
        if mission['overlay']:
            mission['overlay'] = False
        elif mission['battery'] > 8.0:
            mission['overlay'] = True
        else:
            say("Scanner battery too low.", 1.6)

    glutPostRedisplay()


def specialKeyListener(key, x, y):
    """
    Handles special key inputs (arrow keys) for adjusting the camera angle and height.
    """
    global camera_pos, cam_angle, cam_height
    x, y, z = camera_pos

    # Move camera up (UP arrow key)
    if key == GLUT_KEY_UP:
        cam_height = clamp(cam_height + 24.0, CAM_MIN_H, CAM_MAX_H)

    # Move camera down (DOWN arrow key)
    if key == GLUT_KEY_DOWN:
        cam_height = clamp(cam_height - 24.0, CAM_MIN_H, CAM_MAX_H)

    # moving camera left (LEFT arrow key)
    if key == GLUT_KEY_LEFT:
        cam_angle = (cam_angle - 3.5) % 360.0  # Small angle decrement for smooth movement

    # moving camera right (RIGHT arrow key)
    if key == GLUT_KEY_RIGHT:
        cam_angle = (cam_angle + 3.5) % 360.0  # Small angle increment for smooth movement

    camera_pos = get_cam_pos()
    glutPostRedisplay()


def mouseListener(button, state, x, y):
    """
    Handles mouse inputs: left click interacts with whatever is in reach,
    right click toggles between the first and third person cameras.
    """
    global first_person

    # Left mouse button interacts (door first, otherwise loot)
    if button == GLUT_LEFT_BUTTON and state == GLUT_DOWN:
        if mission['state'] == 'RUN' and not mission['paused']:
            if not try_exit():
                try_collect()

    # Right mouse button toggles camera tracking mode
    if button == GLUT_RIGHT_BUTTON and state == GLUT_DOWN:
        first_person = not first_person
        say("First person view." if first_person else "Third person view.", 1.4)

    glutPostRedisplay()


#  SECTION 14 - ENTRY POINT


def main():
    global quadric, last_time

    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)  # Double buffering, RGB color, depth test
    glutInitWindowSize(WIN_W, WIN_H)  # Window size
    glutInitWindowPosition(0, 0)  # Window position
    wind = glutCreateWindow(b"Vault Runner - 3D Stealth Heist")  # Create the window

    quadric = gluNewQuadric()
    reset_game()
    last_time = time.time()

    glutDisplayFunc(showScreen)  # Register display function
    glutKeyboardFunc(keyboardListener)  # Register keyboard listener
    glutSpecialFunc(specialKeyListener)
    glutMouseFunc(mouseListener)
    glutIdleFunc(idle)  # Register the idle function for continuous updates

    glutMainLoop()  # Enter the GLUT main loop


if __name__ == "__main__":
    main()
