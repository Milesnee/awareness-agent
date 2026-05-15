# ADR-001: SKILL 驱动 vs 独立 Python 脚本

> 日期：2026-05-11
> 状态：已接受

## 背景

觉察助手需要一个对话引擎来驱动晨间/晚间觉察引导。两种可选方案：

## 选项

### A: 独立 Python 脚本
- 自建对话状态机、消息队列、定时触发
- 完全独立于 OpenClaw

### B: OpenClaw SKILL 驱动（选择）
- 复用 OpenClaw 的 session 管理、消息路由、心跳机制
- SKILL.md 定义对话逻辑，heartbeat 触发主动推送

## 决策

选择 B（SKILL 驱动）。

## 理由

1. **复用基础设施**：OpenClaw 已有飞书消息路由、心跳调度、session 管理，不需要重复造轮子
2. **统一管理**：所有任务（觉察、资本周期、ClawCast）在同一个 HEARTBEAT.md 中管理
3. **渐进式披露**：SKILL.md + references/ 的分层结构天然支持按需加载
4. **MVP 速度**：不需要额外部署任何服务，注册 SKILL 即可使用

## 影响

- 觉察助手依赖 OpenClaw 运行，不能独立部署
- 对话质量受限于当前模型（GLM-5-Turbo）的共情能力
- 后续如果需要独立部署（微信服务号），需要抽取对话引擎为独立模块
