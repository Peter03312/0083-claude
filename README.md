# 双视角声音漫游 · 故事校样

为校园艺术周的双视角声音漫游做录音前校样：听众分别替角色 A、B 选路
（绕钟楼 / 穿连廊），在同一声景里会面。应用**逐结局**核验每条选择序列：

* 到达/离开都是整数分钟上的**离散可达时刻**——不使用连续区间，
  “最早/最晚”之间不存在的时刻（空洞）不会被当成可会面时刻；
* 绝对时间窗口（open/close，按整数分钟裁决）；
* 地点之间必须显式给出**最短转场**分钟数，缺边即不可达，
  角色不能瞬间跨越两座楼；
* 会面配对要求两人在**同一刻**到达各自被引用的场景；
* 消息的阅读事件必须显式引用发送事件，且发送时刻**严格早于**阅读
  （回信先于留言会被抓出；跨支线引用不存在的发送也会被抓出）；
* 同一合流场景被不同来路同刻抵达时，各选择序列仍是独立路线、
  独立结局——合流处绝不混成一份状态。

应用只核验作者给出的结构，不续写台词、不推荐剧情。

## 首个矛盾的确定性裁决

所有结局（A 路线 × B 路线的笛卡尔配对）全部检查；全局首个矛盾按键排序：

`(故事时间, A 已走边数, B 已走边数, 角色编号, 边序, 矛盾代码, 结局序号)`

返回中包含可复述的两条路线、相关事件与相差分钟数。

## 修订与图依赖影响域

* 每次提交建立**只追加**的新修订，校样 JSON 冻结入库（SQLite，gzip 存储），
  旧修订重复读取逐字节一致，永不随新编辑漂移；
* 编辑时长 / 窗口 / 转场下限时，按场景图依赖标出**必须重算**的场景与结局：
  时长编辑向下游闭包传播；窗口编辑向上游闭包传播；转场编辑只落到
  真正跨越该地点对的选择边及其下游；会面/消息变化重裁全部结局；
* 前端每次异步请求带代次令牌，过期响应直接丢弃；结局详情必须显式带
  修订号，跨修订的路线标识返回 422——旧异步响应不能贴到新修订。

## 目录

```
api/    Python 3.12 + Flask + SQLite（engine/ 为纯函数校样引擎，零 Web 依赖）
web/    Vue 3 + TypeScript + Canvas（路线泳道、分钟时间带、离散空洞、结局矩阵）
verify/ 一次性核验服务（pytest + vite build + 真实 HTTP 端到端）
docker-compose.yml  web / api 常驻 + verify 一次性
```

## 用 Compose 运行

```bash
WEB_PORT=8080 API_PORT=8000 docker compose up --build
```

* 打开 http://localhost:8080 使用校样应用（宿主端口可用
  `WEB_PORT` / `API_PORT` 调整）；
* `verify` 容器在 web/api 健康后运行：引擎与传播算法测试、API 测试、
  前端生产构建，然后通过**真实 HTTP** 打开校样页、提交故事板，
  打印 `VERIFY OK` 后退出；
* 只启动常驻组件：`docker compose up --build web api`。

首次启动会播种一条修订链：通过样例 `sample_valid` 与三个确定性反例
（画廊多停一分钟 / 缺最短转场 / 跨支线消息）。

## 本地开发（不使用 Docker）

```bash
# 后端
python3 -m venv .venv && . .venv/bin/activate
pip install -r api/requirements.txt
cd api && SEED_SAMPLES=1 python wsgi.py            # :8000

# 前端
cd web && npm install && npm run dev               # :5173，/api 代理到 :8000

# 只跑测试
cd api && python -m pytest tests -q
cd web && npm run build
```

## 故事板 JSON 结构

```json
{
  "title": "可选标题",
  "start": "gate",
  "scenes": [
    {
      "id": "gate",
      "label": "校门",
      "location": "校门广场",
      "durations": [1],
      "choices": [
        { "to": "gallery", "label": "绕钟楼方向" },
        { "to": "corridor_w", "label": "穿连廊方向" }
      ]
    }
  ],
  "windows":    [ { "scene": "belltower", "open": 5, "close": 8 } ],
  "transitions": [ { "from": "艺术楼", "to": "钟楼", "minutes": 2 } ],
  "meetings":   [ { "kind": "meeting", "scene_a": "belltower",
                    "scene_b": "belltower", "label": "钟声会面" } ],
  "messages":   [ { "kind": "message",
                    "send_role": "a", "send_scene": "gate",
                    "read_role": "b", "read_scene": "belltower",
                    "label": "出发口信" } ]
}
```

约束：单一起点；场景图有限且无环；每个场景 1~3 个整数分钟时长；
选择边按数组顺序裁决；窗口、会面、消息只能引用存在的场景。

## 测试覆盖（28 项）

* 离散时刻空洞（第 3 分钟不在 {2,4} 里不可会面）；
* 不同来路同刻合流仍保持独立路线/结局；
* 消息严格时序与跨支线引用缺失；
* 地点不可达（缺最短转场）与显式 0 分钟转场；
* 确定性反例与首矛盾排序、可复述内容；
* **窗口漏报回归**：违规窗口挂在路线中途场景（而非终点）时，
  逐结局同样判矛盾，未经过该场景的结局不被连坐；
* 影响域：时长向下游、窗口向上游、转场精确到跨越边、约束变更全量、
  无编辑空影响域；
* API：冻结校样不漂移、结构错误 422 不落库、跨修订路线拒绝、预演不落库。

## 健康检查与离线降级

* web 容器 nginx 同时监听 IPv4/IPv6 的 80 端口，Compose 健康检查
  固定访问 `http://127.0.0.1/healthz`，避免 localhost 解析到 `::1` 误判；
* 前端在后端尚未就绪时仍渲染编辑器（空白故事板），健康轮询恢复后
  自动载入样例与修订；连接中断可手动“重试连接”。
