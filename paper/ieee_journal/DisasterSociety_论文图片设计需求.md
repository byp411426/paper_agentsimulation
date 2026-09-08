# DisasterSociety 三张核心图片设计需求

用途：本文档定义期刊正文仅保留的三张核心示意图。当前阶段只冻结科学内容、三图分工、版式、图题和验收标准，不生成图片文件。全文数量口径固定为 **3 张图片 + 7 张独立表格**；表格不计入图片数量。实验结果不再制作正文图，继续由表 I–VII 报告精确数值。

## 一、三图总原则

三张图分别回答三个不同问题，不能互相重复：

| 图号 | 图的职责 | 回答的问题 | 正文位置 |
|---:|---|---|---|
| 图 1 | 引言中的人物/家庭运行示例 | 灾害中的居民和家庭究竟经历什么过程？ | 第 I 节引言 |
| 图 2 | DisasterSociety 总体架构 | 系统包含哪些对象、层次和接口？ | 第 IV-A 节 |
| 图 3 | 社会过程方法机制与运行闭环 | 记忆、反馈、规划、互动如何共同产生并约束行动？ | 第 IV-D/E 节交界处 |

三图的边界固定如下：

- 图 1 讲具体情境和研究动机，不画完整软件组件图；
- 图 2 讲系统静态组成与数据流，不展开某一家庭的时间故事；
- 图 3 讲方法的动态机制和状态转换，不重复图 2 的数据来源与证据层；
- E1、E2、E3/E3a 和 E3c 的结果均保留在表 III–VII 中，不另设结果图号；
- 表 I–II 承担评价映射和数据角色，不再把它们重复绘制成图片。

## 二、统一制作规范

- 三张图均建议使用 IEEE 双栏宽度，最终插入宽度约 7.16 in；如果图 1 的三阶段故事足够简洁，可在排版时尝试单栏版本，但不能为了塞入单栏而把字号压小。
- 主文件导出为可编辑矢量 `PDF` 或 `SVG`；LaTeX 中优先插入裁切后的矢量 `PDF`。另导出 300 dpi PNG 仅供审阅预览。
- 最终缩放后，图内正文不低于 8 pt，面板标记 10–11 pt；字体与 IEEE 正文协调，英文标签优先使用简洁名词短语。
- 使用色盲友好配色并提供形状或线型的双重编码：蓝色表示 Resident/私有认知，橙色表示 Household/协调状态，紫色表示 Interaction/社会消息，深灰表示 World/物理事实，绿色表示可执行或已执行，朱红表示道路关闭或行动拒绝。
- 不使用 3D、渐变、阴影、装饰性城市背景或 AI 生成插画。人物使用简洁的矢量剪影或线性图标，不采用照片或写实卡通。
- 箭头必须具有明确语义，并在必要时标注 `observation`、`message`、`intent`、`commitment`、`execution outcome`；不能用无标签的大循环替代真实信息流。
- 每张图的正文术语必须与论文完全一致：`Resident`、`Household`、`Interaction`、`World`、`EventPack`、`Engine`、`memory`、`feedback`、`planning`、`commitment`。
- 图片生成后应保存源文件、最终 PDF、预览 PNG 和 SHA-256；三张图的来源与导出信息写入 `figures/manifest.json`。

## 三、图 1：动态灾害中的人物与家庭响应示例

### 1. 图的类型与目的

类型：引言中的 motivated/running example。

目的：让读者在 30 秒内理解多个居民如何在信息不对称、家庭资源共享和环境变化中形成连续响应。图中家庭为抽象合成家庭，不对应真实 Carr 受访者，也不代表 Carr Fire 的历史轨迹。

### 2. 推荐布局

采用从左到右的三阶段故事图，每一阶段都同时显示人物、家庭资源和 World 状态。

#### 阶段 A：信息不对称

- 成人 A 收到官方预警，成人 B 尚未收到；
- 两人头顶使用不同的信息气泡表示所知信息不同；
- 家庭场景中显示一辆共享车辆和一名需要照护的成员；
- 地图小窗显示危险正在接近且主路线仍开放。

阶段标签：`Asymmetric warning exposure`。

#### 阶段 B：家庭协商

- A 与 B 围绕同行成员、共享车辆、主路线和出发时间进行协商；
- 两人的对话气泡汇合成一张简洁的家庭方案卡；
- 图形上继续保留两个人物，不把家庭画成一个统一大脑。

阶段标签：`Household coordination`。

#### 阶段 C：路线变化与行动执行

- 主路线出现关闭标志，原方案无法继续；
- 红色反馈箭头把路线失败返回家庭；
- 家庭改用绿色备用路线并形成更新方案；
- 右端使用“通过约束检查”的标记表示方案可以执行。

阶段标签：`Disruption, feedback, and adaptation`。

整张图采用人物故事板，不使用软件架构框、完整状态机或多条技术泳道。三阶段之间只保留少量方向箭头。

