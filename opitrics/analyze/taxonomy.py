"""The aspect taxonomy clusters get mapped onto.

Clustering finds themes bottom-up; this list gives them fixed axes so
two different cars can be charted against each other. A cluster that
matches nothing here stays unmapped, and that pile is where genuinely
new topics show up — a spreading recall, a viral defect, a scandal.

Each aspect carries a `description`: a short bilingual keyword phrase
that clusters are matched against by embedding similarity. These are
deliberately written as the vocabulary people actually use rather than
as formal definitions, and lead with Japanese because that is the
language most of this corpus is written in. Add the terms real
commenters reach for — including slang — when extending this list.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Aspect:
    key: str
    group: str
    label: str
    # Short bilingual keyword phrase. Comments are matched against this
    # by embedding similarity, so it should read like the vocabulary
    # people actually use — not like a formal definition.
    description: str
    # Aspects that only apply to some vehicles. None = always applies.
    applies_to: str | None = None
    # Meta aspects are about the video, the channel or the argument —
    # not about the car. They are scored separately and excluded from
    # headline sentiment, or they quietly corrupt it.
    is_meta: bool = False


CORE: list[Aspect] = [
    # ── Ownership & cost ────────────────────────────────────
    Aspect("cost.maintenance", "Ownership & cost", "maintenance cost",
           "整備 修理 メンテナンス費用 車検 維持費 maintenance repair servicing cost"),
    Aspect("cost.parts", "Ownership & cost", "parts & availability",
           "部品 パーツ供給 部品が手に入らない 純正部品 spare parts availability supply"),
    Aspect("cost.reliability", "Ownership & cost", "reliability",
           "故障 壊れる 信頼性 トラブル 初期不良 breaks down reliability faults"),
    Aspect("cost.durability", "Ownership & cost", "durability & rust",
           "耐久性 錆 サビ 経年劣化 何年もつ durability rust corrosion long term wear"),
    Aspect("cost.resale", "Ownership & cost", "resale value",
           "リセール 下取り 買取価格 残価 値落ち resale trade-in residual value"),
    Aspect("cost.warranty", "Ownership & cost", "warranty & support",
           "保証 アフターサービス サポート体制 warranty after-sales support"),
    Aspect("cost.running", "Ownership & cost", "running cost",
           "電気代 燃費 税金 保険 ランニングコスト running cost electricity tax insurance"),

    # ── Build & quality ─────────────────────────────────────
    Aspect("build.materials", "Build & quality", "material quality",
           "内装の素材 プラスチック チープ 質感 安っぽい material quality plastics cheap feel"),
    Aspect("build.fit", "Build & quality", "fit & finish",
           "建て付け 隙間 チリ 組み立て精度 作りが雑 panel gaps fit and finish assembly"),
    Aspect("build.underbody", "Build & quality", "underbody & chassis",
           "下回り 足回り シャーシ 溶接 剥き出し underbody chassis suspension construction"),
    Aspect("build.noise", "Build & quality", "rattles & noise",
           "異音 きしみ ビビリ音 カタカタ rattles squeaks unwanted noise"),

    # ── Driving ─────────────────────────────────────────────
    Aspect("drive.power", "Driving", "power & acceleration",
           "加速 パワー モーター出力 トルク acceleration power motor output"),
    Aspect("drive.ride", "Driving", "ride comfort",
           "乗り心地 突き上げ バタバタ感 快適性 ride comfort bumps harshness"),
    Aspect("drive.handling", "Driving", "handling & stability",
           "ハンドリング 操縦安定性 コーナリング ふらつき handling stability cornering"),
    Aspect("drive.nvh", "Driving", "quietness",
           "静粛性 ロードノイズ 風切り音 静か quietness road noise wind noise"),
    Aspect("drive.braking", "Driving", "braking",
           "ブレーキ 回生ブレーキ 制動 止まらない brakes braking stopping"),
    Aspect("drive.weight", "Driving", "vehicle weight",
           "車重 重い 1200kg 軽いのに重い vehicle weight heavy kerb weight"),

    # ── Practicality ────────────────────────────────────────
    Aspect("prac.space", "Practicality", "interior space",
           "室内 広さ 頭上空間 足元 居住性 cabin space headroom legroom roomy"),
    Aspect("prac.cargo", "Practicality", "cargo & boot",
           "荷室 ラゲッジ 積載量 トランク cargo boot luggage capacity"),
    Aspect("prac.seats", "Practicality", "seats & comfort",
           "シート 座り心地 シートアレンジ パワーシート seats seating comfort"),
    Aspect("prac.access", "Practicality", "doors & access",
           "スライドドア ドア 乗り降り 開口部 sliding doors access getting in and out"),
    Aspect("prac.clearance", "Practicality", "ground clearance",
           "最低地上高 車高 130mm 腹を擦る 段差 ground clearance ride height"),

    # ── Tech & features ─────────────────────────────────────
    Aspect("tech.infotainment", "Tech & features", "infotainment",
           "ナビ ディスプレイ タッチパネル インフォテインメント infotainment touchscreen navigation"),
    Aspect("tech.adas", "Tech & features", "driver assistance",
           "運転支援 自動ブレーキ ADAS 先進安全 driver assistance autonomous safety systems"),
    Aspect("tech.equipment", "Tech & features", "equipment level",
           "装備 標準装備 快適装備 装備が充実 equipment features specification"),
    Aspect("tech.safety", "Tech & features", "crash safety",
           "衝突安全性 衝突試験 NCAP 事故 crash safety crash test collision"),

    # ── Design ──────────────────────────────────────────────
    Aspect("design.exterior", "Design", "exterior styling",
           "エクステリア 外観 デザイン かっこいい ダサい exterior styling looks design"),
    Aspect("design.interior", "Design", "interior design",
           "インテリア 内装デザイン 室内の雰囲気 interior design cabin look"),
    Aspect("design.naming", "Design", "model name",
           "ラッコ という名前 ネーミング 車名 the name Racco model name naming"),
    Aspect("design.derivative", "Design", "derivative design",
           "パクリ 真似 そっくり N-BOXのパチもん copy imitation derivative lookalike"),

    # ── Commercial ──────────────────────────────────────────
    Aspect("comm.price", "Commercial", "price & value",
           "価格 値段 高い 安い コスパ 割安 price value expensive cheap"),
    Aspect("comm.rivals", "Commercial", "versus rivals",
           "N-BOX サクラ スペーシア タント 比較 ライバル versus rivals comparison"),
    Aspect("comm.dealer", "Commercial", "dealer network",
           "ディーラー 販売店 店舗数 商談 dealership showroom sales network"),
    Aspect("comm.sales", "Commercial", "sales & demand",
           "売れる 売れない 販売台数 受注 キャンセル sales demand orders"),
    Aspect("comm.subsidy", "Commercial", "subsidies & incentives",
           "補助金 助成金 減税 優遇 subsidy grant incentive tax break"),

    # ── Brand & origin ──────────────────────────────────────
    # This corpus made the case for its own group: a large share of
    # comments are about who built the car, not about the car.
    Aspect("brand.origin", "Brand & origin", "country of origin",
           "中国製 中国車 made in China 生産国 country of origin chinese made"),
    Aspect("brand.trust", "Brand & origin", "brand trust",
           "信用できない 信頼できるメーカーか BYDというだけで brand trust can we trust the maker"),
    Aspect("brand.longevity", "Brand & origin", "will they stay?",
           "撤退 何年後に居るのか 突然いなくなる will they stay withdraw from market long term presence"),
    Aspect("brand.domestic", "Brand & origin", "domestic industry",
           "日本メーカー 国内産業 日本車の危機 競争 domestic carmakers local industry competition"),
    Aspect("brand.geopolitics", "Brand & origin", "politics",
           "政治 領海侵犯 反日 愛国 国際関係 politics nationalism international relations"),
    Aspect("brand.data", "Brand & origin", "data & security",
           "情報漏洩 データ 監視 セキュリティ スパイ data privacy surveillance security"),

    # ── Meta — not about the car ────────────────────────────
    Aspect("meta.reviewer", "Meta", "the reviewer",
           "五味さん レビュアー 忖度 この人の評価 the reviewer presenter his opinion",
           is_meta=True),
    Aspect("meta.video", "Meta", "the video",
           "この動画 チャンネル 編集 分かりやすい解説 this video the channel production",
           is_meta=True),
    Aspect("meta.sponsorship", "Meta", "sponsorship claims",
           "案件 いくら貰った ステマ 提灯記事 paid sponsored shill bias accusation",
           is_meta=True),
    Aspect("meta.argument", "Meta", "arguing with commenters",
           "@ 返信 お前 論破 コメント欄の言い合い replying arguing with another commenter",
           is_meta=True),
    Aspect("meta.chatter", "Meta", "chatter & thanks",
           "ありがとうございます 笑 なるほど 短い相槌 thanks lol short reaction no opinion",
           is_meta=True),
]

ADDONS: list[Aspect] = [
    # ── EV ──────────────────────────────────────────────────
    Aspect("ev.general", "EV", "EVs in general", applies_to="ev",
           description="EVはいらない EV普及 電気自動車への賛否 ガソリン車の方がいい opinions about EVs in general"),
    Aspect("ev.range", "EV", "real-world range", applies_to="ev",
           description="航続距離 実走行距離 一充電走行 180km 320km real world range how far on a charge"),
    Aspect("ev.charging", "EV", "charging speed & access", applies_to="ev",
           description="充電 急速充電 充電スタンド 充電時間 自宅充電 charging speed charging stations"),
    Aspect("ev.battery", "EV", "battery & degradation", applies_to="ev",
           description="バッテリー 電池 劣化 交換費用 LFP battery degradation replacement cost"),
    Aspect("ev.fire", "EV", "fire & battery safety", applies_to="ev",
           description="発火 炎上 燃える 火災 バッテリー火災 battery fire catching fire"),
    Aspect("ev.cold", "EV", "cold weather", applies_to="ev",
           description="寒冷地 冬 雪 暖房 電費悪化 cold weather winter snow heating range loss"),

    # ── Trucks & SUVs ───────────────────────────────────────
    Aspect("util.towing", "Utility", "towing", applies_to="truck",
           description="牽引 トレーラー けん引能力 towing trailer caravan"),
    Aspect("util.offroad", "Utility", "off-road", applies_to="truck",
           description="オフロード 悪路 雪道 未舗装 off-road rough terrain"),
    Aspect("util.payload", "Utility", "payload", applies_to="truck",
           description="積載 荷物 最大積載量 payload load carrying capacity"),

    # ── Kei ─────────────────────────────────────────────────
    Aspect("kei.class", "Kei", "kei class rules", applies_to="kei",
           description="軽自動車規格 軽枠 660cc 黄色ナンバー 軽の定義 kei car regulations size limits"),
    Aspect("kei.suitability", "Kei", "fit for kei buyers", applies_to="kei",
           description="軽ユーザー 主婦 セカンドカー 近所の足 軽に求めるもの suits typical kei buyers needs"),
]

ALL: list[Aspect] = CORE + ADDONS

BY_KEY: dict[str, Aspect] = {a.key: a for a in ALL}


def aspects_for(vehicle_types: list[str] | None = None) -> list[Aspect]:
    """Core aspects plus the add-ons relevant to this vehicle.

    `vehicle_types` is a list because a car can be several things at
    once — the BYD Racco is both a kei car and an EV, and both sets of
    concerns show up in its comments.
    """
    types = set(vehicle_types or [])
    return [a for a in ALL if a.applies_to is None or a.applies_to in types]


def car_aspects(aspects: list[Aspect]) -> list[Aspect]:
    """Only the aspects that are actually about the car."""
    return [a for a in aspects if not a.is_meta]
