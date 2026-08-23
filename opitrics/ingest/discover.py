"""Find what is worth analysing before you have decided what to analyse.

Four signals, each catching something the others miss:

  trending      YouTube's own Autos & Vehicles chart. Cheap, but late —
                a video is already big by the time it charts.
  velocity      Views per hour on recent uploads from watched channels.
                Catches a video on the way up rather than at the top.
  argument      Comments per view. A video with an unusual comment rate
                is one people are fighting over, and a fight is content.
  convergence   The same model covered by many channels in a short
                window. This is the launch-moment signal, and nothing
                else surfaces it.

Convergence is what turns a list of hot videos into a list of hot
*cars*, which is the actual question.
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from opitrics.ingest.youtube import COST_LIST, Video, YouTubeClient

log = logging.getLogger(__name__)

AUTOS_CATEGORY = "2"

# Regions swept for coverage, not for comparison — a car's conversation
# lives wherever it is sold.
DEFAULT_REGIONS = ["JP", "US", "GB", "DE", "AU", "ID"]

# Review vocabulary, in the languages this tool actually reads. These
# find model coverage that the trending chart does not surface.
REVIEW_QUERIES = [
    "新型 試乗 レビュー",
    "新車 徹底 比較 試乗",
    "first drive review new car",
    "new car review 2026",
]


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hours_since(value: str) -> float:
    delta = datetime.now(timezone.utc) - _parse_ts(value)
    return max(delta.total_seconds() / 3600, 1.0)


@dataclass
class VideoHeat:
    video: Video
    region: str | None = None
    signals: dict[str, float] = field(default_factory=dict)

    @property
    def views_per_hour(self) -> float:
        return (self.video.view_count or 0) / _hours_since(self.video.published_at)

    @property
    def comments_per_1k_views(self) -> float:
        views = self.video.view_count or 0
        if views < 500:
            return 0.0
        return 1000 * (self.video.comment_count or 0) / views

    @property
    def score(self) -> float:
        return sum(self.signals.values())


@dataclass
class ModelHeat:
    """A car model, and the evidence that it is having a moment."""

    name: str
    videos: list[VideoHeat] = field(default_factory=list)

    @property
    def channels(self) -> set[str]:
        return {v.video.channel_id for v in self.videos}

    @property
    def total_views(self) -> int:
        return sum(v.video.view_count or 0 for v in self.videos)

    @property
    def total_comments(self) -> int:
        return sum(v.video.comment_count or 0 for v in self.videos)

    @property
    def argument_rate(self) -> float:
        """Comments per 1,000 views across the model's coverage."""
        if self.total_views < 1000:
            return 0.0
        return 1000 * self.total_comments / self.total_views

    @property
    def convergence(self) -> int:
        """Distinct channels covering it. The launch-moment signal."""
        return len(self.channels)

    @property
    def newest_hours(self) -> float:
        return min(_hours_since(v.video.published_at) for v in self.videos)

    @property
    def score(self) -> float:
        """Combined heat.

        Convergence is weighted hardest because it is the signal that
        distinguishes "a car everyone is covering" from "one popular
        video". Recency decays over roughly a month, so a launch that
        has gone quiet stops competing with one happening now.
        """
        convergence = math.log1p(self.convergence) * 3.2
        volume = math.log1p(self.total_views / 1000) * 0.9
        argument = min(self.argument_rate, 12) * 0.35
        recency = math.exp(-self.newest_hours / (24 * 30))
        return (convergence + volume + argument) * (0.45 + 0.55 * recency)

    @property
    def why(self) -> str:
        bits = [f"{self.convergence} channels"]
        if self.total_views:
            bits.append(f"{self.total_views:,} views")
        if self.argument_rate > 4:
            bits.append(f"{self.argument_rate:.1f} comments/1k — contentious")
        days = self.newest_hours / 24
        bits.append("today" if days < 1 else f"{days:.0f}d ago")
        return " · ".join(bits)


