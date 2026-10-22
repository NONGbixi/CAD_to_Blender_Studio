# CAD to Blender Studio · 中文说明

把机械 CAD 装配体做成产品级静帧和影视镜头的一套 Blender / Cycles 生产管线。

这不是库，而是一条真实跑完的产品片流水线：一个 SolidWorks 总装 → 导入 Blender →
搭双摄影棚 → 脚本控制相机 → 笔记本 GPU 渲染 → 剪成 55 秒广告片。轮廓、相机、字幕、
渲染任务管理四套工具都是为这件事从零写的。

代码取自生产项目，**没有为了好看而重写**。CAD、`.blend`、渲染图、字体、音乐都
刻意没有包含进来，复用前请先看 [NOTICE.md](NOTICE.md)。

## 最有价值的部分：模组透明强调

工业产品片常见的需求是"突出这一个机构，但整机还要看得出结构"。常规做法是 Freestyle、
Line Art 或 Wireframe 修改器，但在 79 万个三角面的装配体上，它们做不出**逐帧稳定、
细而不断、遮挡正确**的线。

这里的做法是把问题拆成两半：

1. **面**照常渲染：主体保留原 CAD 材质、完全不透明；其余零件换成派生透明材质，
   Alpha **0.13**，Cycles 渲染后降噪。
2. **线**用装配体自带的派生边线，每帧用当前相机投影到屏幕空间，对**逐帧重建的 BVH**
   做背面与遮挡测试，剔除共面三角形和 16 mm 以下的封闭小特征，最后以
   **35% 不透明度、约 0.4 px、`#A8ADB3`** 一次性合成到降噪后的面画面上。

线在降噪**之后**合成，所以亚像素细线不会被抹掉；文字再叠在其上，且走二维，不受透视影响。

| 已确认参数 | 值 |
|---|---|
| 非主体表面 Alpha | `0.13` |
| 1080p 线宽 | `约 0.4 px`（4K 时 0.8 px） |
| 线条颜色 / 不透明度 | `#A8ADB3` / `35%` |
| 主体 | 原 CAD 材质、完全不透明、几何不动 |
| 剔除的线 | 背面、被遮挡、共面、密集小孔 |
| 不使用 | Freestyle、Line Art、Wireframe 修改器、用模糊假装景深 |

参数在 `studio/02_studio/presets/module_outline_*.json`，实现在
`studio/03_director/outline_approved/`。

## 目录

| 模块 | 作用 | 入口 |
|---|---|---|
| 轮廓管线 | 逐帧透明上下文 + BVH 遮挡测试的投影描边 | `studio/03_director/outline_approved/outline_pipeline.py` |
| 二维线合成 | 把逐帧边线 JSON 合成进面渲染 | `.../compose_edges.py` |
| 模组聚焦 | 决定每个镜头的实体 / 虚化 / 隐藏 | `studio/03_director/module_focus.py` |
| 摄影棚构建 | 从 JSON 预设生成 `Studio_Light` / `Studio_Dark` | `studio/02_studio/scripts/build_studio.py` |
| 场景核心 | Cycles 设备选择、渲染参数、几何指纹 | `.../studio_core.py` |
| 相机系统 | fit / dolly / orbit / follow / animate_lens，56 组已校验取景 | `studio/03_director/camera_control.py` |
| 字幕系统 | 二维 RGBA 字幕 + 逐字 cmap 缺字校验 | `studio/03_director/typography/` |
| 渲染任务 | 带指纹、可续渲的 PNG 序列任务 + FFmpeg 编码 | `.../render_job.py`、`.../encode_video.py` |
| 队列与锁 | 顺序 GPU 队列与单 worker 锁 | `tvc/07_自动化制作/scripts/` |

## 值得抄的工程纪律

- **版本目录只增不改**：每次修订新开 `rNN_<原因>/`，旧工程与旧帧永久可读。
- **单一指针文件**：`project_current.json` / `task_current.json` 记录当前版本与所有输入的 SHA-256。
- **拒绝混用修订**：渲染任务对模型、预设、脚本做哈希，任一变化就拒绝复用旧帧。
- **重开验证**：每个保存的场景都重新打开并重算几何指纹（顶点、循环、材质索引、平滑、
  层级、世界矩阵），不通过不算完成。
- **写下不确定性**：无法证明运动归属的零件记作"置信度中"，不猜。

## 环境要求

- **Blender 4.5.3 LTS**（只在这个版本验证过）
- **Cycles GPU**：全程 OptiX，代码会依次回退 CUDA / HIP / oneAPI / Metal / CPU，
  并记录真正出图的 backend
- **Windows**：只有 `run_render.py` 的资源采样依赖 Win32 `ctypes`；渲染本身跨平台
- **Python 3.12** + `Pillow` / `numpy` / `imageio-ffmpeg`

参考耗时（RTX 5070 Laptop，1080p，OptiX，128 自适应采样，OIDN）：
深色棚 **1.95 秒/帧**，浅色 Shadow Catcher 棚 **5.2 秒/帧**。

## 环境变量

| 变量 | 默认 | 含义 |
|---|---|---|
| `CAD_ROOT` | `studio/` | 含 `01_materials`、`03_director`、`04_output` 的项目根 |
| `CAD_STUDIO_ROOT` | `<repo>/studio` | 镜头引擎使用的摄影棚项目 |
| `CAD_STUDIO_BLEND` | `02_studio/studio.blend` | 渲染任务打开的工程 |
| `CAD_MODEL_BLEND` | `01_materials/model/model.blend` | `build_studio.py` 的 CAD 输入 |
| `CAD_OUTLINE_PROFILE` | `06_视觉控制/module_outline_tvc.json` | 镜头引擎的轮廓配置 |
| `CAD_TYPOGRAPHY_PROFILE` | `04_字体与版式/typography_profile.json` | 字体角色与 SHA-256 |
| `CAD_BLENDER` | `PATH` 中的 `blender` | Blender 可执行文件 |
| `CAD_PYTHON` | `PATH` 中的 `python` | 二维合成辅助脚本用的系统 Python |
| `CAD_FFMPEG` | 内置 `imageio-ffmpeg` | FFmpeg 可执行文件 |

## 状态与限制

- **是抽取，不是封装**：没有 CLI、没有测试、没有 release。是真实生产代码把项目相关部分参数化。
- **继承了原项目的目录约定**：改造成本见 [docs/porting.md](docs/porting.md)。
- **资源采样只在 Windows 可用**。
- **只在一台机器上验证过**：未做长时间温控与 4K 基准。
- **不含任何产品资产**，README 没有效果图是刻意的。
- **不含逐镜头的运动引擎**：那部分绑定在这一台机器的零件编号、齿轮啮合、同步带循环和轮组上，
  不具复用性，放在私有归档里；这里公开的是它所驱动的整套下层能力（摄影棚、相机、轮廓、字幕、任务）。

## 许可

代码 MIT（见 [LICENSE](LICENSE)），第三方声明见 [NOTICE.md](NOTICE.md)。

English README: [README.md](README.md)。
