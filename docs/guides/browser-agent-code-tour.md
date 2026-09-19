# 读 Jev Ultrafast：为什么「选动作」和「写文字」要分开？

上游仓库：[browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast)

这篇导读只基于公开 README 与其指出的源码入口（`jev_ultrafast/agent.py`）。**本目录没有复现**其演示耗时或航班任务成功率。

## 它在解决什么

浏览器自动化里，模型容易同时做两件难事：

1. 决定「点哪个、滚哪里、是否结束」  
2. 决定「往输入框里打什么字」

把两件事混在一次自由生成里，动作空间会膨胀，失败也难定位。Ultrafast 的做法是：

- 每一帧观察生成**编号元素表**
- 只提供有限 **operations**（如 `CLICK`、`TYPE_TEXT`、`SELECT`、`WAIT`、`DONE`、`BLOCKED`…）
- **一次 TypeSafe 请求**选出 operation 以及对应的 target 头
- **仅当** operation 是 `TYPE_TEXT` 时，才调用**另一个**小 LLM 生成字符串

也就是说：Jev 负责「选」，文本模型负责「写」。

## 你应该先读哪里

1. README 中的 **The action space**（元素表 + 一次请求多头）  
2. 源码入口：`jev_ultrafast/agent.py`（决策循环）  
3. 本地试跑说明：需要 `TYPESAFE_API_KEY`、`TEXT_MODEL_API_KEY`、Chrome / Browser Harness

读循环时盯三件事：

- 元素表如何从页面构造，选项如何裁剪到「合法 operation × 合法 target」
- 为何 target 问题可以「投机」地一起问，却只执行与 operation 匹配的那一个
- `TYPE_TEXT` 分支如何把控制权交给文本模型，再回到浏览器执行

## 这对你自己的 Agent 意味着什么

- **先枚举可执行动作**，再问 Jev；不要把整个 HTML 丢给聊天模型让它「看着办」
- **文本生成是可选副作用**，不是每个决策的默认输出
- **测量要分开**：决策延迟、文本生成延迟、页面加载等待——混在一个数字里无法改进

## 限制（请写进你的预期）

- 演示依赖真实站点与两套 Key；环境一变，延迟声明不可直接外推  
- README 中的云端产品 waitlist 与开源本地 demo 不是同一交付物  
- 本目录验证等级为 `code_located`：定位到了循环文件，**不等于**我们跑通了 demo

## 相关阅读

- [Jev 到底适合放在你的程序哪一步？](start-here.md)
- [官方 API、社区 SDK、LocalJev、kev：应该从哪里开始？](choose-your-path.md)
