# AFS — FGO 自动战斗脚本

基于图像识别的《Fate/Grand Order》安卓模拟器自动化战斗脚本：OpenCV 模板匹配识别场景 → minitouch 触控注入 → 配置驱动的状态机循环执行。

> ⚠️ 免责声明：本工具用于自动化重复刷图，使用前请自行确认符合游戏用户协议；封号风险自负。本项目仅供个人学习研究使用。

## 功能

- 8 状态主流程状态机：战斗（技能/指令卡/宝具）→ 结算 → 连续出击 → 助战选择 → 循环
- 策略配置驱动：技能释放顺序、指令卡选择、宝具使用全部可配置（GUI 可视化编辑）
- 多通道截图（参考 MaaFramework ScreencapAgent）：
  - mumu 模拟器专线（内存直读，实测 ~15ms/帧）+ RawByNetcat（TCP 直传）加速通道，自动测速选优
  - adb 多通道截图：Raw / RawGzip / Encode / Pull 自动测速选优、失败降级（默认）
  - minicap 流式截图（可选，部分模拟器可能不稳定）
- minitouch 触控注入，无需 root
- 内置 GitHub 增量更新（检查更新 → 增量包下载 → 重启自动应用）

## 环境要求

- Windows 10/11 + Python 3.11+（源码运行）
- 安卓模拟器（MuMu / 雷电 / NOX 等）或真机（adb 连接）
- 依赖：见 `requirements.txt`（`pip install -r requirements.txt`）

## 源码运行

```bat
python script.py
```

启动后：选择模拟器 → 配置策略 → 点击「开始」。

## 初始化配置教程

面向新用户的完整初始化流程（约 10 分钟）。

### 1. 安装

- **发布包**：下载 `AFS_full_{ver}.zip` 解压到任意目录（如 `D:\AFS`），运行 `AFS.exe`。PyInstaller 打包，**无需安装 Python**。
- **源码运行**（开发用）：`Python 3.11+`，`pip install -r requirements.txt`，然后 `python script.py`。

首次启动会自动完成配置迁移（`settingMigrate`）：以 `settingDefault.json` 为模板补齐缺失字段，个人数据保留；配置损坏时自动从 `.bak` / 默认模板恢复。

### 2. 连接模拟器

1. 打开安卓模拟器，确认 adb 已开启（mumu：设置 → 其他 → adb 调试；雷电：设置 → 其他 → ADB 本地连接）
2. AFS「设置」页 → 模拟器选择 → 「模拟器添加」：填写 `名称` 与 `IP:端口`
   | 模拟器 | adb 地址 |
   |--------|----------|
   | mumu12 | `127.0.0.1:16384` |
   | mumu6 | `127.0.0.1:7555` |
   | 雷电 | `127.0.0.1:5555` |
   | NOX 夜神 | `127.0.0.1:62001` |
3. 点「模拟器链接测试」，看到 `adb success connect to xxx` 即连接成功

### 3. 配置助战素材

1. 设置页助战区 → 「增添助战」（数量对应 3 个助战槽）
2. 选中所添加的助战 → 点「更新」按钮，程序自动从模拟器当前画面截取并保存为 `fgoMaterial/assistServant_{编号}.png`
3. 需要匹配礼装（从者+概念礼装）时：勾选「是否关心礼装」，同样方式截取 `fgoMaterial/assistCloth_{编号}.png`
4. 素材与策略的对应：策略的「助战选择」三个编号 → 对应 `assistServant_{编号}.png`

### 4. 编辑策略

1. 「增添策略」→ 输入名称
2. 三个回合分别填写两组文本：
   - **技能序列**（回合 1~3）：空格分隔的动作组，每组 3 位数字 `从者_技能_目标`，如 `110 120 231`（从者1技能1 → 从者1技能2 → 从者2技能3目标1）；`530` = 换人技（自动重读从者头像）；`0` = 无目标
   - **指令卡序列**（回合 1~3）：`/` 分隔步骤（顺序执行），空格分隔同一步骤的**可交换候选**（命中第一个），如 `z/1/2`（攻击 → 卡1 → 卡2）、`b1 r1 g1`（第一步任选一张蓝/红/绿卡）；`z`=攻击 `x`/`c`=其他固定位，`1`~`5`=固定卡位，`b1`/`r2`/`g3`=颜色+从者编号条件卡
3. 运行页「选择策略」下拉框选中 → 点「开始」

### 5. 开始战斗

1. 「设置」页配置：**战斗次数**、**苹果类型**（金/银/蓝/铜/不吃）、是否**连续出击**
2. 把游戏画面停留在**助战选择/出战界面**
3. 「运行」页 → 选策略 → 「开始」
4. 状态机自动循环：助战选择 → 出战 → 战斗（技能/指令卡/宝具）→ 结算 → 连续出击

### 6.（可选）截图通道加速

默认使用 adb 多通道截图（Raw/RawGzip/Encode/Pull 启动实测选最快、失败自动降级），无需配置即可运行。可选加速：

- **mumu 模拟器专线**（实测 ~15ms/帧，比 adb 默认快 37 倍）：编辑 `configure/setting.json` → `changable.mumuPath` 填 mumu 安装目录（留空=自动探测 `D:\mumu\MuMuPlayer` 等常见路径）、`mumuIndex` 填多开实例索引（0 起，默认 0）
- **minicap 流式截图**：`changable.useMinicap` = `true`（虚拟显示可能致部分模拟器 adb 掉线，默认 `false`）

### 7. 检查更新（GitHub 增量更新）

1. 编辑 `configure/settingFixed.json` → `fixed.update.repo` = `你的GitHub用户名/仓库名`（如 `qcfei/AFS`，空=禁用）
2. 设置页「检查更新(GitHub)」→ 自动对比仓库 `version.json` → 有新版则下载增量包 → 关闭程序后自动应用并重启

### 8. 常见问题

| 问题 | 处理 |
|------|------|
| 模拟器连不上 | 确认模拟器 adb 开关与端口；「模拟器链接测试」看报错；模拟器 adb 掉线时重启模拟器实例 |
| 场景识别不到 | 确认游戏停在正确界面（与 mask 对应）；窗口尺寸/分辨率变化时重新截图素材 |
| 助战素材无效 | 确认编号与策略「助战选择」一致；素材为完整清晰的当前版本截图 |
| 配置损坏崩溃 | 启动时自动从 `.bak` / 默认模板恢复，无需手动处理 |
| minicap 掉线 | `useMinicap` 改回 `false` 走 adb 多通道（默认） |

## 发布包与更新

- 完整包：`AFS_full_{ver}.zip`（默认配置，无个人数据）
- 增量包：`AFS_update_{ver}.zip`（仅含与上一版不同的文件，`update_manifest.json` 含 md5 校验）
- 更新方式：GUI 设置页「检查更新(GitHub)」→ 下载增量包 → 关闭程序自动应用并重启
- 更新仓库配置：`configure/settingFixed.json` → `fixed.update.repo` = `你的GitHub用户名/仓库名`（空=禁用）

## 目录结构

```
pytool/          源码包（状态机/识别/触控/截图/更新）
configure/      配置（settingDefault 分发模板 / settingFixed 程序参数）
mask/           场景识别掩码
fgoMaterial/    个人素材（助战截图等，不入库）
minitouch/      触控注入二进制
minicap/        流式截图二进制（GPL 协议，见 THIRD_PARTY_NOTICES.md）
platform-tools/ 谷歌 adb 工具
```

## 协议

本项目源码以 MIT 协议发布（见 LICENSE）；随包分发的第三方二进制与参考实现见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
