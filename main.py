import os
import math
import random
import wave
import struct
from pathlib import Path

WIDTH = 640
HEIGHT = 480
CELL = 48
GRID_W = WIDTH // CELL
GRID_H = HEIGHT // CELL


# Ensure resource folders exist
Path("sounds").mkdir(exist_ok=True)
Path("music").mkdir(exist_ok=True)

def synth_wav(path, freq=440.0, duration=0.5, volume=0.2):
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            t = i / sample_rate
            value = int(volume * 32767.0 * math.sin(2.0 * math.pi * freq * t))
            data = struct.pack('<h', value)
            wf.writeframesraw(data)


# create small sound files if missing
if not os.path.exists('music/bg.wav'):
    synth_wav('music/bg.wav', freq=220.0, duration=3.0, volume=0.08)
if not os.path.exists('sounds/sfx.wav'):
    synth_wav('sounds/sfx.wav', freq=880.0, duration=0.15, volume=0.2)

try:
    from pygame import Rect
except Exception:
    Rect = None
try:
    import pygame
except Exception:
    pygame = None

# Try to load kenney tiles and parse sampleMap.tmx (if the user added the pack)
KENNEY_DIR = os.path.join(os.getcwd(), 'kenney_tiny-dungeon')
KENNEY_TILES_DIR = os.path.join(KENNEY_DIR, 'Tiles')
TMX_PATH = os.path.join(KENNEY_DIR, 'Tiled', 'sampleMap.tmx')
have_kenney = False
tile_cache = {}
map_data = None
map_tilewidth = 16
map_tileheight = 16
map_width = GRID_W
map_height = GRID_H
floor_gids = set()
explicit_floor_indices = [42, 48, 49, 50, 51, 52, 53]
explicit_floor_gids = set()

import xml.etree.ElementTree as ET

def gid_to_tile_index(gid):
    return gid & 0x1FFFFFFF

if pygame is not None and os.path.isdir(KENNEY_TILES_DIR) and os.path.exists(TMX_PATH):
    try:
        tree = ET.parse(TMX_PATH)
        root = tree.getroot()
        map_width = int(root.get('width'))
        map_height = int(root.get('height'))
        map_tilewidth = int(root.get('tilewidth'))
        map_tileheight = int(root.get('tileheight'))

        # read layer named Dungeon
        layer = None
        for lyr in root.findall('layer'):
            if lyr.get('name') == 'Dungeon':
                layer = lyr
                break
        if layer is not None:
            data = layer.find('data').text.strip()
            raw_gids = [int(x) for x in data.replace('\n','').split(',') if x != '']
            # normalize gids to remove flip/rotation bits
            map_data = [gid_to_tile_index(g) for g in raw_gids]

        # determine most common gids (likely floor tiles)
        try:
            from collections import Counter
            counts = Counter([g for g in map_data if g != 0])
            most_common = [g for g, _ in counts.most_common(8)]
            floor_gids = set(most_common)
        except Exception:
            floor_gids = set()
        # Also explicitly treat specific kenney tiles as floor per user request
        try:
            for num in explicit_floor_indices:
                gid = int(num) + 1
                floor_gids.add(gid)
                explicit_floor_gids.add(gid)
        except Exception:
            pass

        # read Objects layer if present
        objects_layer = None
        for lyr in root.findall('layer'):
            if lyr.get('name') == 'Objects':
                objects_layer = lyr
                break
        objects_data = None
        if objects_layer is not None:
            odata = objects_layer.find('data').text.strip()
            raw_objs = [int(x) for x in odata.replace('\n','').split(',') if x != '']
            objects_data = [gid_to_tile_index(g) for g in raw_objs]

        have_kenney = map_data is not None
    except Exception:
        have_kenney = False

# If map was loaded, adjust grid/window size
if have_kenney:
    GRID_W = map_width
    GRID_H = map_height
    WIDTH = GRID_W * CELL
    HEIGHT = GRID_H * CELL