# Tokens that appear in automotive titles but are never model names.
TITLE_NOISE = {
    "test", "drive", "review", "first", "look", "new", "the", "and", "vs",
    "car", "cars", "ev", "electric", "suv", "video", "full", "best", "top",
    "why", "how", "what", "this", "that", "now", "buy", "price", "specs",
    "試乗", "レビュー", "新型", "比較", "解説", "納車", "内装", "外装",
    "徹底", "登場", "発表", "衝撃", "本音", "公開", "速報", "驚愕",
}

BRANDS = [
    "toyota", "honda", "nissan", "mazda", "subaru", "suzuki", "daihatsu",
    "mitsubishi", "lexus", "byd", "tesla", "hyundai", "kia", "geely",
    "chery", "wuling", "great wall", "gwm", "xpeng", "nio", "li auto",
    "volkswagen", "vw", "audi", "bmw", "mercedes", "porsche", "volvo",
    "ford", "chevrolet", "jeep", "ram", "peugeot", "renault", "citroen",
    "fiat", "skoda", "seat", "mg", "cupra", "polestar", "rivian", "lucid",
    "トヨタ", "ホンダ", "日産", "マツダ", "スバル", "スズキ", "ダイハツ",
    "三菱", "レクサス", "テスラ", "ヒョンデ", "ベンツ", "アウディ",
]


# Model names common enough to recognise on their own. Japanese titles
# very often name only the model — 「ラッコ試乗」 never says BYD — so
# brand-adjacency alone misses most of the domestic conversation.
KNOWN_MODELS = {
    # kei / Japan
    "n-box": "Honda N-BOX", "nbox": "Honda N-BOX", "ｎ-ｂｏｘ": "Honda N-BOX",
    "n-one": "Honda N-ONE", "スペーシア": "Suzuki Spacia", "タント": "Daihatsu Tanto",
    "ワゴンr": "Suzuki Wagon R", "ハスラー": "Suzuki Hustler", "ジムニー": "Suzuki Jimny",
    "サクラ": "Nissan Sakura", "ekクロス": "Mitsubishi eK X", "ムーヴ": "Daihatsu Move",
    "ラッコ": "BYD Racco", "racco": "BYD Racco",
    # Japan mainstream
    "プリウス": "Toyota Prius", "prius": "Toyota Prius", "アクア": "Toyota Aqua",
    "ヤリス": "Toyota Yaris", "カローラ": "Toyota Corolla", "クラウン": "Toyota Crown",
    "アルファード": "Toyota Alphard", "ヴェルファイア": "Toyota Vellfire",
    "ランドクルーザー": "Toyota Land Cruiser", "ハイエース": "Toyota HiAce",
    "シビック": "Honda Civic", "フィット": "Honda Fit", "ヴェゼル": "Honda Vezel",
    "ノート": "Nissan Note", "セレナ": "Nissan Serena", "エクストレイル": "Nissan X-Trail",
    "ロードスター": "Mazda Roadster", "cx-5": "Mazda CX-5", "cx-60": "Mazda CX-60",
    "フォレスター": "Subaru Forester", "レヴォーグ": "Subaru Levorg",
    "スカイライン": "Nissan Skyline", "gt-r": "Nissan GT-R", "フェアレディ": "Nissan Fairlady",
    # global
    "model y": "Tesla Model Y", "model 3": "Tesla Model 3",
    "cybertruck": "Tesla Cybertruck", "ioniq": "Hyundai Ioniq",
    "atto 3": "BYD Atto 3", "seal": "BYD Seal", "dolphin": "BYD Dolphin",
    "id.3": "Volkswagen ID.3", "id.4": "Volkswagen ID.4",
}


