# FindsBlur Standalone v1.3.1 — 中文／日本語切替対応

独立版 FindsBlur 计算工具／単独計算ツール。
**这不是裁切软件的融合版。／画像切り出しソフトとの統合版ではありません。**

## CalcDebug / 中间图像保存 / 中間画像保存

**v1.3.0** 新增 CalcDebug 选项（默认关闭），支持手动选择诊断文件夹。默认目录是 TXT 输出旁的 CalcDebug。成功的单图包含 20 张阶段 PNG、1 张原始解码 RGB 参考、最多 3 张彩色预览、逐扫描线及阶段目录 JSON。失败图仅保存执行过的步骤。数值计算及官方 TXT 格式不变。

**v1.3.0** に CalcDebug を追加（初期設定 OFF）。保存先を直接入力・参照でき、空欄は TXT の保存先にある CalcDebug フォルダーを使用します。20 段階の画像と RGB 参照、擬似カラー、スキャンライン JSON、診断メタデータを保存します。計算失敗時は到達した工程のみ保存し、数値計算の内容は変更しません。

[全20工程の詳細 / 20 个步骤中日文说明](CalcDebug_GUIDE_CN_JA.md)

## 中文说明

### 功能

- **中文 / 日本語**：窗口右上角可以直接切换；标题、按钮、文件选择器、状态、进度、已有日志和提示框都会切换。不必重启，也不会清空已经填写的图片路径、TXT 输出位置、并行数或运行进度。
- **默认文件夹模式**：地址支持手动输入、粘贴或浏览选择，递归搜索 JPG / JPEG / BMP，按文件名排序。
- **单张图片模式**：可选；在同一输入框直接填写文件路径，或通过浏览选择。
- **TXT 输出**：路径和文件名均可指定；已自定义的保存路径在切换语言或输入目录时不会被覆盖。
- **计算**：复用仓库中 Phase 11–13 的算法，IJG 8c `islow`、Fancy Upsampling=1、Block Smoothing=1；原版参数映射固定。并行数 1–4（默认 2）。计算不读取官方 TXT。
- **失败图片不跳过**：每张实际尝试计算的图片都按顺序保留一行。以下输出格式不会随语言变化：

  ```text
  2_DSC00463.jpg 75.954198 12.821429 43.339483 77.028756
  2_DSC00464.jpg ブレ度合測定に失敗しました。
  2_DSC00465.jpg 30.535714 31.351852 30.926418 43.764923
  ```

  另外生成 `_errors.txt` 详细错误文件；其标题与可识别的错误描述使用启动任务时所选语言。用户主动停止后，未开始计算的图片不会被误认为测量失败。

### Windows 运行

1. 将仓库复制到原先能够正常运行 FindsBlur 的 Windows 开发环境；保留 `.venv`、Phase 源码，以及本地编译的 `_work\IJG8c\bin\ijg8c_rgb_probe.exe`。
2. 双击 [`RUN_WINDOWS.cmd`](RUN_WINDOWS.cmd)，或在仓库根目录执行：

   ```bat
   .venv\Scripts\python.exe -m standalone_gui
   ```

3. 选择语言、文件夹/单张图片、TXT 位置，再开始计算。

**注意：** 当前 GitHub 仓库跟踪源码、脚本与测试，不直接提交可携式 EXE、官方 EXE、个人照片、RAW 或编译后的 IJG8c。v1.2.1 完整可携式 Windows x64 分发包已通过 GitHub Actions 构建，可从上方构建记录的 Artifacts 下载；也可运行 [`BUILD_WINDOWS_PORTABLE.cmd`](BUILD_WINDOWS_PORTABLE.cmd) 在本机重新生成目录版。完整官方数值回归仍需独立验收。

### 回归测试

```bash
python -m unittest discover -s standalone_gui/tests -v
```

Tk GUI 测试需要可用的显示器（Linux 上可用 `xvfb-run`）。新改动包括中日互译键一致性、切换时保留路径与任务状态、日文文件对话框、日文失败提示、输出行格式不变。计算的端到端一致性需在 Windows 上使用旧的 110 张、113 张官方样本重新验证。

## 日本語説明

### 主な機能

- **中文 / 日本語の切替**：ウィンドウ右上でいつでも切り替え可能です。タイトル、ボタン、ダイアログ、状態、進捗、過去の実行ログが切り替わります。入力フォルダー、TXT保存先、並列処理数、進捗はそのまま保持されます。
- **フォルダーが初期設定**：パスを直接入力・貼り付け、または「参照...」で選択できます。サブフォルダーも含めて JPG / JPEG / BMP をファイル名順に処理します。
- **画像1枚モード**：ラジオボタンで切り替え、パスの直接入力または参照で指定できます。
- **TXT保存先**：保存先フォルダーとファイル名を自由に指定できます。言語や画像フォルダーを変えても、手動で指定した保存先は保持されます。
- **計算処理**：既存 Phase 11–13 の計算ロジック、IJG 8c (`islow`, Fancy=1, Smoothing=1)、確認済み固定パラメータを使用します。並列数は1～4（初期設定2）です。公式TXTは計算の入力に使用しません。
- **計算失敗した画像**：処理対象から除外せず、`ファイル名 ブレ度合測定に失敗しました。` を必ず出力します（ユーザーによる停止で未着手の画像を除く）。**出力TXTの書式は表示言語を変更しても変わりません。** `_errors.txt` に詳細を保存します。

