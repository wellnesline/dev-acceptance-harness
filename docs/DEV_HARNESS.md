# 新規開発・機能改修のハーネス

採用は **OpenSpec + 既存 LangGraph + 会話エージェント + 独立テストとレビュー**。

新規アプリ・新規パイプラインでは、n8n + Dify を視覚的な構築・実行観測層として使う運用を想定している（既存システムの全面移行は要件ではない）。設定と PoC の入口は、関連リポジトリ n8n-dify-workflow-viewer（`integrations/visual_workflow/` に配置）の README。当該新規部分の manifest を `policy.py` で検査する固定テストを change 専用 profile に含める。適用フレームワークの省略には、既存の明示的なユーザー例外と理由・指示参照が必要。OpenSpec/LangGraph の既存受入条件は維持する。

新規アプリ・新規パイプラインの profile には、ジョブ・AI・プログラムを結ぶ SVG 工程図 `inspection_view` と匿名操作証跡、およびコーディング委譲の既定 `coding_delegation` を必須とする。gate は元 snapshot と図・証跡の一致を検査する。既存 profile は固定された変更名で遡及免除し、別 change で再利用した場合は新契約を適用する。他プロジェクトは共通 policy の `--future-defaults` を change 専用の固定テストから呼ぶ。詳細は n8n-dify-workflow-viewer の README。

適用判断は運用側の方針文書（このリポジトリには含めない）に従う。新規開発・機能改修・パイプライン構築には既定で適用し、適用可否・構成選択に迷う場合は人間に確認する。

OpenSpec 1.14.0 の実 upstream CLI を `dev_harness/tools` へローカル導入した。root `openspec/` が実機能変更の仕様置き場（このリポジトリには含めない）、`dev_harness/project/` は本番へ import しない隔離サンプルである。global 設定は上書きしない。

## 比較と選定

| 候補 | 得意な用途 | 判断 |
|---|---|---|
| OpenSpec | 変更ごとのproposal・差分仕様・design・tasks、CLIでの状態取得と検証 | 変更単位に使え、LangGraphへ機械証跡を渡せるため採用 |
| GitHub Spec Kit | constitutionから仕様・計画・taskへ進める包括的な開発手順 | 新規プロジェクトには有力。ここでは変更単位のOpenSpecを選択 |
| Superpowers | coding-agent向けの設計・テスト・レビューskills | 明示的なCLI契約を先に整えるため保留 |

