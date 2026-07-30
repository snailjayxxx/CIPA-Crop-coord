from __future__ import annotations

TEXT = {
    "zh": {
        "browse":"浏览…","folder":"选择文件夹","save":"选择保存文件","image":"选择图片","image_filter":"图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp);;所有文件 (*)","image_filter_short":"图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)",
        "preview":"在图片上拖动选择范围","preview_help":"左键拖动选择；滚轮或 +/- 缩放。已有有效数值时自动框出对应范围。","fit":"适应窗口","range":"当前范围：x={x}, y={y}, 宽={w}, 高={h}","whole":"当前范围：整张图片","preview_fail":"无法打开预览",
        "x":"x","y":"y","w":"宽","h":"高","pick":"在图片上选择…","match_group":"匹配范围与精度","template":"sample 有效范围：","template_hint":"宽/高为 0：使用整张 sample","search_mask":"被遍历图片遮蔽范围：","search_note":"每边遮蔽比例；16.67% = 搜索中央约 2/3 × 2/3","choose_target":"选择一张有代表性的被遍历图片","search_help":"拖框后按四边距离平均值换算为每边遮蔽百分比。","edge":"sample 边缘屏蔽：","similarity":"最低相似度：",
        "paths":"文件位置","sample":"sample 图片：","input":"遍历文件夹（含子文件夹）：","output":"裁切图片保存文件夹：","output_group":"输出设置","quality":"JPEG 保存质量：","name_note":"命名：1/100s + abc.jpg → 1_100_abc.jpg；无 EXIF 时使用 unknown_。",
        "start":"开始处理","cancel":"取消","debug":"Debug 模式","debug_tip":"保存压缩后的二值化、遮蔽范围、裁切框和识别点参考图","threads":"并行线程：","threads_tip":"大图内存占用高，默认 2 线程。","wait_cancel":"正在等待当前并行任务处理完毕后取消…",
        "missing":"信息不完整","select_missing":"请选择：{items}","finished":"处理结束：成功 {ok}，未达阈值 {skip}，失败 {fail}。","done":"处理完成","done_body":"共 {total} 张\n成功：{ok}\n未达阈值：{skip}\n失败：{fail}\n\n保存位置：{path}{debug}","debug_line":"\nDebug：{path}","failed_title":"处理未完成","cancelled":"处理已取消。已经保存的文件不会被删除。",
        "center_group":"从图片中心裁切","fixed":"固定像素","ratio":"原图比例","ratio_label":"宽、高均取原图的：","ratio_ph":"例如 1/3、1/4 或 0.5","center_note":"裁切区域始终居中；文件名使用“快门速度_原文件名”。",
        "csv":"CSV 保存位置：","csv_filter":"CSV 文件 (*.csv)","coord_note":"CSV 三列：文件名、x坐标、y坐标。坐标是 sample 中心点在被遍历图片中的像素位置；未匹配图片坐标为空。",
        "tab1":"① 相似区域裁切","tab2":"② 中心裁切","tab3":"③ 坐标导出","status":"支持 JPG / PNG / BMP / TIFF / WebP；递归遍历子文件夹。","language":"界面语言：","running":"仍在处理","running_msg":"任务仍在运行。请先取消并等待当前图片处理结束，再关闭程序。",
        "range_out":"指定范围不在图片内","folder_missing":"图片文件夹不存在：{path}","read_fail":"无法读取图片：{path}","encode_fail":"无法编码输出图片：{path}","template_small":"屏蔽边缘后模板过小，请减小屏蔽比例或扩大模板范围","search_small":"搜索范围小于有效模板范围","edge_crop":"匹配位置靠近边缘，无法裁出完整 sample 范围","ratio_format":"比例请输入 1/3、1/4 或 0.5","ratio_range":"裁切比例必须大于 0 且不超过 1","fixed_positive":"固定像素模式下，宽度和高度必须大于 0","fixed_large":"指定裁切像素大于原图","skip":"跳过（相似度 {score:.3f}）：{name}","ok_score":"完成（相似度 {score:.3f}）：{name}","ok":"完成：{name}","fail":"失败：{name} — {error}","record":"已记录（相似度 {score:.3f}）：{name}","below":"未达阈值（{score:.3f}）：{name}","csv_header":("文件名","x坐标","y坐标"),
    },
    "ja": {
        "browse":"参照…","folder":"フォルダーを選択","save":"保存先を選択","image":"画像を選択","image_filter":"画像 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp);;すべてのファイル (*)","image_filter_short":"画像 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)",
        "preview":"画像上でドラッグして範囲を選択","preview_help":"左ボタンでドラッグして選択。ホイールまたは +/- で拡大・縮小します。有効な既存値は自動表示します。","fit":"ウィンドウに合わせる","range":"現在の範囲：x={x}, y={y}, 幅={w}, 高さ={h}","whole":"現在の範囲：画像全体","preview_fail":"プレビューを開けません",
        "x":"x","y":"y","w":"幅","h":"高さ","pick":"画像上で選択…","match_group":"一致範囲と精度","template":"sample 有効範囲：","template_hint":"幅/高さが 0：sample 全体を使用","search_mask":"対象画像の除外範囲：","search_note":"各辺の除外率。16.67% = 中央のおよそ 2/3 × 2/3 を検索","choose_target":"代表的な対象画像を1枚選択","search_help":"ドラッグ範囲から四辺までの距離平均を各辺の除外率へ換算します。","edge":"sample 周辺除外：","similarity":"最低類似度：",
        "paths":"ファイル位置","sample":"sample 画像：","input":"対象フォルダー（サブフォルダー含む）：","output":"切り抜き画像の保存先：","output_group":"出力設定","quality":"JPEG 保存品質：","name_note":"命名：1/100s + abc.jpg → 1_100_abc.jpg。EXIF がない場合は unknown_。",
        "start":"処理開始","cancel":"キャンセル","debug":"Debug モード","debug_tip":"二値化、除外範囲、切り抜き枠、検出点の圧縮参考画像を保存します","threads":"並列スレッド：","threads_tip":"高解像度画像はメモリを多く使用します。既定値は 2。","wait_cancel":"実行中の並列処理が終了してからキャンセルします…",
        "missing":"入力情報が不足しています","select_missing":"選択してください：{items}","finished":"処理完了：成功 {ok}、しきい値未満 {skip}、失敗 {fail}。","done":"処理完了","done_body":"合計 {total} 枚\n成功：{ok}\nしきい値未満：{skip}\n失敗：{fail}\n\n保存先：{path}{debug}","debug_line":"\nDebug：{path}","failed_title":"処理が完了していません","cancelled":"処理をキャンセルしました。保存済みファイルは削除されません。",
        "center_group":"画像中心から切り抜き","fixed":"固定ピクセル","ratio":"元画像比率","ratio_label":"幅・高さを元画像の比率で指定：","ratio_ph":"例：1/3、1/4、0.5","center_note":"切り抜き範囲は常に中央です。ファイル名は「シャッター速度_元ファイル名」です。",
        "csv":"CSV 保存先：","csv_filter":"CSV ファイル (*.csv)","coord_note":"CSV は「ファイル名、x座標、y座標」の3列。座標は対象画像内の sample 中心位置で、不一致画像は空欄です。",
        "tab1":"① 類似領域切り抜き","tab2":"② 中央切り抜き","tab3":"③ 座標出力","status":"JPG / PNG / BMP / TIFF / WebP 対応。サブフォルダーまで再帰処理します。","language":"表示言語：","running":"処理中です","running_msg":"処理が実行中です。先にキャンセルし、現在の画像処理終了後に閉じてください。",
        "range_out":"指定範囲が画像内にありません","folder_missing":"画像フォルダーが存在しません：{path}","read_fail":"画像を読み込めません：{path}","encode_fail":"出力画像をエンコードできません：{path}","template_small":"周辺除外後のテンプレートが小さすぎます。除外率を下げるか有効範囲を広げてください","search_small":"検索範囲が有効テンプレートより小さいです","edge_crop":"一致位置が画像端に近いため sample 全体を切り出せません","ratio_format":"比率は 1/3、1/4、0.5 のように入力してください","ratio_range":"切り抜き比率は 0 より大きく 1 以下にしてください","fixed_positive":"固定ピクセルモードでは幅と高さを 0 より大きくしてください","fixed_large":"指定した切り抜きサイズが元画像より大きいです","skip":"スキップ（類似度 {score:.3f}）：{name}","ok_score":"完了（類似度 {score:.3f}）：{name}","ok":"完了：{name}","fail":"失敗：{name} — {error}","record":"記録済み（類似度 {score:.3f}）：{name}","below":"しきい値未満（{score:.3f}）：{name}","csv_header":("ファイル名","x座標","y座標"),
    },
}


def tr(lang: str, key: str, **kwargs):
    value = TEXT["ja" if lang == "ja" else "zh"][key]
    return value.format(**kwargs) if isinstance(value, str) else value
