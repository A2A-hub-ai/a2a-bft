# A2A-BFT —— reproduce.sh 的薄封装（thin wrapper）
#
# 所有目标都只是转发到 ./reproduce.sh <stage>，不重复任何逻辑。
# 判定语义、串行约束、锁文件与退出码全部由 reproduce.sh 负责，
# 因此 `make verify` 与 `./reproduce.sh verify` 行为完全一致。
#
# 用 .RECIPEPREFIX 把配方前缀从 TAB 改成 '>'：Makefile 的 TAB 前缀在
# 跨编辑器/跨平台搬运时极易被转成空格而静默失效，改成可见字符可避免。
# 需要 GNU make >= 3.82。若本机没有 make，直接用 ./reproduce.sh 即可。

.RECIPEPREFIX = >
.DEFAULT_GOAL := verify

.PHONY: help verify doctor figures datasets install all full

help:
> @./reproduce.sh help

# 默认目标：8 审计 + 5 组负向测试（纯 CPU）
verify:
> @./reproduce.sh verify

# 先跑这个：报告本机能复现到哪一步
doctor:
> @./reproduce.sh doctor

figures:
> @./reproduce.sh figures

datasets:
> @./reproduce.sh datasets

install:
> @./reproduce.sh install

all:
> @./reproduce.sh all

# 需 2×80GB GPU + 78GB 权重；前置条件不满足时直接中止
full:
> @./reproduce.sh full
