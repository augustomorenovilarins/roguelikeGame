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

TITLE = "Roguelike - Prototype"

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

import pgzrun
from pgzero.actor import Actor
from pgzero.clock import clock
# `sounds` and `music` are available at runtime when using `pgzrun`.
# Do not import `sounds` from `pgzero` as that raises ImportError in some versions.
from pgzero.keyboard import keys

TITLE = "Roguelike Prototype"


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
        screen.draw.filled_rect(rect, color)


class Hero(AnimatedEntity):
    def __init__(self, cx, cy):
        idle = [(200, 60, 60), (220, 80, 80)]
        move = [(255, 80, 80), (200, 40, 40), (255, 80, 80), (180, 30, 30)]
        image_idle = ['hero_idle_1', 'hero_idle_2']
        image_move = ['hero_move_1', 'hero_move_2']
        super().__init__(cx, cy, idle, move, image_idle, image_move)
        self.hp = 5


class Enemy(AnimatedEntity):
    def __init__(self, cx, cy, territory_w=3, territory_h=3):
        idle = [(60, 60, 200), (80, 80, 220)]
        move = [(80, 80, 255), (40, 40, 200)]
        image_idle = ['enemy_idle_1']
        image_move = []
        super().__init__(cx, cy, idle, move, image_idle, image_move)
        self.territory = (max(0, cx - territory_w//2), max(0, cy - territory_h//2), territory_w, territory_h)
        self.choose_new_target()

    def choose_new_target(self):
        tx = random.randint(self.territory[0], min(GRID_W-1, self.territory[0] + self.territory[2] - 1))
        ty = random.randint(self.territory[1], min(GRID_H-1, self.territory[1] + self.territory[3] - 1))
        self.set_target_cell(tx, ty)

    def update(self, dt):
        super().update(dt)
        if not self.is_moving and random.random() < 0.01:
            self.choose_new_target()


# Game state
state = 'menu'
music_on = True

hero = Hero(GRID_W // 2, GRID_H // 2)
enemies = [Enemy(3, 3, 4, 4), Enemy(10, 6, 3, 5), Enemy(5, 9, 5, 3)]


def draw():
    screen.clear()
    if state == 'menu':
        draw_menu()
    elif state == 'playing':
        draw_game()


def draw_menu():
    screen.draw.text(TITLE, center=(WIDTH//2, 80), fontsize=44, color='white')
    # buttons
    start_rect = Rect(WIDTH//2 - 100, 160, 200, 50)
    music_rect = Rect(WIDTH//2 - 100, 230, 200, 50)
    exit_rect = Rect(WIDTH//2 - 100, 300, 200, 50)
    screen.draw.filled_rect(start_rect, (40, 120, 40))
    screen.draw.filled_rect(music_rect, (120, 120, 40))
    screen.draw.filled_rect(exit_rect, (120, 40, 40))
    screen.draw.text('Start Game', center=start_rect.center, color='white')
    screen.draw.text(f'Music: {"On" if music_on else "Off"}', center=music_rect.center, color='white')
    screen.draw.text('Exit', center=exit_rect.center, color='white')


def draw_game():
    # grid background
    for gx in range(GRID_W):
        for gy in range(GRID_H):
            r = Rect(gx*CELL, gy*CELL, CELL, CELL)
            screen.draw.rect(r, (70, 70, 70))
    # draw entities
    hero.draw(screen)
    for e in enemies:
        e.draw(screen)
    # HUD
    screen.draw.text(f'HP: {hero.hp}', topleft=(10, 10), color='white')


def update(dt):
    if state == 'playing':
        hero.update(dt)
        for e in enemies:
            e.update(dt)
            # simple collision detection
            if int(e.x)//CELL == int(hero.x)//CELL and int(e.y)//CELL == int(hero.y)//CELL:
                on_hit()


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
        start_rect = Rect(WIDTH//2 - 100, 160, 200, 50)
        music_rect = Rect(WIDTH//2 - 100, 230, 200, 50)
        exit_rect = Rect(WIDTH//2 - 100, 300, 200, 50)
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
    global state, hero
    hero = Hero(GRID_W // 2, GRID_H // 2)
    random.shuffle(enemies)
    state = 'playing'
    if music_on:
        if 'music' in globals():
            try:
                music.play('bg')
            except Exception:
                pass


def quit():
    import sys
    sys.exit(0)


def on_key_up(key):
    pass


pgzrun.go()
