# dev-acceptance-harness

An acceptance gate for spec-driven changes: OpenSpec validation, task completion, fixed tests and before/after hashing, all re-run by the gate instead of trusted from the author.

新規開発・機能改修を OpenSpec の仕様と LangGraph の job に結びつけ、「仕様が検証を通り、task が実作業で完了し、固定テストが成功し、検証中に入力が変わっていない」ことを機械的に確かめる受け入れゲートです。公開用に整理したサンプル実装です。

## 概要

AI に実装を任せると、「仕様書の形式が通った」「テストが通ったと報告された」だけで完了扱いになりがちです。このゲートは、提出された JSON を信じず、公式 OpenSpec CLI と固定テストをその場で再実行します。対象 change ごとに実装ファイル・テスト・実行方法を `profiles.json` で固定し、別の change や隔離サンプルの成功で本番変更を合格にできないようにしています。

## 主な機能・設計のポイント

- **`gate.py`**: 公式の `validate` / `status` / `apply` を実行し、未チェックの task・task が空・テスト失敗・テスト 0 件を不合格にします。結果は標準出力に JSON だけを返し、`status=passed` かつ終了コード 0 のときだけ成功です（失敗は終了コード 2）。
- **実行前後のハッシュ照合**: 仕様・設定・OpenSpec 本体（`dist` の tree digest）・lockfile・登録した実装とテストのハッシュを実行の前後で比べ、実行中に入力が変わったら不合格にします。
- **profile 固定**: change と workspace を profile に結びつけます。`sample` フラグで隔離サンプルと本番を区別し、サンプルの合格を本番に流用できません。
- **0 件テストを成功にしない**: `unittest_runner.py` は指定ファイルだけを実行し、実行件数 0 を失敗にします。pytest も対象 0 件は成功扱いにしません。
- **検証プログラムの版固定（verifier pin）**: job ごとに検証側のコードを読み取り専用の写しとして固定し、gate・提出時の照合・レビュー後の再検証をその写しで行います。共通部分の更新で進行中の job が古くならず、写しの改変は不合格になります。
- **公開閲覧ビューの契約**: 新規の profile には、元の n8n / Dify export と一致する閲覧専用ビュー（`public_view`）と、ジョブ → 担当 → 結果を結ぶ工程図（`inspection_view`）を要求します。この検査は `n8n-dify-workflow-viewer` の `policy.py` を呼びます。遡及を免除する履歴は `workflow_delivery_policy.json` に凍結します（公開版の中身は例 2 件のみ）。
- **隔離サンプル**: `dev_harness/project/` に、仕様 → 失敗するテスト → 実装 → 成功、の流れと、不正な仕様・未完了 task・壊れた実装の 3 種類の拒否を再現するサンプルがあります（`verify_sample.py`）。

## ディレクトリ構成

```
dev_harness/
  gate.py                         受け入れゲート本体
  openspec.py                     ローカル固定版 OpenSpec CLI のラッパー
  unittest_runner.py              登録ファイルだけを実行する unittest ランナー
  profiles.json                   change 専用 profile の登録（合成サンプル）
  workflow_delivery_policy.json   遡及免除の凍結リスト（合成サンプル）
  verify_sample.py                隔離サンプルでゲートの拒否を再現
  project/                        隔離サンプル（OpenSpec の change、実装、テスト）
  tests/                          gate / profile / verifier pin のテスト
  tools/package.json              OpenSpec CLI の固定版（lockfile 付き）
docs/DEV_HARNESS.md               設計の考え方と使い方
```

## 動かし方

必要なもの: Python 3.10 以上、Node.js と npm（OpenSpec CLI の導入用）、`pytest`、および後述の他リポジトリ。

```powershell
npm.cmd ci --prefix dev_harness/tools --ignore-scripts --no-audit --no-fund
python dev_harness/openspec.py new change your-feature
python dev_harness/openspec.py status --change your-feature --json
python -X utf8 dev_harness/gate.py --change <change-id> --profile <profile-id>
python -X utf8 dev_harness/gate.py --sample --change safe-relative-output --profile sample-artifact-path
python dev_harness/verify_sample.py
```

環境変数・外部サービスの鍵は使いません。

## 制限事項（閉包）

- **同梱していない依存**（3 件）: `ops_harness`（`ops-acceptance-harness` リポジトリ）、`integrations`（`n8n-dify-workflow-viewer` リポジトリ。`visual_workflow/` を `integrations/visual_workflow/` として置く）、`pytest`。ゲートと verifier pin は、この 2 リポジトリを同じワークスペースに重ねた構成を前提にしています。単独では `gate.py` は動きません。
- OpenSpec 本体（`@fission-ai/openspec`）は `dev_harness/tools/package.json` に版を固定していますが、`node_modules` は同梱していません。
- `profiles.json` と `workflow_delivery_policy.json` は合成サンプルです。実在の change 名・パスは含みません。
- 設計文書が参照する運用側の方針文書、およびワークスペース直下の `openspec/` は同梱していません。
- 本ゲートが保証するのは、登録した実装・テストの範囲です。要求がテスト範囲に十分対応しているかは、独立したレビューで確認する前提です。

## ライセンス

All rights reserved. 閲覧目的で公開しています。詳細は LICENSE を参照。
