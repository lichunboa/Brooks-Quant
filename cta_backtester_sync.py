"""CTA 回测结果同步到 Brooks 图表。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backtest_result_utils import (
    normalize_stats_payload,
    write_json,
    write_lifecycles_csv,
    write_trades_csv,
)

ROOT_DIR: Path = Path(__file__).resolve().parent
CTA_GUI_OUTPUT_ROOT: Path = ROOT_DIR / "backtests" / "output" / "cta_gui_runs"
CTA_GUI_LATEST_ROOT: Path = ROOT_DIR / "backtests" / "output" / "cta_gui_latest"


def patch_cta_backtester_sync() -> None:
    """给 vnpy_ctabacktester 注入自动导出。"""
    import vnpy_ctabacktester.engine as cta_backtester_engine

    if getattr(cta_backtester_engine.BacktesterEngine, "_brooks_sync_patched", False):
        return

    original_run_backtesting = cta_backtester_engine.BacktesterEngine.run_backtesting

    def run_backtesting_and_export(
        self,
        class_name: str,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        rate: float,
        slippage: float,
        size: int,
        pricetick: float,
        capital: int,
        setting: dict,
    ) -> None:
        original_run_backtesting(
            self,
            class_name,
            vt_symbol,
            interval,
            start,
            end,
            rate,
            slippage,
            size,
            pricetick,
            capital,
            setting,
        )

        if not self.result_statistics:
            return

        export_cta_backtest_result(
            class_name=class_name,
            vt_symbol=vt_symbol,
            interval=interval,
            start=start,
            end=end,
            setting=setting,
            stats=self.result_statistics,
            daily_df=self.result_df,
            engine=self.backtesting_engine,
            engine_parameters={
                "rate": rate,
                "slippage": slippage,
                "size": size,
                "pricetick": pricetick,
                "capital": capital,
            },
        )

    cta_backtester_engine.BacktesterEngine.run_backtesting = run_backtesting_and_export
    cta_backtester_engine.BacktesterEngine._brooks_sync_patched = True


def export_cta_backtest_result(
    *,
    class_name: str,
    vt_symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    setting: dict,
    stats: dict,
    daily_df,
    engine,
    engine_parameters: dict,
) -> None:
    """导出 CTA GUI 回测结果。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = CTA_GUI_OUTPUT_ROOT / stamp
    latest_dir = CTA_GUI_LATEST_ROOT
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "source": "cta_gui",
        "strategy_key": class_name,
        "strategy": class_name,
        "signal_window": setting.get("signal_window", ""),
        "vt_symbol": vt_symbol,
        "interval": interval,
        "start": start.isoformat(sep=" "),
        "end": end.isoformat(sep=" "),
        "setting": setting,
        "engine_parameters": engine_parameters,
    }

    write_json(run_dir / "meta.json", meta)
    normalized_stats = normalize_stats_payload(stats)
    write_json(run_dir / "stats.json", normalized_stats)
    write_trades_csv(run_dir / "trades.csv", engine)
    write_lifecycles_csv(run_dir / "lifecycles.csv", engine)

    if daily_df is not None and not daily_df.empty:
        daily_df.to_csv(run_dir / "daily.csv", encoding="utf-8-sig")

    figure = engine.show_chart()
    if figure:
        figure.write_html(run_dir / "report.html", include_plotlyjs="cdn")

    write_json(latest_dir / "latest_meta.json", meta)
    write_json(latest_dir / "latest_stats.json", normalized_stats)
    write_trades_csv(latest_dir / "latest_trades.csv", engine)
    write_lifecycles_csv(latest_dir / "latest_lifecycles.csv", engine)
    if daily_df is not None and not daily_df.empty:
        daily_df.to_csv(latest_dir / "latest_daily.csv", encoding="utf-8-sig")
    if figure:
        figure.write_html(latest_dir / "latest_report.html", include_plotlyjs="cdn")