def extract_model(title: str, description: str = "") -> str | None:
    """Guess the car this video is about from its title.

    Deliberately conservative: a wrong model name silently merges two
    cars' comment sections, which is worse than returning None and
    letting the video be skipped. Tries a known-model dictionary first,
    then falls back to brand-plus-adjacent-token.

    Known limitation: this identifies which car a title *mentions*, not
    whether the video is a review of it. A dashcam clip captioned
    「プリウスミサイル」 resolves to Toyota Prius. The convergence
    filter absorbs most of this — crash clips rarely appear across
    multiple channels for the same model in the same window — but check
    the listed videos before committing to a fetch.
    """
    text = f"{title} {description[:200]}"
    lowered = text.lower()

    # Longest match first, so "model y" wins over a bare "model".
    for needle in sorted(KNOWN_MODELS, key=len, reverse=True):
        if needle in lowered:
            return KNOWN_MODELS[needle]

    for brand in BRANDS:
        idx = lowered.find(brand)
        if idx < 0:
            continue

        # Look at what follows the brand name for the model token.
        tail = text[idx + len(brand) : idx + len(brand) + 40]
        tokens = re.findall(
            r"[A-Za-z0-9][A-Za-z0-9\-]{1,14}|[ぁ-んァ-ヶー一-鿿]{2,10}", tail
        )
        for token in tokens:
            if token.lower() in TITLE_NOISE or len(token) < 2:
                continue
            if token.isdigit() and len(token) == 4:
                continue  # a year, not a model
            return f"{brand.title()} {token}".strip()

    return None


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug or "unknown"