# tile image loader by TMX tile index
def load_tile_image_by_index(index):
    # index is gid_mask (1-based); convert to zero-based file name
    if index <= 0:
        return None
    if index in tile_cache:
        return tile_cache[index]
    fname = f'tile_{index-1:04d}.png'
    path = os.path.join(KENNEY_TILES_DIR, fname)
    if not os.path.exists(path):
        tile_cache[index] = None
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        img = pygame.transform.scale(img, (CELL, CELL))
        tile_cache[index] = img
        return img
    except Exception:
        tile_cache[index] = None
        return None

# load hero/enemy specific sprites from kenney tiles if present
hero_sprite_tile = None
enemy_sprite_tile = None
goal_sprite_tile = None
if have_kenney:
    # user requested specific tiles
    hero_sprite_tile = load_tile_image_by_index(98)  # tile_0097.png -> index 98 (1-based)
    enemy_sprite_tile = load_tile_image_by_index(122)  # tile_0121.png -> index 122 (1-based)
    goal_sprite_tile = load_tile_image_by_index(90)  # tile_0089.png -> index 90 (1-based)

    # determine goal cell from objects_data (first non-zero) if available
    goal_cell = None
    try:
        if objects_data is not None:
            for i, v in enumerate(objects_data):
                if v != 0:
                    gx = i % map_width
                    gy = i // map_width
                    goal_cell = (gx, gy)
                    break
    except Exception:
        goal_cell = None
    if goal_cell is None:
        # fallback to bottom-right corner
        goal_cell = (map_width - 2, map_height - 2)
else:
    goal_cell = (GRID_W - 2, GRID_H - 2)

import pgzrun
from pgzero.actor import Actor
from pgzero.clock import clock
# `sounds` and `music` are available at runtime when using `pgzrun`.
# Do not import `sounds` from `pgzero` as that raises ImportError in some versions.
from pgzero.keyboard import keys


# menu background (load if present)
menu_bg_surf = None
menu_bg_path = os.path.join('images', 'newgamebackground.jpg')
if os.path.exists(menu_bg_path) and pygame is not None:
    try:
        _img = pygame.image.load(menu_bg_path).convert()
        menu_bg_surf = pygame.transform.scale(_img, (WIDTH, HEIGHT))
    except Exception:
        menu_bg_surf = None



