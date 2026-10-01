# 開発ハーネス導入計画

目的: 新規開発と機能改修の仕様・task・実装・独立検証を、実 upstream OpenSpec と LangGraph に接続する。

完了条件: 比較一次資料、専用 local dependency、公式 CLI による change 作成・仕様検証・task 状態取得、ローカル sample の RED→実装→GREEN、再現可能な検証コマンドを揃える。

検証方法: 課金・公開なし。sample は `dev_harness/project` 内だけで動かす。OpenSpec validator の失敗系、未完了 task 拒否、実コードの回帰試験を確認する。

状態: OpenSpec 1.14.0 を local npm 導入し、公式 wrapper・独立 gate・change 固定 profile を実装。隔離 sample は spec→RED→実装→GREEN を通り、不正仕様・未完了 task・壊れた実装の 3 拒否と復元後の成功を `verify_sample.py` で再現できる。LangGraph の software-development adapter（`ops_harness` 側）と接続する。