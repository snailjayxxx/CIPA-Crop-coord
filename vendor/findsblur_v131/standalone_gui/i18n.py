"""FindsBlur GUI translations; never changes algorithm values or TXT records.

The source-string exception adapter is intentionally limited to user-facing
errors. Technical details not recognized here remain untouched for diagnosis.
"""
from __future__ import annotations

from typing import Any

LANGUAGES = ('zh', 'ja')
LANGUAGE_CHOICES = {'中文': 'zh', '日本語': 'ja'}

TRANSLATIONS: dict[str, dict[str, str]] = {
    'zh': {
        'title': 'FindsBlur 独立计算工具 v1.3.1',
        'headline': 'FindsBlur 独立计算工具',
        'subtitle': 'IJG 8c · 固定原生参数 · JPG / JPEG / BMP',
        'language': '界面语言 / 言語：',
        'source_section': '① 图片来源',
        'folder_mode': '文件夹（默认）',
        'single_mode': '单张图片',
        'browse': '浏览...',
        'folder_help': '默认读取文件夹内全部图片（包含子文件夹）',
        'single_help': '只计算指定的一张图片',
        'output_section': '② TXT 保存位置及文件名',
        'run_section': '③ 开始计算',
        'start': '开始计算',
        'stop': '停止',
        'workers': '并行数：',
        'log_heading': '运行记录',
        'calcdebug_section': '④ CalcDebug · 保存中间图像',
        'calcdebug_enable': 'CalcDebug（保存每一步处理图像，默认关闭）',
        'calcdebug_help': '目录留空：自动保存到 TXT 所在目录 / CalcDebug；每张图片独立子文件夹',
        'calcdebug_select_dir': '选择 CalcDebug 保存目录',
        'calcdebug_bad_path': 'CalcDebug 路径是文件而非文件夹：{path}',
        'calcdebug_started': 'CalcDebug 已启用，保存位置：{path}',
        'calcdebug_saved': 'CalcDebug 中间图像与报告：{path}',
        'ready': '就绪',
        'intro_log': '无法计算的图片不会被跳过，会保留：文件名 ブレ度合測定に失敗しました。',
        'folder_dialog': '选择图片文件夹',
        'image_dialog': '选择单张图片',
        'image_type': '图片',
        'all_files': '所有文件',
        'save_dialog': '保存结果 TXT',
        'found': '找到 {count} 张：{filename}{more}',
        'more': ' ...',
        'input_error_title': '输入错误',
        'choose_txt': '请选择以 .txt 结尾的输出文件名。',
        'confirm_title': '确认覆盖',
        'confirm_overwrite': '{path} 已存在，确定覆盖吗？',
        'running': '处理：{done} / {total}',
        'started': '开始处理 {count} 张；来源：{source}',
        'output_log': '输出：{path}',
        'stop_requested': '收到停止请求；未开始的图片不会被误记为失败。',
        'progress_ok': '[{done}/{total}] 成功 {filename}',
        'progress_fail': '[{done}/{total}] 测量失败（TXT 保留） {filename}：{reason}',
        'finished_status': '成功 {success}/{total}，失败 {failed}',
        'cancelled_status': '已停止：成功 {success}，失败 {failed}，已处理 {completed}/{total}',
        'finished_log': 'TXT：{path} / 耗时 {seconds} 秒',
        'errors_log': '详细日志：{path}',
        'partial_title': '处理完成（含失败）',
        'partial_body': '成功 {success}，失败 {failed}；TXT 已保留失败图片行。\n{path}',
        'done_title': '完成',
        'done_body': '成功 {success} 张。\n{path}',
        'cancelled_title': '用户停止',
        'cancelled_body': '任务已停止，已处理 {completed}/{total} 张。\n未开始的图片不会记为失败。\n{path}',
        'fatal_status': '运行失败',
        'fatal_title': '错误',
        'fatal_log': '运行失败：{reason}',
        'sidecar_title': '图片计算结果日志',
        'sidecar_total': '输入图片：{count}',
        'sidecar_success': '成功：{count}',
        'sidecar_failed': '失败：{count}',
        'sidecar_cancelled': '用户取消：{cancelled}',
        'yes': '是',
        'no': '否',
    },
    'ja': {
        'title': 'FindsBlur 単独計算ツール v1.3.1',
        'headline': 'FindsBlur 単独計算ツール',
        'subtitle': 'IJG 8c · 固定ネイティブパラメータ · JPG / JPEG / BMP',
        'language': '表示言語 / 语言：',
        'source_section': '① 画像の入力元',
        'folder_mode': 'フォルダー（初期設定）',
        'single_mode': '画像1枚',
        'browse': '参照...',
        'folder_help': '初期設定：フォルダー内の全画像を読み込みます（サブフォルダーを含む）',
        'single_help': '指定した画像1枚のみを計算します',
        'output_section': '② TXT保存先とファイル名',
        'run_section': '③ 計算の実行',
        'start': '計算開始',
        'stop': '停止',
        'workers': '並列処理数：',
        'log_heading': '実行ログ',
        'calcdebug_section': '④ CalcDebug・中間画像の保存',
        'calcdebug_enable': 'CalcDebug（各処理段階の画像を保存・初期設定OFF）',
        'calcdebug_help': '空欄の場合：TXT保存先の CalcDebug フォルダーへ出力。画像ごとに別フォルダー',
        'calcdebug_select_dir': 'CalcDebug 保存フォルダーを選択',
        'calcdebug_bad_path': 'CalcDebug の保存先はフォルダーではありません：{path}',
        'calcdebug_started': 'CalcDebug 有効：保存先 {path}',
        'calcdebug_saved': 'CalcDebug 中間画像・診断結果：{path}',
        'ready': '準備完了',
        'intro_log': '計算に失敗した画像も省略せず、「ファイル名 ブレ度合測定に失敗しました。」と記録します。',
        'folder_dialog': '画像フォルダーを選択',
        'image_dialog': '画像を1枚選択',
        'image_type': '画像',
        'all_files': 'すべてのファイル',
        'save_dialog': '計算結果TXTの保存先',
        'found': '{count}枚の画像が見つかりました：{filename}{more}',
        'more': ' ほか',
        'input_error_title': '入力エラー',
        'choose_txt': '拡張子が .txt の出力ファイル名を指定してください。',
        'confirm_title': '上書きの確認',
        'confirm_overwrite': '既に存在するファイルを上書きしますか？\n{path}',
        'running': '処理中：{done} / {total}',
        'started': '{count}枚の処理を開始しました。入力元：{source}',
        'output_log': '出力先：{path}',
        'stop_requested': '停止を受け付けました。未着手の画像は計算失敗として扱いません。',
        'progress_ok': '[{done}/{total}] 成功 {filename}',
        'progress_fail': '[{done}/{total}] 計算失敗（TXTに記録） {filename}：{reason}',
        'finished_status': '成功 {success}/{total}、失敗 {failed}',
        'cancelled_status': '中止：成功 {success}、失敗 {failed}、処理済み {completed}/{total}',
        'finished_log': 'TXT：{path} / 処理時間 {seconds} 秒',
        'errors_log': '詳細ログ：{path}',
        'partial_title': '処理完了（一部失敗）',
        'partial_body': '成功 {success}枚、失敗 {failed}枚。失敗画像の行もTXTに保存しました。\n{path}',
        'done_title': '完了',
        'done_body': '{success}枚の計算が完了しました。\n{path}',
        'cancelled_title': '処理を中止しました',
        'cancelled_body': '処理済み {completed}/{total}枚。未着手の画像は失敗として記録しません。\n{path}',
        'fatal_status': '処理エラー',
        'fatal_title': 'エラー',
        'fatal_log': '処理エラー：{reason}',
        'sidecar_title': '画像計算結果ログ',
        'sidecar_total': '入力画像：{count}',
        'sidecar_success': '成功：{count}',
        'sidecar_failed': '失敗：{count}',
        'sidecar_cancelled': 'ユーザーによる中止：{cancelled}',
        'yes': 'はい',
        'no': 'いいえ',
    },
}


