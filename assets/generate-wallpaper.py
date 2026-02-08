#!/usr/bin/env python3
"""
Generate AVS Technologies wallpaper for GK41 XFCE desktop.
Uses pycairo to create a professional dark wallpaper with AVS branding.
"""

import cairo
import math
import os
from datetime import datetime

# Output
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'avs-wallpaper-gk41.png')

# Dimensions (1920x1080 for standard Full HD)
WIDTH = 1920
HEIGHT = 1080

# Colors - Dark professional theme with AVS blue accent
BG_DARK = (0.067, 0.075, 0.106)        # #111326 - very dark blue
BG_MEDIUM = (0.098, 0.110, 0.157)      # #191C28 - dark blue
ACCENT_BLUE = (0.204, 0.494, 0.969)    # #347EF7 - AVS blue
ACCENT_GLOW = (0.204, 0.494, 0.969, 0.15)  # blue glow
TEXT_WHITE = (0.93, 0.94, 0.96)        # #EDEF54 - off-white
TEXT_GRAY = (0.45, 0.48, 0.55)         # #73798C - gray
GRID_COLOR = (0.14, 0.16, 0.21, 0.4)  # subtle grid

def draw_gradient_background(ctx):
    """Draw dark gradient background"""
    # Radial gradient from center
    pat = cairo.RadialGradient(WIDTH * 0.5, HEIGHT * 0.4, 0,
                                WIDTH * 0.5, HEIGHT * 0.4, WIDTH * 0.7)
    pat.add_color_stop_rgb(0, BG_MEDIUM[0], BG_MEDIUM[1], BG_MEDIUM[2])
    pat.add_color_stop_rgb(1, BG_DARK[0], BG_DARK[1], BG_DARK[2])
    ctx.set_source(pat)
    ctx.paint()

def draw_grid(ctx):
    """Draw subtle grid pattern"""
    ctx.set_source_rgba(*GRID_COLOR)
    ctx.set_line_width(0.5)

    # Horizontal lines
    spacing = 60
    for y in range(0, HEIGHT, spacing):
        ctx.move_to(0, y)
        ctx.line_to(WIDTH, y)
    # Vertical lines
    for x in range(0, WIDTH, spacing):
        ctx.move_to(x, 0)
        ctx.line_to(x, HEIGHT)
    ctx.stroke()

def draw_decorative_circles(ctx):
    """Draw decorative tech circles"""
    # Large glow circle top-right
    pat = cairo.RadialGradient(WIDTH * 0.82, HEIGHT * 0.18, 10,
                                WIDTH * 0.82, HEIGHT * 0.18, 300)
    pat.add_color_stop_rgba(0, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.08)
    pat.add_color_stop_rgba(0.5, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.03)
    pat.add_color_stop_rgba(1, 0, 0, 0, 0)
    ctx.set_source(pat)
    ctx.paint()

    # Smaller glow bottom-left
    pat2 = cairo.RadialGradient(WIDTH * 0.15, HEIGHT * 0.75, 5,
                                 WIDTH * 0.15, HEIGHT * 0.75, 200)
    pat2.add_color_stop_rgba(0, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.06)
    pat2.add_color_stop_rgba(1, 0, 0, 0, 0)
    ctx.set_source(pat2)
    ctx.paint()

    # Decorative ring
    ctx.set_source_rgba(ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.1)
    ctx.set_line_width(1.5)
    ctx.arc(WIDTH * 0.82, HEIGHT * 0.18, 120, 0, 2 * math.pi)
    ctx.stroke()
    ctx.arc(WIDTH * 0.82, HEIGHT * 0.18, 180, 0, 2 * math.pi)
    ctx.stroke()

def draw_connection_lines(ctx):
    """Draw tech connection lines"""
    ctx.set_line_width(1)

    # Horizontal accent line
    pat = cairo.LinearGradient(0, 0, WIDTH, 0)
    pat.add_color_stop_rgba(0, 0, 0, 0, 0)
    pat.add_color_stop_rgba(0.3, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.2)
    pat.add_color_stop_rgba(0.5, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.4)
    pat.add_color_stop_rgba(0.7, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.2)
    pat.add_color_stop_rgba(1, 0, 0, 0, 0)
    ctx.set_source(pat)
    ctx.move_to(0, HEIGHT * 0.55)
    ctx.line_to(WIDTH, HEIGHT * 0.55)
    ctx.stroke()

    # Dots on the line
    for x_frac in [0.25, 0.35, 0.45, 0.55, 0.65, 0.75]:
        ctx.set_source_rgba(ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.5)
        ctx.arc(WIDTH * x_frac, HEIGHT * 0.55, 3, 0, 2 * math.pi)
        ctx.fill()

