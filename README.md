# AFS — FGO 自动战斗脚本

基于图像识别的《Fate/Grand Order》安卓模拟器自动化战斗脚本：OpenCV 模板匹配识别场景 → minitouch 触控注入 → 配置驱动的状态机循环执行。

> ⚠️ 免责声明：本工具用于自动化重复刷图，使用前请自行确认符合游戏用户协议；封号风险自负。本项目仅供个人学习研究使用。

## 功能

- 8 状态主流程状态机：战斗（技能/指令卡/宝具）→ 结算 → 连续出击 → 助战选择 → 循环
- 策略配置驱动：技能释放顺序、指令卡选择、宝具使用全部可配置（GUI 可视化编辑）
- 多通道截图（参考 MaaFramework ScreencapAgent）：
  - minicap 流式截图（可选，最快，部分模拟器可能不稳定）
  - adb 多通道截图：Raw / RawGzip / Encode / Pull 自动测速选优、失败降级（默认）
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

## 首次使用（新用户）

1. 在「设置」页配置模拟器 IP（adb 端口）
2. 在助战素材区添加你自己的助战从者截图（`assistServant_N.png` / `assistCloth_N.png`，通过 GUI 截图按钮捕获）
3. 编辑或新建策略（技能序列/指令卡规则），策略中指定使用哪个助战素材
4. 把游戏停在出战/助战界面，点击「开始」

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