# The fixed Japanese failure text is NOT a localized UI string. It belongs
# to the official TXT wire format and must never change with GUI language.
CORE_ERRORS_JA = (
    ('请选择或填写图片文件夹/图片路径。', '画像フォルダーまたは画像のパスを入力してください。'),
    ('找不到图片文件夹：', '画像フォルダーが見つかりません：'),
    ('请输入存在的 JPG/JPEG/BMP 文件路径：', '有効なJPG/JPEG/BMPファイルを指定してください：'),
    ('无效的图片模式：', '画像選択モードが無効です：'),
    ('没有找到 JPG、JPEG 或 BMP 图片。', 'JPG/JPEG/BMP画像が見つかりません。'),
    ('两个子文件夹存在同名图片，官方 TXT 无法区分：', '別々のサブフォルダーに同名画像があるため、TXTで区別できません：'),
    ('请选择图片。', '画像を指定してください。'),
    ('并行数量必须为 1～4。', '並列処理数は1～4にしてください。'),
    ('缺少本机已编译的 IJG8c 解码器：', 'ローカルにビルドしたIJG8cデコーダーが見つかりません：'),
    ('输出名称必须以 .txt 结尾。', '出力ファイル名は .txt で終わる必要があります。'),
    ('输出文件不能覆盖输入图片。', '出力ファイルで入力画像を上書きできません。'),
    ('原生参数自检不通过：', 'ネイティブパラメータの自己診断に失敗しました：'),
    ('，预期 ', '、期待値 '),
    ('IJG 8c 不接受额外 Image.open 参数。', 'IJG 8cでは追加のImage.open引数を使用できません。'),
    ('IJG 8c 解码超时：', 'IJG 8cのデコードがタイムアウトしました：'),
    ('IJG 8c 解码失败：', 'IJG 8cのデコードに失敗しました：'),
    ('IJG 8c 没有返回尺寸：', 'IJG 8cから画像サイズが返されませんでした：'),
    ('图片尺寸不受支持：', '未対応の画像サイズです：'),
    ('IJG 8c RGB 缓冲区损坏：', 'IJG 8cのRGBバッファーが不正です：'),
    ('CalcDebug 文件夹路径不能与 TXT 文件路径相同。', 'CalcDebugのフォルダーとTXTファイルに同じパスは指定できません。'),
    ('未返回四个有效数值。', '有効な4項目の数値が得られませんでした。'),
    ('内部错误：输出记录数与输入图片数不同。', '内部エラー：出力行数と入力画像数が一致しません。'),
)


def tr(lang: str, key: str, **params: Any) -> str:
    """Translate a presentation key; keep technical filename/path values as-is."""
    table = TRANSLATIONS[lang if lang in TRANSLATIONS else 'zh']
    return table[key].format(**params)


def localize_error(message: str, lang: str) -> str:
    """Translate known UI-facing engine messages; keep unknown traceback data."""
    if lang != 'ja':
        return message
    for source, destination in CORE_ERRORS_JA:
        if source in message:
            message = message.replace(source, destination)
    return message