### 3. 必须出现的视觉元素

- 两名具备决策资格的成年 Resident；
- 一名依赖成员；
- 一辆共享车辆；
- 主路线和备用路线；
- 官方预警；
- 家庭协商与更新方案；
- 路线关闭；
- 路线失败反馈与备用路线。

### 4. 不应出现的内容

- 不放 E1/E2/E3 数值；
- 不写“真实 Carr 家庭”或“历史复现”；
- 不把依赖成员画成独立 LLM 决策者；
- 不把消息投递直接画成全家已同意；
- 不把 Resident 的行动意图直接连到安全区，必须经过 World 仲裁。
- 不写完整的消息或行动状态链，状态合同统一放到图 3。

### 5. 正文图题

> 图 1. 动态灾害中的家庭响应过程示例。两个成年居民在不同时间接收预警，围绕车辆、照护成员和出发方案形成协调承诺；主路线关闭后，执行反馈触发路线更新和重规划，最终行动由共享世界依据成员、车辆、时间与路线状态统一仲裁。图中分别标示居民私有认知、家庭协调状态和可观察物理状态。

### 6. 推荐工具

- 初稿：PowerPoint 或 Keynote；
- 定稿：Figma 或 PowerPoint 矢量导出；
- 不建议使用 Matplotlib、AI 生图或写实素材。

## 四、图 2：DisasterSociety 总体架构

### 1. 图的类型与目的

类型：solution overview / system architecture。

目的：给出整篇方法的静态地图，使读者能够从后续小节定位 EventPack、Resident、Household、Interaction、Engine、World 和证据输出各自位于哪里，以及这些组件之间有哪些主要接口。

### 2. 推荐布局

采用从左到右的四区总体架构图，外层使用 `DisasterSociety` 系统边界。

#### 区域 A：数据与场景输入

- `EventPack manifest`；
- `Population and whole-household donors`；
- `Warning / hazard / road / resource events`；
- `Case-specific adapters`。

这里只画输入类型与来源记录，不展开 Carr 问卷字段清单。

#### 区域 B：居民与家庭社会状态

- 多个 `Resident` 框，内部只概括为 `private cognition and decision`；
- 一个包围成员关系的 `Household` 框：members、vehicles、care responsibilities、commitments；
- 独立 `Interaction` 框，概括为 `message exchange and coordination`。

Resident 不能被 Household 完全包成一个统一认知体；可使用连接线表达家庭成员关系。

#### 区域 C：运行内核与共享世界

- `Event-driven Engine`：只标注 `simulation kernel`，不在架构图中展开时间步算法；
- `World`：hazard、roads、locations、vehicle/resource state；
- Resident、Interaction 与 Engine/World 之间使用少量双向接口箭头，详细含义由图 3 展开。

#### 区域 D：过程与复现输出

- trajectory snapshots；
- message and commitment records；
- intent and execution outcomes；
- model calls、tokens、cost、failure/fallback；
- config、data and code hashes；
- run terminal status。

证据输出作为右侧窄栏，不占据图形中心。

### 3. 关键连线

- EventPack → Engine：`time-indexed events`；
- Engine ↔ Resident/Interaction：`decision and communication interface`；
- Engine ↔ World：`state and execution interface`；
- 所有主要组件 → Evidence outputs：`trace records`。

### 4. 与图 1、图 3 的区别

- 不讲某个家庭的具体故事，那是图 1；
- 不展开 memory、feedback、planning 和 interaction 如何在一个时间步闭环作用，那是图 3；
- 本图只负责让读者看清系统边界、组件责任和接口。

### 5. 正文图题

> 图 2. DisasterSociety 总体架构。人口与家庭 donor、EventPack 事件和场景控制构成输入；事件驱动 Engine 连接 Resident 私有认知、Household 资源与承诺、Interaction 消息生命周期以及 World 物理状态与仲裁；逐步轨迹、调用日志、运行终态、哈希和成本进入统一证据层。

### 6. 推荐工具

- 初稿与正式源文件：draw.io；
- 视觉精修：Figma；
- 如果后续需要与 LaTeX 字体完全一致，可在布局冻结后转为 TikZ。

## 五、图 3：居民社会过程的方法机制与运行闭环

### 1. 图的类型与目的

类型：method mechanism / dynamic process loop。

目的：解释 DisasterSociety 的核心方法如何运行。图 2 告诉读者“系统里有什么”，图 3 则告诉读者“这些机制怎样在连续时间步中共同工作”，并明确消息、家庭承诺、行动意图和物理执行是不同状态。

### 2. 推荐布局

采用“上部主闭环 + 下部状态合同”的双层结构。

#### 上部：六阶段主闭环

从左到右排列六个阶段，最后一阶段以回弯箭头返回第一阶段：

