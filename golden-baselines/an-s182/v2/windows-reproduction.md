# Windows再現手順 v2

## 先に行う検証

1. 指定branchと固定commitを取得し、`python scripts/verify_package.py`を実行する。
2. `python scripts/verify_golden_baseline_v2.py`を実行する。
3. `material-map.json`の全素材で`reproduction_source_status=verified`を確認する。
4. WindowsのCapCut、フォント、Holiday Twist音声、効果音の利用可否を報告する。
5. 1つでも不足・不一致があれば、似た素材や音声へ置き換えずHOLDにする。

## 再現順序

1. 1080×1920、30fpsの新規CapCutプロジェクトを作る。
2. `timeline.json`どおりに10カットをフレーム単位で配置する。
3. C4は`IMG_3958.MOV`の0.0–2.0秒と2.0–3.0秒を使う。
4. C6は`IMG_3893.MOV`の0.0–2.833秒を3.0秒へ合わせる。
5. 各カットの`must_show`と`must_not_show`を確認する。別製品や向きが逆の素材を使わない。
6. 字幕原文、改行、時間、位置、白太字、黒縁を`caption-style.json`どおりに再現する。
7. C5/C6の1フレーム字幕重複は現行Mac正解見本の一部としてそのまま再現し、無断修正しない。
8. TTS 10個をHoliday Twistで配置し、元動画音声を全ミュート、BGMなし、効果音5個とする。
9. 構造検証後、人が映像・字幕・音声を通しで確認する。

## 停止条件

- v2の固定commit、package verifier、v2 verifier、全テストがPASSしていない。
- 素材、sidecar、Holiday Twist、フォント、効果音のいずれかが未確認。
- C4が`IMG_3958.MOV`以外、またはC6が`IMG_3893.MOV`以外になっている。
- 編集開始の明示承認がない。
- 書き出し、クラウド保存、公開、外部送信、課金について別承認がない。

WindowsでのPASSは構造と環境の準備完了を示します。Mac同等品質の最終判定には、人による映像・字幕・音声の比較が必要です。