一次資料: [OpenSpec CLI](https://github.com/Fission-AI/OpenSpec/blob/main/docs/cli.md)、[Spec Kit](https://github.com/github/spec-kit)、[Superpowers](https://github.com/obra/superpowers)。調査日は作成時点。将来のバージョンではCLI仕様が変わるため、実導入はlockfileの1.14.0に固定する。

## 分担
新規開発の受渡しは実n8n/Difyに対応するログイン不要・閲覧専用の外部URLを必須とする。`public_view` にsnapshotと匿名HTTP証跡を記録し、共通policyが元export・snapshot・取得SHA256の一致を検査する。新規profileは `workflow_scope` と `workflow_manifest_paths` を必須とし、gateが独立テストの前に自動検査する。`dev_harness/workflow_delivery_policy.json` に記録した変更前の既存 profile（この公開版では例 2 件のみ）は維持し、既存維持を理由に新規profileを免除しない。

- OpenSpec: 要件とシナリオ、変更設計、taskを管理し、公式CLIで構造と進捗を検証する。
- LangGraph: jobの永続状態、担当への委譲、提出待ち、検証、差戻し、独立レビュー、完了を管理する。
- 会話エージェント: 仕様を具体化し、対象の既存コードを調べて実装する。
- `dev_harness/gate.py`: 公式validate/status/applyと固定テストを実行し、対象コード等の実行前後ハッシュを確かめる。

OpenSpecのvalidate成功だけでは開発完了にならない。unchecked task・空task・テスト失敗・実行中の入力変更は拒否する。profileはchangeとworkspaceに固定し、sampleテストで本番変更を合格にしない。

## 使い方

PowerShellでプロジェクトルートから実行する。

```powershell
npm.cmd ci --prefix dev_harness/tools --ignore-scripts --no-audit --no-fund
.\.harness\venv\Scripts\python.exe dev_harness/openspec.py new change your-feature
.\.harness\venv\Scripts\python.exe dev_harness/openspec.py instructions proposal --change your-feature --json
.\.harness\venv\Scripts\python.exe dev_harness/openspec.py status --change your-feature --json
```

公式instructionsに従いproposal→specs/design→tasksを作成し、未確定要件を解決する。テストを先に用意して意味のある失敗を確認し、実装して成功を確認する。`dev_harness/profiles.json`にそのchange専用の実装ファイル・テスト・固定runnerを登録する。taskを実作業に基づいて完了にしてからgateを実行する。

```powershell
.\.harness\venv\Scripts\python.exe -X utf8 dev_harness/gate.py --change <change-id> --profile <profile-id>
.\.harness\venv\Scripts\python.exe -X utf8 dev_harness/gate.py --sample --change safe-relative-output --profile sample-artifact-path
```

gateは標準出力にJSONだけを返す。`status=passed`かつexit0が機械検証成功。失敗はexit2。`artifact_hashes`はspec、設定、公式schema、lockfile、登録実装・テストと、使った検証プログラムの版（`verifier-pin`）を含む。job の中では pin の写しの gate が `--root` でワークスペースを指して実行される（下の「検証プログラムの固定」）。API本文やテストの生stdoutをレポートへ入れない。

OpenSpec実行本体の`dist`も、対象ディレクトリ内1000ファイル・10MBを上限としたtree digestを保存する。unittestは登録ファイルだけを実行し、実行件数0を失敗にする。pytestも対象0件は成功扱いしない。

既存LangGraphの開発adapterは提出JSONを読むだけでなくgateを再実行し、source hashを照合する。対象profileの範囲が十分か、要求が実際に満たされたかは独立reviewで確認する。未登録のコードまで検証済みとは扱わない。

LangGraphの要求では `workflow: software-development` を選び、成果物に `kind: openspec`、`change`、`profile`、保存したgate JSONの相対`path`を指定する。汎用の`status: passed` JSONでこの検証を代用しない。親の既存job CLIを利用するため、別の永続ジョブ基盤は増やさない。

## 検証プログラムの固定

これまでは、開発 job の証跡に共通の検証プログラム（gate.py、policy.py など）のハッシュが入り、LangGraph の fingerprint にも workflow のコードと登録台帳が入っていた。このため、誰かが共通部分を直すと、無関係な進行中の job まで古くなっていた。現在は、job ごとに検証プログラムを版で固定する。

### 仕組み

- `job start` が、共通の検証部分を読み取り専用の写し `.harness/verifier-pins/<digest>/files/` に保存し、job の状態に `verifier_pin` を記録する。`<digest>` は `manifest.json`（全ファイルの SHA256 の一覧）の SHA256。同じ版なら1つの写しを共有する。
- 固定する範囲（`ops_harness/verifier_pins.py` の一覧）: `dev_harness/gate.py`、`unittest_runner.py`、`workflow_delivery_policy.json`、`tools/package.json`・`package-lock.json`・`tools/node_modules` 一式（OpenSpec 本体・schemas・依存）、`integrations/visual_workflow/policy.py`・`viewer.py`、`ops_harness/*.py`（LangGraph の workflow 自体）、`config/ops_harness.json`、`scripts/qa_memory_md_lint.py`。
- job のそれ以降の操作（status / submit / review / continue / cancel / gate / pin）は、`ops_harness/workflow_cli.py` がチェックポイントから pin ID を読み、その写しの中のコードで実行する。gate の再実行、提出時の照合、独立レビュー後の再検証も、写しの gate・runner・policy・OpenSpec で行う。
- pin した job の fingerprint は「pin ID + LangGraph ライブラリの版」。共通部分や workflow のコードを更新しても、進行中の job は止まらない。
- 自分の source_paths / test_paths / change のファイル / 自分の profile エントリ / `openspec/config.yaml`（OpenSpec がワークスペースから読む）は、今までどおり証跡に入る。変えれば、その job は差し戻される。
- 抜け道を作らないための仕組み:
  - pin ID は開始時の状態にだけ記録し、差し替える経路は無い。
  - 別の pin や本体のコードで job を操作しようとすると拒否される。
  - 振り分け側（リポジトリのコード）が、写しのコードを動かす前に写し全体を照合する。ファイルの変更・追加・削除（`__pycache__` や、最上位に置いたモジュールを含む）が1つでもあれば、submit / review / continue / gate を拒否し、`job pin` は intact: false と表示する。その job は合格できないので、cancel して出し直す。status と cancel は写しを使わずに動く。
  - 照合した後に写しが書き換えられた場合も、検証の直前に写しの中でもう一度全体を照合し、`verifier-pin` の検査を不合格として記録する。
- 新しい版を使えるのは新しい job だけ。古い版の job を新しい版で検証し直したいときは、その job を cancel して出し直す。
- pin 導入前に始まった job は、導入前のランタイムを凍結した固定の pin（`LEGACY_RUNTIME_PIN`）で動く。

### 作業者の手順

```powershell
.\.harness\venv\Scripts\python.exe scripts/ops/harness.py job start --job-id <id> --request <request.json>
.\.harness\venv\Scripts\python.exe scripts/ops/harness.py job gate <id>     # pin の gate で証跡を作り、artifact の path に保存して sha256 を表示
.\.harness\venv\Scripts\python.exe scripts/ops/harness.py job submit <id> --submission <submission.json>
.\.harness\venv\Scripts\python.exe scripts/ops/harness.py job pin <id>      # pin ID・保存場所・全ファイルの照合結果
```

job を始める前の試し実行は、今までどおり `dev_harness/gate.py` を直接実行してよい（ワークスペースの現在の版で実行される）。job を始めてからは、提出する gate JSON を `job gate` で作る。`job status` の `verifier_pin` と gate JSON の `verifier.pin` で、どの版で検証したかを確認できる。

### 共通部分を更新する手順（専任の担当だけ）

1. 変更は OpenSpec の change と change 専用の profile で行う。固定テストは `dev_harness/tests/test_verifier_pins.py` と開発ハーネスの既存テスト一式。
2. 共通部分を更新しても、進行中の pin 付き job は影響を受けない。更新した後に始めた job から、新しい版が使われる。
3. `ops_harness/workflow_cli.py`（振り分け）、`pinned_entry.py`、`verifier_pins.py` は、すべての job の入口になる。互換性を保ったまま変更し、変更後に既存の pin 付き job で `job status` と `job pin` が通ることを確認する。
4. 写しは自動では削除しない。消すのは、その pin を使う job がすべて終わった後だけ。

### 共通部分に入っている仕事ごとの検査（棚卸し）

| 場所 | 中身 | 方針 |
|---|---|---|
| `dev_harness/workflow_delivery_policy.json` の `historical_profiles` / `pre_graph_defaults_profiles` | 既存維持の免除（この公開版では例 2 件） | 新規の追加はしない |
| `gate.py` / `policy.py` / `viewer.py` | 仕事に固有の名前や条件は無い（汎用の検査だけ） | 現状のまま |

仕事ごとの検査は、その仕事の profile の `test_paths` に置く。共通部分に足すと全員の新しい job の pin が変わり、全員の検証に影響する。

## オーケストレーターへの指示

> 〔機能・改修内容〕をOpenSpecとLangGraphで実装してください。root openspecに変更を作り、既存仕様とコードを確認して要件・シナリオ・design・tasksを具体化してください。対象に対応した独立テストを用意し、実装後はchange専用profileで公式OpenSpec検証とテストを実行してください。成果物をLangGraphへ提出し、独立reviewと再検証まで完了してください。既存の許可範囲を継承し、課金・公開など未許可の外部操作が必要な場合だけ具体化後に確認してください。

## 検証記録

サンプルの成功だけを、本番システムや全機能の検証成功へ拡大しない。

再現用の `python dev_harness/verify_sample.py` は隔離sampleのspec・task・実装を一時的に壊し、不合格を確認して元bytesへ戻す。sampleを他の処理が参照していない時だけ単独実行する。本番ファイルは変更しない。不正仕様・未完了task・壊れた実装の3拒否と復元後成功を確認する。

Nodeはupstream要件の20.19.0以上が必要。ローカルwrapperはtelemetryとupdate checkを無効化する。仕様書生成は会話エージェントが行い、OpenSpecを導入しただけでLLMが常駐実行されるわけではない。