1. **Dynamic events and limited observation**
   - EventPack/World 产生预警、危险和路线事件；
   - Interaction 产生社会消息；
   - Resident 只获得满足渠道、位置和访问条件的观察。

2. **Memory**
   - 只有已经处理的信息进入私有记忆；
   - 根据时间、重要度和相关性检索当前可用记录。

3. **Feedback and belief update**
   - 局部观察与上一步执行结果修正路线认识和当前判断；
   - 真实 World 状态不自动同步到全部 Resident。

4. **Planning**
   - 生成或修订包含路线、车辆、同行成员和出发时间的结构化计划；
   - 计划只是预期行动，不直接改变物理状态。

5. **Interaction and household commitment**
   - 居民发送提议或响应；
   - 通过成员、车辆、路线和时间检查后形成版本化家庭承诺；
   - 新承诺可以取代旧版本，但历史保留。

6. **World arbitration and execution**
   - 同一时间步的全部意图在共享快照上批量解析；
   - World 检查道路、车辆容量、成员位置、照护和时间冲突；
   - 只有 `executed` 结果改变位置与资源状态，`rejected(reason)` 返回下一轮。

主闭环上的关键箭头分别标注：

- `observable context`；
- `retrieved memory`；
- `updated cognition`；
- `structured plan / intent`；
- `commitment-constrained intent`；
- `execution outcome / feedback`。

#### 下部：两条状态合同

用两条紧凑的状态带说明最重要的因果边界：

**Message and commitment**

`sent → delivered → processed → accepted / rejected → feasible commitment`

**Action and world state**

`intention → batched resolution → executed / rejected → state update / feedback`

用虚线把 `processed` 连接到 Memory，把 `feasible commitment` 连接到 Planning/Intent，把 `rejected` 连接到 Feedback。这样可同时表现四个机制和两类状态转换，又不会把图 3 退化成单纯的软件流程图。

### 3. 四个机制的视觉编码

- Memory：蓝色圆角框与存储/检索箭头；
- Feedback：朱红输入、蓝色更新输出，强调失败原因进入下一轮；
- Planning：绿色结构化计划卡片；
- Interaction：紫色消息与橙色家庭承诺；
- World arbitration：深灰框，内部列出五项约束检查。

四种机制名称必须直接出现在图内，不能使用 `Module A–D`。

### 4. 与实验的连接方式

图 3 只解释方法，不放消融效应数值。可以在四个机制框右上角放一个小型开关符号，表示它们可以被独立启用或移除；具体 `full` 与 `full−module` 设计、配对 seed 和统计结果继续由第 V-D、V-G 节以及表 IV–VI 说明。

### 5. 正文图题

> 图 3. DisasterSociety 居民社会过程的机制闭环。动态事件和社会消息通过受限观察进入 Resident 的私有认知，记忆、反馈与规划机制生成或修订结构化意图，互动机制形成家庭承诺；World 在共享快照上依据道路、车辆、成员、照护和时间约束统一仲裁，执行或拒绝结果返回下一时间步。图中同时标示消息从发送到接受或拒绝、行动从意图到执行或拒绝的状态转换。

### 6. 推荐工具

- 初稿：draw.io；
- 定稿：Figma 或 draw.io 矢量 PDF；
- 若希望完全可编译复现，可在设计冻结后转 TikZ，但不建议在布局尚未确认时直接手写 TikZ。

## 六、结果表格安排

取消原计划的结果图后，精确结果由现有七张表承担：

| 表号 | 内容 |
|---:|---|
| 表 I | 研究问题、分析尺度与证据类型 |
| 表 II | Carr 案例数据、运行角色与表述边界 |
| 表 III | E1 家庭终态、出发执行与消息过程 |
| 表 IV | E2 四模块近端操纵检查 |
| 表 V | E2 四模块下游家庭效应 |
| 表 VI | E3 七个模型配置中的反馈与互动效应 |
| 表 VII | E3c 100 户配置的家庭过程与运行包络 |

其中表 III–VII 继续保留所有效应方向、区间、样本单位和结果语义，不再把同一信息重复绘制为结果图。

## 七、制作顺序与验收

1. 先画图 1 的三阶段草图，确认它与引言使用同一个家庭 running example；
2. 再画图 2，冻结系统对象、层次与接口；
3. 最后画图 3，确保机制闭环与图 2 不重复，并能对应第 IV-D/E 节；
4. 三图统一执行矢量格式、最终字号、色盲、灰度、箭头语义和双栏缩放检查；
5. 将三张图给不了解项目的读者做 30 秒测试：图 1 应能说明研究场景，图 2 应能复述系统组成，图 3 应能复述机制闭环；
6. 图片确认后再写入 IEEE LaTeX，正文不得重新增加结果图占位。

当前完整性结论：三张图的类型、职责和正文位置互不重复；图 1 是动机示例，图 2 是总体架构，图 3 是方法机制。实验结果由七张表承载。