def draw_server_nodes(ctx):
    """Draw small server node indicators"""
    nodes = [
        (WIDTH * 0.15, HEIGHT * 0.3, 'web-server'),
        (WIDTH * 0.85, HEIGHT * 0.35, 'logics-db'),
        (WIDTH * 0.75, HEIGHT * 0.7, 'api-server'),
        (WIDTH * 0.2, HEIGHT * 0.72, 'backup'),
        (WIDTH * 0.5, HEIGHT * 0.25, 'n8n'),
    ]

    for x, y, label in nodes:
        # Node dot
        ctx.set_source_rgba(ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.3)
        ctx.arc(x, y, 8, 0, 2 * math.pi)
        ctx.fill()
        ctx.set_source_rgba(ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.6)
        ctx.arc(x, y, 4, 0, 2 * math.pi)
        ctx.fill()

        # Node label
        ctx.set_source_rgba(*TEXT_GRAY)
        ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        ctx.set_font_size(11)
        ctx.move_to(x + 12, y + 4)
        ctx.show_text(label)

def draw_branding(ctx):
    """Draw AVS Technologies branding"""
    # Main title: AVS
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(72)

    # Measure text for positioning
    text = "AVS"
    extents = ctx.text_extents(text)
    x = (WIDTH - extents.width) / 2
    y = HEIGHT * 0.44

    # Text shadow/glow
    ctx.set_source_rgba(ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.15)
    ctx.move_to(x, y + 2)
    ctx.show_text(text)

    # Main text
    ctx.set_source_rgb(*TEXT_WHITE)
    ctx.move_to(x, y)
    ctx.show_text(text)

    # Subtitle: TECHNOLOGIES
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(22)
    text2 = "TECHNOLOGIES"
    extents2 = ctx.text_extents(text2)
    x2 = (WIDTH - extents2.width) / 2
    ctx.set_source_rgba(ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.9)
    ctx.move_to(x2, y + 35)
    ctx.show_text(text2)

    # Accent line under TECHNOLOGIES
    line_width = extents2.width + 40
    line_x = (WIDTH - line_width) / 2
    line_y = y + 50
    pat = cairo.LinearGradient(line_x, 0, line_x + line_width, 0)
    pat.add_color_stop_rgba(0, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0)
    pat.add_color_stop_rgba(0.3, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.6)
    pat.add_color_stop_rgba(0.7, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.6)
    pat.add_color_stop_rgba(1, ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0)
    ctx.set_source(pat)
    ctx.set_line_width(2)
    ctx.move_to(line_x, line_y)
    ctx.line_to(line_x + line_width, line_y)
    ctx.stroke()

def draw_system_info(ctx):
    """Draw system identification"""
    # Bottom bar
    ctx.set_source_rgba(0, 0, 0, 0.3)
    ctx.rectangle(0, HEIGHT - 50, WIDTH, 50)
    ctx.fill()

    # Machine name
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(13)
    ctx.set_source_rgba(*TEXT_GRAY)

    info_left = "Michel  |  GK41 Mini-PC  |  Debian 13 Trixie"
    ctx.move_to(30, HEIGHT - 18)
    ctx.show_text(info_left)

    info_right = "AVS Technologies  |  14 rue Joliot-Curie, Petit-Couronne"
    extents = ctx.text_extents(info_right)
    ctx.move_to(WIDTH - extents.width - 30, HEIGHT - 18)
    ctx.show_text(info_right)

    # Accent dot
    ctx.set_source_rgba(ACCENT_BLUE[0], ACCENT_BLUE[1], ACCENT_BLUE[2], 0.7)
    ctx.arc(15, HEIGHT - 25, 4, 0, 2 * math.pi)
    ctx.fill()

def draw_tagline(ctx):
    """Draw tagline below branding"""
    ctx.select_font_face("Sans", cairo.FONT_SLANT_ITALIC, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(14)
    ctx.set_source_rgba(TEXT_GRAY[0], TEXT_GRAY[1], TEXT_GRAY[2], 0.8)

    tagline = "Solutions de caisse  •  Monetique  •  Videosurveillance  •  Alarme  •  Controle d'acces"
    extents = ctx.text_extents(tagline)
    x = (WIDTH - extents.width) / 2
    ctx.move_to(x, HEIGHT * 0.55 + 50)
    ctx.show_text(tagline)


def main():
    # Create surface
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
    ctx = cairo.Context(surface)

    # Draw layers
    draw_gradient_background(ctx)
    draw_grid(ctx)
    draw_decorative_circles(ctx)
    draw_server_nodes(ctx)
    draw_connection_lines(ctx)
    draw_branding(ctx)
    draw_tagline(ctx)
    draw_system_info(ctx)

    # Save
    surface.write_to_png(OUTPUT_FILE)
    print(f"Wallpaper saved to: {OUTPUT_FILE}")
    print(f"Size: {WIDTH}x{HEIGHT}")


if __name__ == '__main__':
    main()
