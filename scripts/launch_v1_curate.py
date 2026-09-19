#!/usr/bin/env python3
"""One-shot launch-v1 editorial enrichment + delegated approve.

Run from content worktree only. Does not call paid APIs.
"""
from __future__ import annotations

from datetime import UTC, datetime

from jev_awesome.curation.review import ReviewService
from jev_awesome.models import (
    EditorialStatus,
    EvidenceItem,
    FlexibleDate,
    JevRelationship,
    LicenseStatus,
    OfficialStatus,
    PrimaryCategory,
    Resource,
    ResourceKind,
    VerificationLevel,
)
from jev_awesome.store import CatalogStore

NOW = datetime(2026, 9, 20, 4, 0, 0, tzinfo=UTC)
REVIEWER = "cursor:delegated-editor"
NOTE = "launch-v1 editorial curation; source/code reviewed from public README; not runtime reproduction"

# id -> field updates
UPDATES: dict[str, dict] = {
    "github:1357590729": {
        "summary_zh": (
            "官方 Python SDK（PyPI: typesafe-sdk）。用 `TypeSafeClient.system_one` 提交 "
            "Choice / Noul / Score，拿到概率化结构化判断，而不是自由生成文本。"
        ),
        "developer_value": (
            "把「在候选中做校准判断」接到任意 Python 服务；是接入官方 Jev 的默认客户端。"
        ),
        "jev_role": "对 state 上的 typed questions 返回 choice/noul/score 与概率；不负责写散文。",
        "prerequisites": (
            "依赖：`typesafe-sdk`（或本仓库已声明版本）。需要 `TYPESAFE_API_KEY`。"
            "先读：上游 README Quickstart 与 docs.typesafe.ai/sdk/python/。"
        ),
        "limitations": "无 Key 无法调真实 Jev；Mock/Adapter 结果≠官方模型。本目录未做 live 复现。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.OFFICIAL,
        "jev_relationship": JevRelationship.OFFICIAL,
        "primary_category": PrimaryCategory.SDK_INTEGRATIONS,
        "resource_kind": ResourceKind.SDK,
        "languages": ["python"],
    },
    "github:1357635350": {
        "summary_zh": "官方 TypeScript/JavaScript SDK，与 Python 客户端同属 System One 调用面。",
        "developer_value": "在 Node / 浏览器后端侧接入同一套 typed questions，与 Python 团队对齐契约。",
        "jev_role": "官方客户端：system_one + Choice/Noul/Score；不替代业务编排。",
        "prerequisites": "依赖官方 JS SDK 包；需要 TYPESAFE_API_KEY。先读仓库 README 与官方 SDK 文档。",
        "limitations": "需有效 Key；本目录仅 source_checked，未跑通线上调用。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.OFFICIAL,
        "jev_relationship": JevRelationship.OFFICIAL,
        "primary_category": PrimaryCategory.SDK_INTEGRATIONS,
        "resource_kind": ResourceKind.SDK,
        "languages": ["typescript", "javascript"],
    },
    "github:1373655162": {
        "summary_zh": (
            "Browser Use × TypeSafe：动态编号动作空间；Jev 选 operation/target，"
            "仅 TYPE_TEXT 时才让小 LLM 写字。"
        ),
        "developer_value": (
            "学习「决策与文本生成解耦」的可运行浏览器 Agent；先读 agent 循环比抄提示词更有用。"
        ),
        "jev_role": "一次请求内选出 CLICK/TYPE_TEXT/… 与目标元素索引；不生成页面文案。",
        "prerequisites": (
            "依赖：uv、Chrome + Browser Harness、TYPESAFE_API_KEY、TEXT_MODEL_API_KEY（示例为 OpenRouter）。"
            "先读：`jev_ultrafast/agent.py` 与 README「The action space」。"
        ),
        "limitations": (
            "演示延迟/路径依赖真实页面与 Key；本目录未复现其 7.1s 声明。"
            "云端 waitlist 与本地 demo 是不同产品面。"
        ),
        "verification_level": VerificationLevel.CODE_LOCATED,
        "official_status": OfficialStatus.COMMUNITY,
        "jev_relationship": JevRelationship.CALLS_OFFICIAL_API,
        "primary_category": PrimaryCategory.APPLICATIONS,
        "resource_kind": ResourceKind.APPLICATION,
        "languages": ["python"],
        "license_status": LicenseStatus.KNOWN,
        "license_identifier": "MIT",
        "evidence": [
            EvidenceItem(
                url="https://github.com/browser-use/jev-ultrafast",
                source_type="github",
                checked_at=NOW,
                supports="README action-space design reviewed; agent loop located",
                code_location="jev_ultrafast/agent.py",
            )
        ],
    },
    "github:1374280231": {
        "summary_zh": (
            "Android 真机 Agent：Mobilerun 观察/执行，Jev 做决策；含 React studio、CLI 与痕迹。"
        ),
        "developer_value": "看清手机侧「观察→Jev 决策→执行」链路与本地 studio，而不是又一个聊天 demo。",
        "jev_role": "根据屏幕观察在动作候选中做结构化选择；不直接驱动触摸硬件。",
        "prerequisites": (
            "Node 22+/24、pnpm、MOBILERUN_API_KEY、TYPESAFE_API_KEY、可用 Android 设备（经 Mobilerun）。"
            "先读：README「Run it」与 `docs/DEMO.md`；暗色主题 demo 可离线理解流程。"
        ),
        "limitations": "设备/云服务单独计费；完整订票类 demo 未演示成交。本目录未接真机复现。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.COMMUNITY,
        "jev_relationship": JevRelationship.CALLS_OFFICIAL_API,
        "primary_category": PrimaryCategory.APPLICATIONS,
        "resource_kind": ResourceKind.APPLICATION,
        "languages": ["javascript", "typescript"],
        "license_status": LicenseStatus.KNOWN,
        "license_identifier": "MIT",
        "evidence": [
            EvidenceItem(
                url="https://github.com/droidrun/mobile-jev",
                source_type="github",
                checked_at=NOW,
                supports="README requirements and demo limits reviewed 2026-09-20",
            )
        ],
    },
    "github:1375026016": {
        "summary_zh": "PostgreSQL 扩展：用自然语言条件过滤/排序/分类行；每行由 Jev 判概率，无向量列。",
        "developer_value": "把「语义过滤」放进 SQL，而不是在应用层把整表塞进聊天模型。",
        "jev_role": "对行级条件返回概率（jev / jev_prob）；不负责生成 SQL 或嵌入。",
        "prerequisites": (
            "PostgreSQL + 扩展安装（PGXN/构建）；TYPESAFE_API_KEY；网络可达 TypeSafe。"
            "先读：上游 README 的 SQL 示例与扩展安装说明。"
        ),
        "limitations": "每行/批调用有成本与延迟；许可为 PostgreSQL 类（NOASSERTION 元数据）。本目录未装扩展复现。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.COMMUNITY,
        "jev_relationship": JevRelationship.CALLS_OFFICIAL_API,
        "primary_category": PrimaryCategory.APPLICATIONS,
        "resource_kind": ResourceKind.APPLICATION,
        "languages": ["sql", "shell"],
        "evidence": [
            EvidenceItem(
                url="https://github.com/realZachi/pg-jev",
                source_type="github",
                checked_at=NOW,
                supports="README SQL API and Jev role reviewed 2026-09-20",
            )
        ],
    },
    "github:1372296290": {
        "summary_zh": (
            "Neo4j 图导航演示：每跳把出边做成 Choice，并同请求问 Noul「是否到达目标」。"
        ),
        "developer_value": "学习如何用概率路径/beam search 做图遍历，而不是让 LLM 编造下一跳。",
        "jev_role": "单跳 Choice（跟哪条边）+ Noul（是否到达）；应用层做 beam 与可视化。",
        "prerequisites": (
            "Neo4j（默认可指公共 companies2 demo）、TYPESAFE_API_KEY、Python 环境。"
            "先读：`src/neo4jev/navigator.py` 与 README Architecture。"
            "无 Key 时上游会显式用占位答案，不伪装成 TypeSafe 输出。"
        ),
        "limitations": "演示图与自建图 schema 不同；本目录未连接 Neo4j/live Jev。",
        "verification_level": VerificationLevel.CODE_LOCATED,
        "official_status": OfficialStatus.COMMUNITY,
        "jev_relationship": JevRelationship.CALLS_OFFICIAL_API,
        "primary_category": PrimaryCategory.APPLICATIONS,
        "resource_kind": ResourceKind.APPLICATION,
        "languages": ["python"],
        "evidence": [
            EvidenceItem(
                url="https://github.com/jexp/neo4jev",
                source_type="github",
                checked_at=NOW,
                supports="README architecture reviewed; navigator module located",
                code_location="src/neo4jev/navigator.py",
            )
        ],
    },
    "github:1376174149": {
        "summary_zh": "GitHub Next：本地兼容 `POST /v1/systemone` 的实现（Bun + Diffusion），用于研究/桥接。",
        "developer_value": "在无官方 Key 或要本地试验时，对齐 System One 契约做客户端联调。",
        "jev_role": "本地兼容端点；不是官方托管 Jev，质量与校准不可直接等同。",
        "prerequisites": "按上游 README 安装运行时与模型依赖。先读仓库说明与 `/v1/systemone` 兼容说明。",
        "limitations": "名称易与官方混淆；输出≠官方 Jev。本目录未本地启动服务。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.COMMUNITY,
        "jev_relationship": JevRelationship.INSPIRED_INDEPENDENT,
        "primary_category": PrimaryCategory.RESEARCH_ALTS,
        "resource_kind": ResourceKind.ALTERNATIVE,
    },
    "github:1375069862": {
        "summary_zh": (
            "受 Jev 启发的可训练小型决策模型（Qwen + LoRA/读出头）；提供兼容 System One 的服务端。"
        ),
        "developer_value": "研究「概率读出 vs 解码文本」、本地训练与冻结评测套件；可换 base_url 试官方 SDK。",
        "jev_role": "独立模型族；API 形状对齐 System One，但权重与校准是作者自己的。",
        "prerequisites": (
            "Python 3.12+、uv、权重（Hugging Face）、Apple Silicon/CUDA 视规模而定。"
            "先读：README Highlights 与 PLAN.md；评测口径见 frozen suites 说明。"
        ),
        "limitations": "作者自述部分 checkpoint 未过其发布门槛；数字不可当官方 Jev 成绩。本目录未训练/未服务。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.COMMUNITY,
        "jev_relationship": JevRelationship.INSPIRED_INDEPENDENT,
        "primary_category": PrimaryCategory.RESEARCH_ALTS,
        "resource_kind": ResourceKind.RESEARCH,
        "languages": ["python"],
        "license_status": LicenseStatus.KNOWN,
        "license_identifier": "Apache-2.0",
    },
    "github:1345508845": {
        "summary_zh": "官方 Agent Skill：教代理如何用 System One / Jev 设计类型化工作流。",
        "developer_value": "在 Claude Code / skills.sh 里快速对齐「该问 Choice 还是 Noul」的设计习惯。",
        "jev_role": "技能文档与提示；不本身调用模型（由宿主代理决定是否调 API）。",
        "prerequisites": "兼容的 agent 运行时。先读 `skills/typesafe-ai/SKILL.md`。",
        "limitations": "安装技能≠已配置 API Key；本目录未验证各宿主安装路径。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.OFFICIAL,
        "jev_relationship": JevRelationship.OFFICIAL,
        "primary_category": PrimaryCategory.OFFICIAL,
        "resource_kind": ResourceKind.TUTORIAL,
    },
    "github:1328238153": {
        "summary_zh": "官方适配器：用通用 LLM API 充当 TypeSafeClient 替身，便于本地实验。",
        "developer_value": "无官方 Key 时仍能联调客户端形状；明确区分「替身」与「真 Jev」。",
        "jev_role": "开发/测试替身；结果不等同于 System One / Jev。",
        "prerequisites": "Python + 上游依赖 + 你自己的 LLM API Key。先读仓库 README。",
        "limitations": "勿当生产替代；概率/校准语义可能完全不同。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.OFFICIAL,
        "jev_relationship": JevRelationship.OFFICIAL,
        "primary_category": PrimaryCategory.SDK_INTEGRATIONS,
        "resource_kind": ResourceKind.SDK,
        "languages": ["python"],
    },
    "github:1373664881": {
        # created below if missing
        "summary_zh": (
            "并排对照：Cerebras 上 Qwen 结构化输出 vs TypeSafe Jev vs 本地 Needle，"
            "记录延迟、成本与校验通过情况。"
        ),
        "developer_value": "读方法与原始导出，判断「换模型」还是「换决策形态」；不要只看首页 GIF。",
        "jev_role": "基准中的原生判断路径；与 LLM schema 输出、本地 tool-call 对照。",
        "prerequisites": (
            "复现需各提供商 Key 与上游说明的运行环境。"
            "先读：`docs/benchmarks/README.md` 与 `docs/jev.md`；把表格当作者实验记录，非本仓库复现。"
        ),
        "limitations": (
            "作者自述 Needle 测量条件不同，不能当严格速度排名。"
            "本目录仅阅读公开方法与结果页，未重跑基准 → verification 非 benchmarked。"
        ),
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.COMMUNITY,
        "jev_relationship": JevRelationship.CALLS_OFFICIAL_API,
        "primary_category": PrimaryCategory.EVALS_LIMITS,
        "resource_kind": ResourceKind.EVALUATION,
        "languages": ["typescript", "javascript"],
        "license_status": LicenseStatus.KNOWN,
        "license_identifier": "MIT",
        "evidence": [
            EvidenceItem(
                url="https://github.com/iammrduncan/typesafe-ai-benchmark",
                source_type="github",
                checked_at=NOW,
                supports="README methodology and caveat table reviewed 2026-09-20",
            )
        ],
    },
    "web:1ee3f04b85cf2674": {
        "summary_zh": "官方文档机器可读索引（llms.txt）：概念、原语、SDK 与 cookbook 入口。",
        "developer_value": "动手前先定向打开正确文档页，避免只搜到过时二次摘要。",
        "jev_role": "文档导航；不调用模型。",
        "prerequisites": "浏览器或能拉文本的客户端。先打开该索引再跟链到 primitives/confidence/SDK。",
        "limitations": "索引会变更；条目存在≠你已理解实现。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.OFFICIAL,
        "jev_relationship": JevRelationship.OFFICIAL,
        "primary_category": PrimaryCategory.OFFICIAL,
        "resource_kind": ResourceKind.OFFICIAL_DOC,
    },
    "web:6b79f05c84473e46": {
        "summary_zh": "官方原语说明：Choice / Score / Noul 的字段语义与同请求隔离。",
        "developer_value": "设计问题时必读：弄清「选项」「有序档」「是否」三种问题类型。",
        "jev_role": "定义你能向 Jev 问什么；本身不是运行时。",
        "prerequisites": "无 Key。先读本页，再写 SDK 调用。",
        "limitations": "文档会迭代；以线上 docs.typesafe.ai 为准。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.OFFICIAL,
        "jev_relationship": JevRelationship.OFFICIAL,
        "primary_category": PrimaryCategory.GETTING_STARTED,
        "resource_kind": ResourceKind.OFFICIAL_DOC,
    },
    "web:64154f4aee021df4": {
        "summary_zh": "官方置信度说明：confidence 仅适用于 Choice/Score；Noul 无 confidence。",
        "developer_value": "避免在 Noul 上读不存在的字段，或把 confidence 误当成万能阈值。",
        "jev_role": "解释如何解读返回分布上的置信信息。",
        "prerequisites": "先读 primitives，再读本页。无需 Key。",
        "limitations": "置信度≠业务正确性保证。",
        "verification_level": VerificationLevel.SOURCE_CHECKED,
        "official_status": OfficialStatus.OFFICIAL,
        "jev_relationship": JevRelationship.OFFICIAL,
        "primary_category": PrimaryCategory.GETTING_STARTED,
        "resource_kind": ResourceKind.OFFICIAL_DOC,
    },
}


