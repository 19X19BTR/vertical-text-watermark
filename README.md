# 竖排中文文字水印工具

给短视频批量加**竖排中文水印**（一列字，从左上往下排），保留原音轨，纯 Python 实现，不依赖系统装 ffmpeg。

写它的缘由：批量处理后台上传的短视频，需要统一角标，剪辑软件一个个加太慢，而且很容易忘。

## 效果

![效果预览](docs/preview.png)

（预览图是在纯色渐变画面上渲染的，实际视频里是左上角竖排一列白字 + 黑描边。）

## 特点

- **纯 Python**：`moviepy` + `Pillow` 逐帧绘制，机器上没装 ffmpeg 也能跑（moviepy 自带 imageio-ffmpeg）
- **保留原音轨**：输出 `libx264 + aac`，声音不丢
- **可中断**：处理中按 `q` 暂停，选择退出会删掉半成品文件，不留坏文件
- **按序选择**：支持 `2` / `5-` / `1-3` / `1,3,5-8,10-` 这类写法，只处理你挑的那几条
- **字体自动探测**：macOS 苹方、Windows 黑体/雅黑、Linux 文泉驿 / Noto CJK 都会自己找

## 安装

```bash
pip install -r requirements.txt
```

> `moviepy` 请保持 1.x（本脚本用的是 `moviepy.editor` API）。moviepy 2.x 改了导入方式，直接跑会报 ImportError。
> 想用「按 q 中断」需要 `pynput`（Windows 上用系统自带的 `msvcrt`，不需要 pynput）。

## 用法

```bash
# 基本用法
python watermark.py --src ./videos --out ./output --text "示例水印"

# 调位置和大小
python watermark.py --src ./videos --text "我的水印" --size 72 --left 40 --top 90 --stroke 4

# 字体自己指定
python watermark.py --src ./videos --text "角标" --font "/System/Library/Fonts/PingFang.ttc"
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--src` | 必填 | 视频所在目录 |
| `--out` | `<src>/output` | 输出目录 |
| `--text` | `示例水印` | 竖排显示的文字 |
| `--font` | 自动探测 | 字体文件路径 |
| `--size` | 60 | 字号（像素） |
| `--left` / `--top` | 30 / 100 | 位置 |
| `--stroke` | 3 | 黑色描边宽度，白字在浅背景上靠它压住 |

## 原理

1. `VideoFileClip` 读入视频，用 `clip.fl()` 对每一帧做变换
2. 每帧转成 PIL Image，逐字绘制：先画一圈黑色描边偏移（`stroke` 像素），再画白色正文
3. 回写成 mp4（`libx264` 视频 + `aac` 音频）

逐帧处理比 ffmpeg 的 `drawtext` 慢，但不用装 ffmpeg、能精确控制中文字体和描边，跑小批量足够。

## 已知限制

- 一段 1080p / 5 分钟视频大约要 2–4 分钟（逐帧 PIL 绘制是瓶颈）
- 只支持左上角竖直排列，不支持旋转、倾斜、多行
- 中断续传没有实现：中断后重新跑会从头开始

## License

MIT
