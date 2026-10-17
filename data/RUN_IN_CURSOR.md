# 在 Cursor 运行两份 CSV 生成脚本

目标：生成 `normal.csv` 和 `disruption.csv`，每份 12,000 行。
这些命令只操作本地文件，不会 push GitHub，也不会修改远程 main。
本分支发布数据及生成工具；不包含完整 dashboard 网页应用。

## 1. 打开本地项目

Cursor → File → Open Folder，选择你克隆或下载的仓库根目录。
左侧应该看到 `data/`，其中包含 `generate_data.py`、`station_anchors.json`、
`README.v5.md` 和 `_qc_snapshot.py`。请保留整个 `data/` 文件夹。

脚本需要 Python 3.9+ 和可用的 IANA 时区数据库，无需安装 Python 第三方包。
完整应用存在时使用 `app/qc.py`；本数据分支没有该文件时，自动使用字节完全
相同的 `_qc_snapshot.py`，并验证其 SHA256。来源和哈希见 `README.md`。

## 2. 打开终端

Cursor 菜单 Terminal → New Terminal。确认终端当前目录是刚打开的仓库根目录。
如果不是，先用 `cd` 进入你自己的仓库位置。无需使用任何他人的个人电脑路径。

## 3. 一次生成两份数据

```sh
python3 data/generate_data.py
```

等待命令结束、终端提示符重新出现。程序先构造和验证数据，再备份旧的
生成文件并替换。不要在运行中关闭窗口。若有报错，保留完整终端输出，不要
跳过检查或手工删除文件重试。

成功后 `data/` 顶层只有两份场景 CSV：

- `normal.csv`：所有导出库存 6–24，运营警告与三种统计候选事件均为零。
- `disruption.csv`：出现 Empty、Full、Low、High 及统计规则示例。

JSON、JSONL 和 Markdown 文件是设置、验证、代码说明和骑行审计文件，
不是第三份场景数据集。旧 `edge_cases.csv` 和旧版输出会备份至输出目录旁的
`.dockwatch-data-backups/时间戳/`。备份文件夹不需要上传至 GitHub。

## 4. 查看验证结果与演讲位置

打开：

- `data/validation.json`：本次生成的实际检查结果。
- `data/demo_guide.md`：可演示的场景、站点、日期、钟点和预期现象。

运行独立检查；测试使用临时目录，不替换活跃 CSV：

```sh
python3 -m unittest discover -s data -p 'test_generate_data.py' -v
```

最后应显示 `OK`。测试数量和耗时以终端实际输出为准。检查也覆盖数据分支
不含 `app/` 时的检测器加载、快照完整性和完整应用检测器的优先级。

## 5. 与完整网页项目连接

**本数据分支不能单独启动网页。** 将两份 CSV、`stations.json` 和
`settings.json` 集成到你们完整 dashboard 项目的对应 `data/` 目录后，
按那个项目的说明重新启动后端。只刷新浏览器不能清除后端缓存。

如果完整项目提供 `app/testme.sh`，可在完整项目根目录运行该启动脚本；
不要在本分支中寻找不存在的网页文件。网页能否直接使用这些文件，要以该项目
实现的三列输入格式和配置接口为准。集成后应核对 Normal 和 Disruption
两种场景、数据版本及对应的验证结果。

## 6. 演讲检查顺序

1. Normal：选监测期某天的早高峰，库存随站点和时间变化，但没有库存警告。
2. 同一时间切到 Disruption：查看空站、满站、P2 及建议数量，与地图联动。
3. 按 `demo_guide.md` 的实际坐标进入 Analysis，展示越界、8 点同侧、6 点趋势。
4. 展示库存仍在 6–24 但有统计候选信号的站点：公司需要调查，不自动生成搬运数量。
5. 回到触发前一个服务日，验证序列规则要等最后一点出现才触发。

`Needs baseline review` 是审核状态，不是数据错误。不要为了演讲把未经审核的
基线自动批准；候选事件默认仍是 Exploratory。正常示例无候选事件不代表现实
运营永远无异常。这两份都是明确标注的合成演示数据。

## 可选：先生成到独立预览目录

```sh
python3 data/generate_data.py --output-dir /tmp/dockwatch-data-preview
```

预览不会自动进入网页。保持默认 seed 5300 和日期可复现发布数据；更改 seed
或日期后，使用重新生成并验证的演讲位置，不要继续使用旧版坐标。
