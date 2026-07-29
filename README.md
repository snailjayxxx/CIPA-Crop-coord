# CIPA Crop & Coord

一个面向大尺寸照片批处理的 Windows 桌面工具。界面包含三个标签：

1. **相似区域裁切**：使用 sample 图片的指定区域，在文件夹及全部子文件夹内定位相同部位并裁切。
2. **中心裁切**：按固定像素或原图比例，从每张图片的正中心裁切。
3. **坐标导出**：定位 sample 后，将 sample 中心点在每张图片中的 `(x, y)` 像素坐标写入 CSV。

最终发布的 `CIPA-Crop-Coord.exe` 已包含 Python 和运行库，客户电脑不需要安装 Python。

## 功能细节

- 支持 JPG、JPEG、PNG、BMP、TIFF、WebP。
- 递归遍历指定文件夹的所有子文件夹。
- sample 范围、搜索范围均可直接输入 `x / y / 宽 / 高`，也可点击按钮在图片预览上拖框。
- 宽、高为 `0` 时表示使用整张图片或搜索整张图片。
- 可屏蔽 sample 四周 `0%–45%`，定位时仅比较内部区域，减少边缘干扰；成功后仍按完整 sample 范围裁切。
- 匹配采用缩小图粗定位、原始像素精定位。程序每次只保留一张待处理原图，适合 6680 万像素级照片；实际速度和可用内存取决于电脑、图片格式及搜索范围。
- 图片输出名称为 `快门速度_原名`，例如 `1/100s` 的 `abc.jpg` 输出为 `1_100_abc.jpg`。
- 没有 EXIF 快门信息时使用 `unknown_` 前缀。
- 同名输出不会覆盖，自动追加 `__2`、`__3`。
- 如果输出文件夹位于输入文件夹内，输出文件夹会从遍历中排除。
- CSV 使用 UTF-8 BOM 编码，可直接用中文版 Excel 打开。固定三列：`文件名,x坐标,y坐标`；未达到相似度阈值时坐标留空。

> 坐标以读取并按 EXIF 方向旋转后的图片左上角为 `(0, 0)`，x 向右、y 向下。

## Windows 客户端构建

### GitHub 自动构建（推荐）

仓库名使用 `CIPA-Crop-coord`。将代码推送到 GitHub 后：

1. 打开仓库的 **Actions**。
2. 选择 **Build Windows EXE**。
3. 点击 **Run workflow**。
4. 完成后下载名为 `CIPA-Crop-Coord-Windows` 的 artifact，里面是单文件 EXE。

推送 `v1.0.0` 这类 tag 也会自动构建。

### 在 Windows 本机构建

构建电脑需安装 64 位 Python 3.11，然后双击：

```text
build_windows.bat
```

结果位于：

```text
dist\CIPA-Crop-Coord.exe
```

只有“构建电脑”需要 Python，拿到 EXE 的客户电脑不需要。

## 从源码运行

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

python -m pip install -r requirements.txt
python launcher.py
```

## 使用建议

- sample 应只包含稳定、清晰、有纹理的目标，避免大片纯色或重复图案。
- 首次可从相似度 `0.70` 开始。误匹配时提高阈值；漏匹配时适当降低。
- 搜索范围越小，速度越快，也越不容易匹配到错误位置。
- 如果所有照片构图相近，先用代表性照片框选搜索范围。
- 6680 万像素图片建议至少 8 GB 内存，16 GB 更稳妥。
- 程序不会覆盖已有输出，但正式批处理前仍建议先用少量复制文件测试参数。

## 开发测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```
