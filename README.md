<div align="center">

# 真寻农场(astrbot_plugin_farm)
<p align="center">
    <a href="./LICENSE">
        <img src="https://img.shields.io/badge/license-GPL3.0-FE7D37" alt="license">
    </a>
    <a href="https://www.python.org">
        <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python">
    </a>
    <a href="https://github.com/astral-sh/ruff">
        <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json" alt="ruff">
    </a>
    <a href="https://github.com/AstrBotDevs/AstrBot">
        <img src="https://img.shields.io/badge/AstrBot-3.5.1%2B-%2376BAD9" alt="AstrBot">
    </a>
</p>

<p align="center">

[![tencent-qq](https://img.shields.io/badge/%E7%BE%A4-%E7%9C%9F%E5%AF%BB%E5%86%9C%E5%9C%BA%E6%B5%8B%E8%AF%95-%23FF99CC
)](https://qm.qq.com/q/7hsOD4rOw2)

</p>

你是说可以种地对吧🤔?<br>
该项目由真寻小插件[真寻农场](https://github.com/Shu-Ying/zhenxun_plugin_farm)移植

</div>

----
## 目录
- [真寻农场(astrbot\_plugin\_farm)](#真寻农场astrbot_plugin_farm)
  - [目录](#目录)
  - [农场界面](#农场界面)
  - [使用指令](#使用指令)
  - [更新日志(详细)：](#更新日志详细)
  - [用户方面](#用户方面)
  - [代码方面](#代码方面)
  - [待办事宜 `Todo` 列表](#待办事宜-todo-列表)
  - [关于](#关于)
  - [致谢](#致谢)
  - [许可证](#许可证)

---

## 农场界面

![农场界面](./resource/1.png)

---

## 使用指令

| 指令 | 描述 | Tip |
| --- | --- | --- |
| @小真寻 开通农场 | 首次开通农场 |  |
| 我的农场 | 你的农场 |  |
| 农场详述 | 农场详细信息 |  |
| 我的农场币 | 查询农场币 |  |
| 种子商店 [筛选关键字] [页数] or [页数] | 查看种子商店 | 当第一个参数为非整数时，会默认进入筛选状态。页数不填默认为1 |
| 购买种子 [种子名称] [数量] | 购买种子 | 数量不填默认为1 |
| 我的种子 | 查询仓库种子 |  |
| 播种 [种子名称] [数量] | 播种种子 | 数量不填默认将最大可能播种 |
| 收获 | 收获成熟作物 |  |
| 铲除 | 铲除荒废作物 |  |
| 我的作物 | 你的作物 |  |
| 出售作物 [作物名称] [数量] | 从仓库里向系统售卖作物 | 不填写作物名将售卖仓库种全部作物 填作物名不填数量将指定作物全部出售 |
| 偷菜 @美波理 | 偷别人的菜 | 每人每天只能偷5次 |
| 更改农场名 [新的农场名] | 改名 | 农场名称无法存储特殊字符 |
| 农场签到 | 签到 | 需要注意，该项会从服务器拉取签到数据 |

---

## 配置
在 astrbot 网页端后台进行配置

| 配置项 | 是否必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| FarmDrawQuality | 否 | "low" | 绘制农场清晰度 分为："low", "medium", "hight", "original" |
| FarmPrefix | 否 |  | 对指令添加防冲突的前缀 |
| FarmServerUrl | 否 | "http://diuse.work" | 后续签到、交易行、活动等服务器地址 |

---

## 更新日志[(详细)](./log/log.md)：
用户方面
---
- 新增种子商店筛选功能（如果没有BUG的话后续我的种子、我的作物等也会加入筛选功能
- 新增签到功能（测试
- 新增农场详述功能，能通过该功能更加详细的观看农场数据
- 修复了迁移旧数据库无法正常迁移的BUG
- 修复了偷菜会导致偷自己的BUG
- 修正了作物阶段绘制不正确的BUG

代码方面
---
- 修正了多阶段作物成长素材计算逻辑
- 修正了作物数据库字段错乱的问题
- 作物新增offset字段，用于以后偏移坐标和大小(尚未启用，该模式有商议
---

## 待办事宜 `Todo` 列表

- [x] 完善我的农场图片，例如左上角显示用户数据
- [ ] 完善升级数据、作物数据、作物图片
- [x] 签到功能
- [ ] 添加渔场功能
- [ ] 增加活动、交易行功能
- [ ] 增加交易行总行功能
- [ ] 添加其他游戏种子素材
- [ ] 想不到了，想到再说

---

## 关于

本人毫无任何Python经验，也从未正式的、系统的、完整的去学习Python。如有看到写的不对的地方，欢迎指出，也欢迎任何人一起来开发、完善农场。

素材来均源于互联网，侵权请联系我删除

---

## 致谢

最后感谢以下框架/作者的提供的技术支持(排名不分先后):

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) *✨ 易上手的多平台 LLM 聊天机器人及开发框架 ✨*
- [zhenxun_bot](https://github.com/zhenxun-org/zhenxun_bot) *最爱真寻的一集*
- [HibiKier](https://github.com/HibiKier) *阿咪为什么是神*
- [ATTomato](https://github.com/ATTomatoo) *流泪偷码头.jpg*

## 许可证

`真寻农场(astrbot_plugin_farm)`将采用的是`GPLv3`许可证进行开源