def ensure_benchmark(store: CatalogStore) -> None:
    rid = "github:1373664881"
    if store.get_resource(rid) is not None:
        return
    resource = Resource(
        id=rid,
        resource_kind=ResourceKind.EVALUATION,
        primary_category=PrimaryCategory.EVALS_LIMITS,
        tags=["launch-v1"],
        languages=["typescript", "javascript"],
        canonical_url="https://github.com/iammrduncan/typesafe-ai-benchmark",
        author_or_org="iammrduncan",
        official_status=OfficialStatus.COMMUNITY,
        jev_relationship=JevRelationship.CALLS_OFFICIAL_API,
        original_title="iammrduncan/typesafe-ai-benchmark",
        summary_en="LLM structured output vs TypeSafe Jev latency/cost/judgment benchmark",
        published_at=FlexibleDate(
            value=datetime(2026, 9, 16, tzinfo=UTC),
            precision="day",
            raw="2026-09-16",
            source="github.created_approx",
        ),
        first_discovered_at=NOW,
        license_status=LicenseStatus.KNOWN,
        license_identifier="MIT",
        editorial_status=EditorialStatus.PROPOSED,
        verification_level=VerificationLevel.DISCOVERED,
        github_repo_id=1373664881,
        github_full_name="iammrduncan/typesafe-ai-benchmark",
        source_identity="github:1373664881",
    )
    store.save_resource(resource, inbox=True)


def main() -> None:
    store = CatalogStore()
    ensure_benchmark(store)
    svc = ReviewService(store)
    for rid, fields in UPDATES.items():
        r = store.get_resource(rid)
        if r is None:
            raise SystemExit(f"missing resource: {rid}")
        update = dict(fields)
        evidence = update.pop("evidence", None)
        if evidence is not None:
            update["evidence"] = evidence
        elif r.evidence:
            # keep existing
            pass
        updated = r.model_copy(update=update)
        # Keep proposed/pending until approve
        if updated.editorial_status == EditorialStatus.PENDING:
            updated = updated.model_copy(update={"editorial_status": EditorialStatus.PROPOSED})
        store.save_resource(updated, inbox=True)
        approved = svc.approve(rid, reviewer=REVIEWER, note=NOTE)
        print(f"approved {approved.id} → curated ({approved.verification_level.value})")
    print("done", len(UPDATES), "curated")


if __name__ == "__main__":
    main()