class Discovery:
    def __init__(self, client: YouTubeClient) -> None:
        self.client = client

    # ── signal 1: trending ──────────────────────────────────

    def trending(self, regions: list[str] | None = None, per_region: int = 25) -> list[VideoHeat]:
        """YouTube's own Autos & Vehicles chart, per region."""
        found: list[VideoHeat] = []
        for region in regions or DEFAULT_REGIONS:
            self.client._spend("videos.list:chart", COST_LIST)
            try:
                resp = (
                    self.client._yt.videos()
                    .list(
                        part="snippet,statistics,contentDetails",
                        chart="mostPopular",
                        videoCategoryId=AUTOS_CATEGORY,
                        regionCode=region,
                        maxResults=min(per_region, 50),
                    )
                    .execute()
                )
            except Exception as exc:  # noqa: BLE001 - one bad region must not stop the sweep
                log.warning("trending failed for %s: %s", region, exc)
                continue

            for item in resp.get("items", []):
                video = _video_from_item(item)
                heat = VideoHeat(video=video, region=region)
                heat.signals["trending"] = 2.0
                found.append(heat)

        log.info("trending: %d videos across %d regions",
                 len(found), len(regions or DEFAULT_REGIONS))
        return found

    # ── signal 1b: review search ────────────────────────────

    def review_sweep(
        self,
        queries: list[str] | None = None,
        within_days: int = 45,
        per_query: int = 30,
    ) -> list[VideoHeat]:
        """Search for recent review content directly.

        The trending chart turned out to be a poor source for this:
        Autos & Vehicles trends on dashcam clips, motorcycle shorts and
        viral crash compilations, not on model reviews. Measured on a
        150-video sweep, only about a third mentioned any car model at
        all. Searching review vocabulary finds the actual conversation.

        Costs 100 units per query, so keep the list short.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=within_days)
        ).isoformat().replace("+00:00", "Z")

        found: list[VideoHeat] = []
        for query in queries or REVIEW_QUERIES:
            self.client._spend("search.list:reviews", 100)
            try:
                resp = (
                    self.client._yt.search()
                    .list(
                        part="id",
                        q=query,
                        type="video",
                        order="viewCount",
                        publishedAfter=cutoff,
                        maxResults=min(per_query, 50),
                    )
                    .execute()
                )
            except Exception as exc:  # noqa: BLE001 - one bad query must not stop the sweep
                log.warning("review search failed for %r: %s", query, exc)
                continue

            ids = [i["id"]["videoId"] for i in resp.get("items", [])]
            for video in self.client.get_videos(ids):
                heat = VideoHeat(video=video)
                heat.signals["review"] = 1.5
                found.append(heat)

        log.info("review sweep: %d videos from %d queries",
                 len(found), len(queries or REVIEW_QUERIES))
        return found

    # ── signal 2: channel velocity ──────────────────────────

    def channel_velocity(
        self, channel_ids: list[str], within_days: int = 21, per_channel: int = 10
    ) -> list[VideoHeat]:
        """Recent uploads from watched channels, ranked by views/hour.

        Costs 100 units per channel because it needs search — use a
        short, curated channel list rather than a broad one.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=within_days)).isoformat()
        found: list[VideoHeat] = []

        for channel_id in channel_ids:
            self.client._spend("search.list:channel", 100)
            try:
                resp = (
                    self.client._yt.search()
                    .list(
                        part="id",
                        channelId=channel_id,
                        type="video",
                        order="date",
                        publishedAfter=cutoff.replace("+00:00", "Z"),
                        maxResults=per_channel,
                    )
                    .execute()
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("velocity failed for %s: %s", channel_id, exc)
                continue

            ids = [i["id"]["videoId"] for i in resp.get("items", [])]
            for video in self.client.get_videos(ids):
                heat = VideoHeat(video=video)
                vph = heat.views_per_hour
                if vph > 200:
                    heat.signals["velocity"] = min(math.log1p(vph / 100), 4.0)
                    found.append(heat)

        log.info("velocity: %d fast-rising videos", len(found))
        return found

    # ── signal 3: argument rate ─────────────────────────────

    @staticmethod
    def score_argument(videos: list[VideoHeat]) -> None:
        """Flag videos whose comment rate is unusually high.

        Scored in place. A high comment-to-view ratio means people are
        replying to each other, not just watching.
        """
        for heat in videos:
            rate = heat.comments_per_1k_views
            if rate > 3:
                heat.signals["argument"] = min(rate / 3, 3.0)

    # ── signal 4: convergence ───────────────────────────────

    @staticmethod
    def group_by_model(videos: list[VideoHeat]) -> list[ModelHeat]:
        """Collapse videos into the models they are about.

        Videos whose model cannot be identified are dropped rather than
        guessed at — see `extract_model`.
        """
        groups: dict[str, ModelHeat] = {}
        unknown = 0

        for heat in videos:
            model = extract_model(heat.video.title)
            if not model:
                unknown += 1
                continue
            key = model.lower()
            groups.setdefault(key, ModelHeat(name=model)).videos.append(heat)

        if unknown:
            log.info("%d videos had no identifiable model", unknown)

        # A single video is a video, not a moment.
        return [m for m in groups.values() if m.convergence >= 2]

    # ── the sweep ───────────────────────────────────────────

    def sweep(
        self,
        regions: list[str] | None = None,
        channels: list[str] | None = None,
        min_channels: int = 2,
        reviews: bool = True,
        queries: list[str] | None = None,
    ) -> list[ModelHeat]:
        """Run every signal and return models ranked by heat."""
        videos = self.trending(regions)
        if reviews:
            videos.extend(self.review_sweep(queries))
        if channels:
            videos.extend(self.channel_velocity(channels))

        # De-duplicate: the same video can trend in several regions.
        seen: dict[str, VideoHeat] = {}
        for heat in videos:
            existing = seen.get(heat.video.video_id)
            if existing:
                for key, value in heat.signals.items():
                    existing.signals[key] = max(existing.signals.get(key, 0), value)
            else:
                seen[heat.video.video_id] = heat

        deduped = list(seen.values())
        self.score_argument(deduped)

        models = self.group_by_model(deduped)
        models = [m for m in models if m.convergence >= min_channels]
        models.sort(key=lambda m: -m.score)
        return models


def _video_from_item(item: dict) -> Video:
    snip = item["snippet"]
    stats = item.get("statistics", {})

    def as_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return Video(
        video_id=item["id"],
        title=snip["title"],
        channel_id=snip["channelId"],
        channel_title=snip["channelTitle"],
        published_at=snip["publishedAt"],
        view_count=as_int(stats.get("viewCount")),
        like_count=as_int(stats.get("likeCount")),
        comment_count=as_int(stats.get("commentCount")),
        duration=item.get("contentDetails", {}).get("duration"),
        default_lang=snip.get("defaultAudioLanguage") or snip.get("defaultLanguage"),
    )