### Windowsでの起動

1. 既存のWindows開発環境でリポジトリを使用してください。`.venv`、Phaseモジュール、ローカルビルド済みの `_work\IJG8c\bin\ijg8c_rgb_probe.exe` が必要です。
2. [`RUN_WINDOWS.cmd`](RUN_WINDOWS.cmd) を実行するか、リポジトリ直下で次のコマンドを実行します。

   ```bat
   .venv\Scripts\python.exe -m standalone_gui
   ```

3. 右上で言語を選択し、画像フォルダーまたは画像1枚、TXTの保存先を指定して計算を開始します。

ソースコードとテストのみを公開しています。v1.2.1の配布用Windows x64版はGitHub Actionsでビルドと起動チェックに成功しています。配布版は上記のActionsのArtifactsから入手できます。必要に応じて [`BUILD_WINDOWS_PORTABLE.cmd`](BUILD_WINDOWS_PORTABLE.cmd) でビルドし、実画像を使って検証してください。

### テスト

```bash
python -m unittest discover -s standalone_gui/tests -v
```

GUIテストはTkディスプレイが必要です。言語変更での入力・出力パス保持、進捗、翻訳の網羅性、失敗行の不変性を確認します。Windows実機での110枚＋113枚の回帰は別途必要です。

## Fixed algorithm / 固定参数 / 固定パラメータ

For image short edge `s`, nearby and hole size: `round_half_up(s × .05)`; max scan width: `round_half_up(s × .10)`; x margin: `round_half_up(s × .20)`; y margin: `round_half_up(s × (7/30+.05))`. Native captured arguments have been verified for 1170×779 images. Other dimensions and BMP parity remain subject to further testing.


## 当前 Windows 便携版 / 現在のWindows配布版

- 中文：**v1.2.1 Windows x64 完整目录版已构建成功，且用户已确认之前失败的棋盘图可以计算。** 无需安装 Python；解压后运行 `FindsBlur_Standalone.exe`，保持 `_internal` 和 EXE 在同一分发文件夹。下载位置：[GitHub Actions #41941674025（Artifacts）](https://github.com/snailjayxxx/CIPA-Calc/actions/runs/41941674025)。仅在源码里保存打包流程，不将 175 MB 运行文件及其他二进制包直接跟踪进 Git。暂不声称全部官方样本六位小数完全一致。
- 日本語：**v1.2.1のWindows x64ポータブル版はビルドに成功し、以前失敗していたチェッカーボード画像の計算成功がユーザーから報告されています。** Pythonの追加インストールは不要です。ZIPを展開し、`_internal`を含むフォルダー一式を保持して`FindsBlur_Standalone.exe`を実行してください。[GitHub Actions #41941674025（Artifacts）](https://github.com/snailjayxxx/CIPA-Calc/actions/runs/41941674025)からダウンロードできます。配布ファイルには保存期限があります。すべての公式TXT結果との6桁一致は引き続き検証対象です。

## v1.2.1 — 402B00 flag-buffer regression fix / 分叉点标记修正 / 分岐点フラグ修正

- 中文：修复 `phase12/whole_image_until_flags.py` 的缓冲区角色错误。旧版把二值区域中的 `0xff` 误当成分叉点候选，造成 `native:no matching projection junctions`，黑白棋盘可能全部失败。新版先保留 `0x01/0x03` 骨架/分叉标记，再按区域掩码叠加 `0x04`。测量参数和 TXT 格式不变。
- 日本語：`0x402B00` のバッファ順序を修正し、二値領域の `0xff` を分岐点として誤検出する問題を修正。骨格 `0x01`、分岐 `0x03`、領域 `0x04` を合成。測定パラメータおよび TXT 形式は変更しません。
- Regression test: `standalone_gui/tests/test_flag_overlay_regression.py` tests bit-label preservation. Real JPEG→TXT parity with the official EXE requires separate confirmation.
- Windows portable build: `.github/workflows/findsblur-windows-v1.2.1.yml` builds a folder distribution on pushes to `main`.

## v1.3.1 — 静默后台解码 / コンソール非表示のデコード

- 中文：批量计算时 IJG 8c JPEG 解码器作为独立子进程启动。旧版 Windows 会反复弹出 CMD。现在使用 Windows `CREATE_NO_WINDOW` 标志隐藏解码器控制台，防止抢焦点；仍然保存 stdout/stderr 以处理错误，不改变解码器命令、参数和计算结果。正常 GUI 继续无控制台运行，CalcDebug 不受影响。
- 日本語：バッチ計算時に IJG 8c デコーダーのコンソールが何度も表示される現象を、Windows `CREATE_NO_WINDOW` で解消。標準出力／エラー取得、JPEG デコード設定、数値計算、CalcDebug の保存内容は変更しません。
- Regression: `standalone_gui/tests/test_no_console.py` tests Windows process flags and decoder RGB bytes using a mocked child. Windows portable build self-test continues in GitHub Actions.