class AnimatedEntity:
    def __init__(self, cell_x, cell_y, color_frames_idle, color_frames_move, image_frames_idle=None, image_frames_move=None):
        self.cell_x = cell_x
        self.cell_y = cell_y
        self.x = cell_x * CELL
        self.y = cell_y * CELL
        self.target_x = self.x
        self.target_y = self.y
        self.speed = 180.0  # pixels per second
        self.move_dx = 0
        self.move_dy = 0
        self.frame_index = 0
        self.frame_timer = 0.0
        self.idle_frames = color_frames_idle
        self.move_frames = color_frames_move
        self.image_frames_idle = image_frames_idle or []
        self.image_frames_move = image_frames_move or []
        self.use_images = False
        # determine whether all image frames exist in the images/ folder
        try:
            missing = False
            for name in (self.image_frames_idle + self.image_frames_move):
                if not os.path.exists(os.path.join('images', name + '.png')):
                    missing = True
                    break
            self.use_images = (len(self.image_frames_idle + self.image_frames_move) > 0) and (not missing)
        except Exception:
            self.use_images = False

    @property
    def is_moving(self):
        return (self.x != self.target_x) or (self.y != self.target_y)

    def set_target_cell(self, cx, cy):
        cx = max(0, min(GRID_W - 1, cx))
        cy = max(0, min(GRID_H - 1, cy))
        self.cell_x = cx
        self.cell_y = cy
        self.target_x = cx * CELL
        self.target_y = cy * CELL

    def update(self, dt):
        # move smoothly toward target
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy)
        if dist > 1e-3:
            step = self.speed * dt
            if step >= dist:
                self.x = self.target_x
                self.y = self.target_y
            else:
                self.x += dx / dist * step
                self.y += dy / dist * step

        # animation
        self.frame_timer += dt
        frame_rate = 6.0
        if self.frame_timer >= 1.0 / frame_rate:
            self.frame_timer = 0.0
            self.frame_index = (self.frame_index + 1) % max(1, len(self.move_frames if self.is_moving else self.idle_frames))

    def draw(self, screen):
        if self.use_images and 'Actor' in globals():
            frames = self.image_frames_move if self.is_moving else self.image_frames_idle
            if not frames:
                return
            name = frames[self.frame_index % len(frames)]
            try:
                a = Actor(name)
                a.pos = (int(self.x) + CELL // 2, int(self.y) + CELL // 2)
                a.draw()
                return
            except Exception:
                # fallback to color drawing
                pass

        frames = self.move_frames if self.is_moving else self.idle_frames
        if not frames:
            return
        color = frames[self.frame_index % len(frames)]
        rect = Rect(int(self.x) + 8, int(self.y) + 8, CELL - 16, CELL - 16) if Rect else (int(self.x) + 8, int(self.y) + 8, CELL - 16, CELL - 16)
        # If we have kenney tiles loaded, optionally draw hero/enemy images
        if have_kenney and pygame is not None:
            cls = getattr(self, '__class__', None)
            name = cls.__name__ if cls is not None else ''
            if name == 'Hero' and hero_sprite_tile is not None:
                px = int(self.x) + (CELL - hero_sprite_tile.get_width()) // 2
                py = int(self.y) + (CELL - hero_sprite_tile.get_height()) // 2
                try:
                    screen.surface.blit(hero_sprite_tile, (px, py))
                    return
                except Exception:
                    pass
            if name == 'Enemy' and enemy_sprite_tile is not None:
                px = int(self.x) + (CELL - enemy_sprite_tile.get_width()) // 2
                py = int(self.y) + (CELL - enemy_sprite_tile.get_height()) // 2
                try:
                    screen.surface.blit(enemy_sprite_tile, (px, py))
                    return
                except Exception:
                    pass
        screen.draw.filled_rect(rect, color)


class Hero(AnimatedEntity):
    def __init__(self, cx, cy):
        idle = [(200, 60, 60), (220, 80, 80)]
        move = [(255, 80, 80), (200, 40, 40), (255, 80, 80), (180, 30, 30)]
        image_idle = ['hero_idle_1', 'hero_idle_2']
        image_move = ['hero_move_1', 'hero_move_2']
        super().__init__(cx, cy, idle, move, image_idle, image_move)
        self.hp = 5

    def set_target_cell(self, cx, cy):
        # prevent walking through walls when TMX floor info is available
        cx = max(0, min(GRID_W - 1, cx))
        cy = max(0, min(GRID_H - 1, cy))
        try:
            if have_kenney and map_data is not None and floor_gids:
                idx = map_data[cy * GRID_W + cx]
                if idx not in floor_gids:
                    return
        except Exception:
            pass
        super().set_target_cell(cx, cy)


class Enemy(AnimatedEntity):
    def __init__(self, cx, cy, territory_w=3, territory_h=3, persistent=False, visible_duration=8.0, chase_time=1.0):
        idle = [(60, 60, 200), (80, 80, 220)]
        move = [(80, 80, 255), (40, 40, 200)]
        image_idle = ['enemy_idle_1']
        image_move = []
        super().__init__(cx, cy, idle, move, image_idle, image_move)
        self.territory = (max(0, cx - territory_w//2), max(0, cy - territory_h//2), territory_w, territory_h)
        self.choose_new_target()
        self.persistent = persistent
        self.visible_timer = 0.0
        self.visible_duration = visible_duration
        self.chase_time = chase_time
        self.chase_remaining = chase_time
        self.dead = False

    def choose_new_target(self):
        tx = random.randint(self.territory[0], min(GRID_W-1, self.territory[0] + self.territory[2] - 1))
        ty = random.randint(self.territory[1], min(GRID_H-1, self.territory[1] + self.territory[3] - 1))
        self.set_target_cell(tx, ty)

    def update(self, dt):
        # If not persistent, increment visibility timer and handle chase -> disappear
        if not self.persistent:
            self.visible_timer += dt
            # chase hero for the first `chase_time` seconds
            if self.chase_remaining > 0:
                self.chase_remaining -= dt
                # set target to hero cell to move toward hero
                try:
                    self.set_target_cell(hero.cell_x, hero.cell_y)
                    # increase speed briefly while chasing
                    old_speed = self.speed
                    self.speed = max(self.speed, 240.0)
                    super().update(dt)
                    self.speed = old_speed
                except Exception:
                    super().update(dt)
            else:
                super().update(dt)
            # disappear after visible_duration
            if self.visible_timer >= self.visible_duration:
                self.dead = True
        else:
            # persistent enemies behave as before, but with more activity
            super().update(dt)
            if not self.is_moving and random.random() < 0.05:
                self.choose_new_target()


# Game state
state = 'menu'
music_on = True

hero = Hero(GRID_W // 2, GRID_H // 2)
enemies = [Enemy(3, 3, 4, 4, persistent=True), Enemy(10, 6, 3, 5, persistent=True), Enemy(5, 9, 5, 3, persistent=True)]
# enemy spawn control
enemy_spawn_timer = 0.0
spawn_interval = 5.0  # seconds between spawns
max_enemies = 8


def draw():
    screen.clear()
    if state == 'menu':
        draw_menu()
    elif state == 'playing':
        draw_game()
    elif state == 'victory':
        draw_victory()


def draw_menu():
    # draw background image if loaded
    try:
        if menu_bg_surf is not None and pygame is not None:
            try:
                screen.surface.blit(menu_bg_surf, (0, 0))
            except Exception:
                pass
    except Exception:
        pass

    # horizontal layout for three buttons
    btn_w = 160
    btn_h = 56
    spacing = 24
    total_w = 3 * btn_w + 2 * spacing
    left = max(10, WIDTH // 2 - total_w // 2)
    y = HEIGHT // 2

    start_rect = Rect(left, y, btn_w, btn_h)
    music_rect = Rect(left + btn_w + spacing, y, btn_w, btn_h)
    exit_rect = Rect(left + 2 * (btn_w + spacing), y, btn_w, btn_h)

    # attempt to use kenney tile_0040 as button background
    tile_bg = None
    try:
        # tile_0040.png corresponds to index 41 (1-based)
        if have_kenney and pygame is not None:
            tile_bg = load_tile_image_by_index(41)
    except Exception:
        tile_bg = None

    # draw each button using the tile as background when available
    buttons = [
        (start_rect, 'Start Game', (40, 120, 40)),
        (music_rect, f'Music: {"On" if music_on else "Off"}', (120, 120, 40)),
        (exit_rect, 'Exit', (120, 40, 40)),
    ]

    # mouse pos for hover
    try:
        mx, my = pygame.mouse.get_pos() if pygame is not None else (0, 0)
    except Exception:
        mx, my = (0, 0)

    base_alpha = int(255 * 0.5)
    hover_alpha = int(255 * 0.9)

    for rect, label, fallback_color in buttons:
        hovered = rect.collidepoint((mx, my))
        alpha = hover_alpha if hovered else base_alpha
        drawn = False
        if tile_bg is not None and pygame is not None:
            try:
                bg = pygame.transform.scale(tile_bg, (rect.width, rect.height))
                surf = bg.copy()
                surf.set_alpha(alpha)
                screen.surface.blit(surf, (rect.x, rect.y))
                drawn = True
            except Exception:
                drawn = False
        if not drawn:
            if pygame is not None:
                try:
                    surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                    r, g, b = fallback_color
                    surf.fill((r, g, b, alpha))
                    screen.surface.blit(surf, (rect.x, rect.y))
                except Exception:
                    screen.draw.filled_rect(rect, fallback_color)
            else:
                screen.draw.filled_rect(rect, fallback_color)

        screen.draw.text(label, center=(rect.x + rect.width // 2, rect.y + rect.height // 2), color='white')


def draw_game():
    # grid background (draw tiles from TMX if available)
    for gx in range(GRID_W):
        for gy in range(GRID_H):
            x = gx * CELL
            y = gy * CELL
            drawn = False
            if have_kenney and map_data is not None:
                idx = map_data[gy * GRID_W + gx]
                gid = gid_to_tile_index(idx)
                if gid > 0:
                    img = load_tile_image_by_index(gid)
                    if img is not None:
                        try:
                            screen.surface.blit(img, (x, y))
                            drawn = True
                        except Exception:
                            drawn = False
            if not drawn:
                r = Rect(x, y, CELL, CELL)
                screen.draw.rect(r, (70, 70, 70))
    # draw entities
    # draw goal
    try:
        if have_kenney and goal_sprite_tile is not None:
            gx, gy = goal_cell
            px = gx * CELL + (CELL - goal_sprite_tile.get_width()) // 2
            py = gy * CELL + (CELL - goal_sprite_tile.get_height()) // 2
            try:
                screen.surface.blit(goal_sprite_tile, (px, py))
            except Exception:
                pass
        else:
            # simple marker
            screen.draw.filled_rect(Rect(goal_cell[0]*CELL+12, goal_cell[1]*CELL+12, CELL-24, CELL-24), (200,200,50))
    except Exception:
        pass
    hero.draw(screen)
    for e in enemies:
        e.draw(screen)
    # HUD
    screen.draw.text(f'HP: {hero.hp}', topleft=(10, 10), color='white')


def update(dt):
    if state == 'playing':
        hero.update(dt)
        for e in list(enemies):
            e.update(dt)
            # simple collision detection
            if int(e.x)//CELL == int(hero.x)//CELL and int(e.y)//CELL == int(hero.y)//CELL:
                on_hit()
        # remove dead enemies
        enemies[:] = [e for e in enemies if not getattr(e, 'dead', False)]
        # spawn enemies periodically on floor cells
        global enemy_spawn_timer
        enemy_spawn_timer += dt
        try:
            if enemy_spawn_timer >= spawn_interval and len(enemies) < max_enemies:
                enemy_spawn_timer = 0.0
                # choose spawn candidate from floor_gids if available
                candidates = []
                if map_data is not None and floor_gids:
                    for gy in range(GRID_H):
                        for gx in range(GRID_W):
                            idx = map_data[gy * GRID_W + gx]
                            if idx in floor_gids:
                                # avoid hero/enemy cells
                                if (gx, gy) == (hero.cell_x, hero.cell_y):
                                    continue
                                conflict = False
                                for ex in enemies:
                                    if (gx, gy) == (ex.cell_x, ex.cell_y):
                                        conflict = True
                                        break
                                if not conflict:
                                    candidates.append((gx, gy))
                # fallback to any free cell
                if not candidates:
                    for gy in range(GRID_H):
                        for gx in range(GRID_W):
                            if (gx, gy) == (hero.cell_x, hero.cell_y):
                                continue
                            conflict = False
                            for ex in enemies:
                                if (gx, gy) == (ex.cell_x, ex.cell_y):
                                    conflict = True
                                    break
                            if not conflict:
                                candidates.append((gx, gy))
                if candidates:
                    sx, sy = random.choice(candidates)
                    enemies.append(Enemy(sx, sy, 3, 3))
        except Exception:
            pass
        # check victory
        if int(hero.x)//CELL == goal_cell[0] and int(hero.y)//CELL == goal_cell[1]:
            on_victory()


def on_hit():
    if hero.hp > 0:
        hero.hp -= 1
        if 'sounds' in globals():
            try:
                sounds.sfx.play()
            except Exception:
                pass
        if hero.hp <= 0:
            go_to_menu()


def go_to_menu():
    global state
    state = 'menu'
    if music_on:
        if 'music' in globals():
            try:
                music.stop()
            except Exception:
                pass


def on_key_down(key):
    if state != 'playing':
        return
    # grid movement: change target cell and allow smooth movement
    # prefer comparing to `keys` constants, fallback to attribute `name` for compatibility
    name = getattr(key, 'name', '').lower() if key is not None else ''
    if key == keys.LEFT or name == 'left':
        hero.set_target_cell(hero.cell_x - 1, hero.cell_y)
    elif key == keys.RIGHT or name == 'right':
        hero.set_target_cell(hero.cell_x + 1, hero.cell_y)
    elif key == keys.UP or name == 'up':
        hero.set_target_cell(hero.cell_x, hero.cell_y - 1)
    elif key == keys.DOWN or name == 'down':
        hero.set_target_cell(hero.cell_x, hero.cell_y + 1)


def on_mouse_down(pos):
    global state, music_on
    if state == 'menu':
        # align with horizontal layout used in draw_menu
        btn_w = 160
        btn_h = 56
        spacing = 24
        total_w = 3 * btn_w + 2 * spacing
        left = max(10, WIDTH // 2 - total_w // 2)
        y = HEIGHT // 2
        start_rect = Rect(left, y, btn_w, btn_h)
        music_rect = Rect(left + btn_w + spacing, y, btn_w, btn_h)
        exit_rect = Rect(left + 2 * (btn_w + spacing), y, btn_w, btn_h)
        if start_rect.collidepoint(pos):
            start_game()
        elif music_rect.collidepoint(pos):
            music_on = not music_on
            if music_on:
                if 'music' in globals():
                    try:
                        music.play('bg')
                    except Exception:
                        pass
            else:
                if 'music' in globals():
                    try:
                        music.stop()
                    except Exception:
                        pass
        elif exit_rect.collidepoint(pos):
            quit()


def start_game():
    global state, hero, goal_cell
    hero = Hero(GRID_W // 2, GRID_H // 2)
    random.shuffle(enemies)
    # choose a random goal cell that's not occupied by the hero or enemies
    # prefer cells that belong to the detected floor_gids (from TMX)
    candidates = []
    try:
        # prefer explicit floor tiles when available
        if map_data is not None and explicit_floor_gids:
            for gy in range(GRID_H):
                for gx in range(GRID_W):
                    idx = map_data[gy * GRID_W + gx]
                    if idx in explicit_floor_gids:
                        candidates.append((gx, gy))
        elif map_data is not None and 'floor_gids' in globals() and floor_gids:
            for gy in range(GRID_H):
                for gx in range(GRID_W):
                    idx = map_data[gy * GRID_W + gx]
                    if idx in floor_gids:
                        candidates.append((gx, gy))
    except Exception:
        candidates = []

    if not candidates:
        # fallback to any free cell
        for gy in range(GRID_H):
            for gx in range(GRID_W):
                if (gx, gy) == (hero.cell_x, hero.cell_y):
                    continue
                conflict = False
                for e in enemies:
                    if (gx, gy) == (e.cell_x, e.cell_y):
                        conflict = True
                        break
                if not conflict:
                    candidates.append((gx, gy))

    if candidates:
        goal_cell = random.choice(candidates)
    else:
        goal_cell = (max(0, GRID_W-2), max(0, GRID_H-2))
    state = 'playing'
    if music_on:
        if 'music' in globals():
            try:
                music.play('bg')
            except Exception:
                pass


def on_victory():
    global state
    state = 'victory'
    try:
        if 'music' in globals():
            music.stop()
    except Exception:
        pass


def draw_victory():
    screen.clear()
    screen.draw.text("Você venceu!", center=(WIDTH//2, HEIGHT//2), fontsize=64, color='yellow')


def quit():
    import sys
    sys.exit(0)


def on_key_up(key):
    pass


pgzrun.go()
