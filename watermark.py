#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
竖排中文文字水印（保留原音轨，支持中断续处理）

纯 Python 方案：moviepy + Pillow 逐帧绘制，不依赖系统安装的 ffmpeg 可执行文件。

用法：
    python watermark.py --src ./videos --out ./output --text "示例水印文字"
    python watermark.py --src ./videos --text "示例" --size 72 --left 40 --top 80
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.avi', '.flv', '.wmv', '.m4v', '.3gp'}

# 常见中文字体候选，按平台自动挑第一个存在的
FONT_CANDIDATES = [
    '/System/Library/Fonts/PingFang.ttc',          # macOS
    '/System/Library/Fonts/STHeiti Medium.ttc',    # macOS 旧版
    'C:/Windows/Fonts/simhei.ttf',                 # Windows 黑体
    'C:/Windows/Fonts/msyh.ttc',                   # Windows 雅黑
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',  # Linux 文泉驿
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
]


# ============ 键盘监听：按 q 中断 ============
_abort_flag = False


def _start_keyboard_listener() -> None:
    """Windows 用 msvcrt；其他平台尽量用 pynput，装不上就退化为不可中断。"""
    global _abort_flag
    if sys.platform == 'win32':
        import msvcrt

        def poll():
            global _abort_flag
            while True:
                if msvcrt.kbhit() and msvcrt.getwch().lower() == 'q':
                    _abort_flag = True
                    return

        threading.Thread(target=poll, daemon=True).start()
        return

    try:
        from pynput import keyboard

        def on_press(key):
            global _abort_flag
            try:
                if getattr(key, 'char', None) and key.char.lower() == 'q':
                    _abort_flag = True
            except Exception:
                pass

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
    except ImportError:
        print('[WARN] 未安装 pynput，本平台不支持按 q 中断')


def kb_hit() -> bool:
    return _abort_flag


# ============ 水印绘制 ============
class Watermarker:
    def __init__(self, text: str, font_path: str | None, size: int, left: int, top: int,
                 color=(255, 255, 255), shadow=(0, 0, 0), stroke: int = 3):
        self.text = text
        self.size = size
        self.left = left
        self.top = top
        self.color = color
        self.shadow = shadow
        self.stroke = stroke
        self.font = ImageFont.truetype(font_path or self.detect_font(), size)
        self.line_h = size + 8

    @staticmethod
    def detect_font() -> str:
        for path in FONT_CANDIDATES:
            if Path(path).exists():
                return path
        raise FileNotFoundError(
            '没找到可用的中文字体，请用 --font 指定一个 .ttf/.ttc 文件'
        )

    def draw_on(self, frame: np.ndarray) -> np.ndarray:
        img = Image.fromarray(frame)
        draw = ImageDraw.Draw(img)
        for idx, ch in enumerate(self.text):
            y = self.top + idx * self.line_h
            for dx in range(-self.stroke, self.stroke + 1):
                for dy in range(-self.stroke, self.stroke + 1):
                    if dx or dy:
                        draw.text((self.left + dx, y + dy), ch, font=self.font, fill=self.shadow)
            draw.text((self.left, y), ch, font=self.font, fill=self.color)
        return np.asarray(img)


# ============ 单文件处理 ============
def process_video(marker: Watermarker, src_path: Path, dst_path: Path) -> bool:
    from moviepy.editor import VideoFileClip

    print(f'[INFO] 开始处理：{src_path.name}（按 q 可暂停）')
    clip = VideoFileClip(str(src_path))

    def process_frame(get_frame, t):
        if kb_hit():
            raise KeyboardInterrupt
        return marker.draw_on(get_frame(t))

    write_kwargs = dict(codec='libx264', audio_codec='aac', verbose=False, logger=None)
    try:
        clip.fl(process_frame, apply_to=['video']).write_videofile(str(dst_path), **write_kwargs)
    except KeyboardInterrupt:
        print('\n>>> 检测到 q，暂停...')
        while True:
            yn = input('>>> 确认退出?(y/n) ').strip().lower()
            if yn == 'y':
                if dst_path.exists():
                    dst_path.unlink()
                print('[EXIT] 已删除半成品')
                return False
            if yn == 'n':
                break
            print('请输入 y 或 n')
        # 继续写，从头开始
        clip.fl(process_frame, apply_to=['video']).write_videofile(str(dst_path), **write_kwargs)

    print(f'[DONE] 已保存（含音频）：{dst_path.name}')
    return True


# ============ 选择语法：2  5-  1-3  1,3,5-8,10- ============
def parse_choice(raw: str, max_n: int) -> list[int]:
    raw = raw.strip()
    if not raw:
        return []
    picked: set[int] = set()
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start_s, end_s = part.split('-', 1)
            start = int(start_s) - 1
            end = max_n - 1 if end_s == '' else int(end_s) - 1
            if start < 0 or start >= max_n or end < start or end >= max_n:
                raise ValueError(f'区间 {part} 超出范围')
            picked.update(range(start, end + 1))
        else:
            idx = int(part) - 1
            if idx < 0 or idx >= max_n:
                raise ValueError(f'序号 {part} 超出范围')
            picked.add(idx)
    return sorted(picked)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='竖排中文文字水印')
    parser.add_argument('--src', required=True, help='视频所在文件夹')
    parser.add_argument('--out', help='输出文件夹，默认 ./output')
    parser.add_argument('--text', default='示例水印', help='竖排显示的文本')
    parser.add_argument('--font', default=None, help='字体文件路径，默认自动探测')
    parser.add_argument('--size', type=int, default=60, help='字号，默认 60')
    parser.add_argument('--left', type=int, default=30, help='左边距')
    parser.add_argument('--top', type=int, default=100, help='上边距')
    parser.add_argument('--stroke', type=int, default=3, help='描边宽度')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    src_dir = Path(args.src).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve() if args.out else src_dir / 'output'
    out_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in VIDEO_EXTS)
    if not videos:
        print(f'[WARN] 在 {src_dir} 未找到任何视频文件')
        return 1

    for i, v in enumerate(videos, 1):
        print(f'[{i:>3}]  {v.name}')

    while True:
        raw = input('\n>>> 请选择要处理的视频（如 2 / 5- / 1-3 / 1,3,5-8,10- ，回车=全部）：').strip()
        try:
            choices = parse_choice(raw, len(videos)) if raw else list(range(len(videos)))
            if not choices:
                print('未选中任何视频，请重新输入！')
                continue
            break
        except ValueError as exc:
            print('输入错误：', exc, '请重新输入！')

    marker = Watermarker(args.text, args.font, args.size, args.left, args.top,
                         stroke=args.stroke)
    _start_keyboard_listener()

    for idx in choices:
        target = videos[idx]
        if not process_video(marker, target, out_dir / f'{target.stem}_watermark.mp4'):
            print('[All Abort] 用户主动退出')
            return 0

    print(f'\n[All Done] 共处理 {len(choices)} 个视频 → {out_dir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
