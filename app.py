from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Energy Trade Journal", page_icon="📒", layout="wide")

# Streamlit Cloud stores deployment secrets in st.secrets. Mirror them into
# environment variables before database.py creates its SQLAlchemy engine.
for _key in ("DATABASE_URL", "JOURNAL_TRADER_USER", "JOURNAL_TRADER_PASS", "JOURNAL_MENTOR_TOKEN"):
    try:
        _value = st.secrets.get(_key)
    except Exception:
        _value = None
    if _value and not os.getenv(_key):
        os.environ[_key] = str(_value)

from database import (
    close_trade,
    create_trade,
    delete_trade,
    get_entry_fills,
    get_trade,
    get_trades,
    get_weekly_note,
    init_db,
    save_weekly_note,
    update_live_trade,
    update_trade,
    get_database_backend,
)

init_db()

PRODUCTS = ["CL", "CO", "NG", "FCPO", "G", "GC", "HG", "HO", "NGHH", "RB", "SI", "Other"]
STRUCTURES = ["Outright", "Spread", "Fly", "D-Fly", "1M-Fly", "1M-DFly", "2M-Spread", "2M-Fly", "2M-DFly", "Custom"]
TRADERS = ["Suraj Kumar", "Amiyendra Senapati"]

TRADER_USER = os.getenv("JOURNAL_TRADER_USER", "trader")
TRADER_PASS = os.getenv("JOURNAL_TRADER_PASS", "trade123")
MENTOR_TOKEN = os.getenv("JOURNAL_MENTOR_TOKEN", "local-mentor-demo-token-change-me")


def inject_css():
    st.markdown(
        """
        <style>
        .block-container {padding-top: 2.5rem; padding-bottom: 2rem; max-width: 1500px;}
        .journal-title {font-size:2rem; font-weight:800; color:#0F3325; margin:0 0 .15rem 0; padding-top:.20rem; line-height:1.35;}
        .journal-sub {color:#63736b; margin-bottom:1rem;}
        .sheet-title {font-size:1.35rem; font-weight:800; color:#0F3325; margin:.35rem 0 .75rem 0; line-height:1.35;}
        div[data-testid="stMetric"] {background:#ffffff; border:1px solid #d9e2dd; padding:12px 14px; border-radius:8px;}
        div[data-testid="stDataFrame"] {border:1px solid #d9e2dd; border-radius:6px;}
        .live-badge {background:#dff2e7;color:#17663b;padding:3px 9px;border-radius:12px;font-weight:700;}
        .closed-badge {background:#ecefed;color:#59635e;padding:3px 9px;border-radius:12px;font-weight:700;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def mentor_access_active() -> bool:
    """Return True only when the secret mentor token is present in the URL."""
    try:
        return st.query_params.get("mentor") == MENTOR_TOKEN
    except Exception:
        return False


def login():
    # A mentor using the secret read-only URL never sees the login page.
    if mentor_access_active():
        return
    if st.session_state.get("auth"):
        return
    inject_css()
    st.markdown('<div class="journal-title">Energy Trade Journal</div>', unsafe_allow_html=True)
    st.markdown('<div class="journal-sub">Trader sign-in</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.15, 1])
    with c2:
        with st.form("login_form"):
            st.subheader("Sign in")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            if username == TRADER_USER and password == TRADER_PASS:
                st.session_state.update(auth=True, role="Trader", username=username)
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()


def raw_df() -> pd.DataFrame:
    trades = get_trades()
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    for col in ["entry_date", "exit_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")
    df["ticks_result"] = pd.to_numeric(df["ticks_result"], errors="coerce")
    return df


def excel_style_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "Trade ID": df["id"],
        "Date": df["entry_date"].dt.date,
        "Product": df["product"],
        "Strategy": df["contract_details"].fillna("").where(df["contract_details"].fillna("") != "", df["structure"]),
        "Structure": df["structure"],
        "Position": df["direction"],
        "Status": df["trade_status"],
        "Stake / Qty": df["quantity"],
        "Entry": df["average_entry"],
        "Exit": df["exit_price"],
        "PnL (Ticks)": df["ticks_result"],
        "PnL ($)": df["pnl"],
        "Open Date": df["entry_date"].dt.date,
        "Close Date": df["exit_date"].dt.date,
        "Entry Idea": df["entry_idea"],
        "Exit Idea": df["exit_idea"],
        "Exit Reason": df["exit_reason"],
        "Trader": df["trader_name"],
        "Remarks": df["remarks"],
    })
    return out.sort_values(["Date", "Trade ID"], ascending=[False, False])


def page_trade_log(read_only: bool):
    st.markdown('<div class="sheet-title">01 — Trade Data</div>', unsafe_allow_html=True)
    st.caption("This is the Streamlit equivalent of the Excel 01-data sheet. Every trade is stored here; LIVE trades simply have no exit yet.")

    if not read_only:
        with st.expander("➕ Add New Trade", expanded=False):
            trade_entry_form()

    df = raw_df()
    if df.empty:
        st.info("No trades have been entered yet. The journal database is empty.")
        return

    c1, c2, c3, c4 = st.columns(4)
    status_opt = c1.multiselect("Status", ["LIVE", "CLOSED"], default=["LIVE", "CLOSED"])
    prod_opt = sorted(df["product"].dropna().unique())
    prod = c2.multiselect("Product", prod_opt, default=prod_opt)
    trader_opt = sorted(df["trader_name"].dropna().unique())
    trader = c3.multiselect("Trader", trader_opt, default=trader_opt)
    structures = sorted(df["structure"].dropna().unique())
    struct = c4.multiselect("Structure", structures, default=structures)

    f = df[df["trade_status"].isin(status_opt) & df["product"].isin(prod) & df["trader_name"].isin(trader) & df["structure"].isin(struct)]
    display = excel_style_df(f)
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "Entry Idea": st.column_config.TextColumn(width="large"),
            "Exit Idea": st.column_config.TextColumn(width="large"),
            "Exit Reason": st.column_config.TextColumn(width="large"),
            "Remarks": st.column_config.TextColumn(width="large"),
            "Status": st.column_config.TextColumn(width="small"),
        },
    )
    st.download_button("Download trade data as CSV", display.to_csv(index=False).encode("utf-8"), "trade_data.csv", "text/csv")

    if not read_only:
        st.divider()
        manage_trade_panel(df)


def trade_entry_form():
    if "fill_count" not in st.session_state:
        st.session_state.fill_count = 1

    a, b, c, d = st.columns(4)
    trader_name = a.selectbox("Trader Name", TRADERS)
    product = b.selectbox("Product", PRODUCTS)
    structure = c.selectbox("Structure", STRUCTURES)
    direction = d.selectbox("Position", ["Long", "Short"])

    a, b, c, d = st.columns(4)
    contract_details = a.text_input("Strategy / Contract", placeholder="e.g. NG Apr27-May27-Jun27")
    entry_date = b.date_input("Open Date", value=date.today())
    expected_tick_move = c.number_input("Expected Tick Move", value=None, placeholder="Optional")
    trade_idea_source = d.text_input("Trade Idea / Source", placeholder="Optional")

    a, b = st.columns(2)
    target_price = a.number_input("Target Price", value=None, format="%.5f", placeholder="Optional")
    stop_price = b.number_input("Stop Price", value=None, format="%.5f", placeholder="Optional")

    st.markdown("**Entry fills**")
    fill_rows = []
    for i in range(st.session_state.fill_count):
        c1, c2, c3, c4 = st.columns([1.1, 1.1, .8, 2.0])
        fd = c1.date_input("Fill Date", value=entry_date, key=f"fd_{i}")
        fp = c2.number_input("Entry Price", format="%.5f", key=f"fp_{i}")
        fq = c3.number_input("Qty", min_value=0.0, step=1.0, key=f"fq_{i}")
        fn = c4.text_input("Fill Note", key=f"fn_{i}")
        fill_rows.append({"fill_date": fd.isoformat(), "price": fp, "quantity": fq, "note": fn})

    cadd, creset, _ = st.columns([1, 1, 5])
    if cadd.button("+ Add Fill", key="add_fill"):
        st.session_state.fill_count += 1
        st.rerun()
    if creset.button("Reset Fills", key="reset_fill"):
        st.session_state.fill_count = 1
        st.rerun()

    valid = [r for r in fill_rows if r["quantity"] > 0]
    if valid:
        total_qty = sum(r["quantity"] for r in valid)
        avg = sum(r["price"] * r["quantity"] for r in valid) / total_qty
        m1, m2 = st.columns(2)
        m1.metric("Total Quantity", f"{total_qty:g}")
        m2.metric("Weighted Avg Entry", f"{avg:.5f}")

    entry_idea = st.text_area("Entry Idea", height=130, placeholder="Write the full reason for entering the trade...")
    exit_idea = st.text_area(
        "Exit Idea",
        height=130,
        placeholder="Optional while LIVE — write your planned exit approach or leave blank until later...",
    )
    remarks = st.text_area("Remarks", height=80, placeholder="Optional additional notes")

    if st.button("Save Trade as LIVE", type="primary", use_container_width=True, key="save_new_trade"):
        if not entry_idea.strip():
            st.error("Entry Idea is required.")
        elif not valid:
            st.error("Add at least one entry fill with quantity greater than zero.")
        else:
            trade_id = create_trade({
                "trader_name": trader_name,
                "product": product,
                "structure": structure,
                "contract_details": contract_details.strip(),
                "direction": direction,
                "entry_date": entry_date.isoformat(),
                "expected_tick_move": expected_tick_move,
                "target_price": target_price,
                "stop_price": stop_price,
                "trade_idea_source": trade_idea_source.strip(),
                "entry_idea": entry_idea.strip(),
                "exit_idea": exit_idea.strip(),
                "remarks": remarks.strip(),
            }, valid)
            st.success(f"Trade #{trade_id} saved. Status = LIVE.")


def _as_date(value, fallback=None):
    if value is None or value == "":
        return fallback or date.today()
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return fallback or date.today()


def _fills_editor_data(fills: list[dict[str, Any]]) -> pd.DataFrame:
    if not fills:
        return pd.DataFrame([{"Fill Date": date.today(), "Entry Price": 0.0, "Qty": 1.0, "Fill Note": ""}])
    out = pd.DataFrame(fills)
    return pd.DataFrame({
        "Fill Date": pd.to_datetime(out["fill_date"], errors="coerce").dt.date,
        "Entry Price": pd.to_numeric(out["price"], errors="coerce"),
        "Qty": pd.to_numeric(out["quantity"], errors="coerce"),
        "Fill Note": out["note"].fillna(""),
    })


def _clean_editor_fills(editor_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for _, r in editor_df.iterrows():
        qty = pd.to_numeric(r.get("Qty"), errors="coerce")
        price = pd.to_numeric(r.get("Entry Price"), errors="coerce")
        fill_date = r.get("Fill Date")
        if pd.isna(qty) or float(qty) <= 0 or pd.isna(price) or fill_date is None or pd.isna(fill_date):
            continue
        if hasattr(fill_date, "date") and not isinstance(fill_date, date):
            fill_date = fill_date.date()
        rows.append({
            "fill_date": fill_date.isoformat() if hasattr(fill_date, "isoformat") else str(fill_date),
            "price": float(price),
            "quantity": float(qty),
            "note": str(r.get("Fill Note") or ""),
        })
    return rows


def manage_trade_panel(df: pd.DataFrame):
    st.markdown("### Edit / Close a Saved Trade")
    st.caption("Select any saved trade. LIVE and CLOSED trades can both be edited later; closing remains a separate action for LIVE trades.")

    labels = {
        int(r.id): f"#{int(r.id)} | {r.product} | {r.contract_details or r.structure} | {r.direction} | {r.trade_status}"
        for _, r in df.iterrows()
    }
    selected = st.selectbox("Select Saved Trade", list(labels), format_func=lambda x: labels[x])
    trade = get_trade(selected)
    fills = get_entry_fills(selected)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", trade["trade_status"])
    c2.metric("Qty", f"{trade['quantity']:g}")
    c3.metric("Avg Entry", f"{trade['average_entry']:.5f}")
    c4.metric("Expected Ticks", f"{trade['expected_tick_move'] or 0:g}")

    tab_names = ["Edit Trade"]
    if trade["trade_status"] == "LIVE":
        tab_names.append("Close Trade")
    tab_names.append("Delete")
    tabs = st.tabs(tab_names)

    with tabs[0]:
        st.markdown("#### Edit saved trade")
        a, b, c, d = st.columns(4)
        trader_idx = TRADERS.index(trade["trader_name"]) if trade["trader_name"] in TRADERS else 0
        product_idx = PRODUCTS.index(trade["product"]) if trade["product"] in PRODUCTS else 0
        structure_idx = STRUCTURES.index(trade["structure"]) if trade["structure"] in STRUCTURES else 0
        direction_idx = 0 if trade["direction"] == "Long" else 1
        trader_name = a.selectbox("Trader Name", TRADERS, index=trader_idx, key=f"edit_trader_{selected}")
        product = b.selectbox("Product", PRODUCTS, index=product_idx, key=f"edit_product_{selected}")
        structure = c.selectbox("Structure", STRUCTURES, index=structure_idx, key=f"edit_structure_{selected}")
        direction = d.selectbox("Position", ["Long", "Short"], index=direction_idx, key=f"edit_direction_{selected}")

        a, b, c, d = st.columns(4)
        contract_details = a.text_input("Strategy / Contract", value=trade.get("contract_details") or "", key=f"edit_contract_{selected}")
        entry_date = b.date_input("Open Date", value=_as_date(trade.get("entry_date")), key=f"edit_entry_date_{selected}")
        expected = c.number_input("Expected Tick Move", value=float(trade.get("expected_tick_move") or 0), key=f"edit_expected_{selected}")
        trade_idea_source = d.text_input("Trade Idea / Source", value=trade.get("trade_idea_source") or "", key=f"edit_source_{selected}")

        a, b = st.columns(2)
        target = a.number_input("Target Price", value=float(trade.get("target_price") or 0), format="%.5f", key=f"edit_target_{selected}")
        stop = b.number_input("Stop Price", value=float(trade.get("stop_price") or 0), format="%.5f", key=f"edit_stop_{selected}")

        st.markdown("**Edit entry fills**")
        edited_fills = st.data_editor(
            _fills_editor_data(fills),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"fills_editor_{selected}",
            column_config={
                "Fill Date": st.column_config.DateColumn(format="YYYY/MM/DD"),
                "Entry Price": st.column_config.NumberColumn(format="%.5f"),
                "Qty": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                "Fill Note": st.column_config.TextColumn(width="large"),
            },
        )

        entry_idea = st.text_area("Entry Idea", value=trade.get("entry_idea") or "", height=120, key=f"edit_entry_idea_{selected}")
        remarks = st.text_area("Remarks", value=trade.get("remarks") or "", height=80, key=f"edit_remarks_{selected}")

        edit_fields = {
            "trader_name": trader_name,
            "product": product,
            "structure": structure,
            "contract_details": contract_details.strip(),
            "direction": direction,
            "entry_date": entry_date.isoformat(),
            "expected_tick_move": expected,
            "target_price": target,
            "stop_price": stop,
            "trade_idea_source": trade_idea_source.strip(),
            "entry_idea": entry_idea.strip(),
            "remarks": remarks.strip(),
        }

        if trade["trade_status"] == "CLOSED":
            st.markdown("**Closed trade details**")
            a, b, c, d = st.columns(4)
            close_date = a.date_input("Close Date", value=_as_date(trade.get("exit_date")), key=f"edit_exit_date_{selected}")
            exit_price = b.number_input("Exit Price", value=float(trade.get("exit_price") or 0), format="%.5f", key=f"edit_exit_price_{selected}")
            ticks_result = c.number_input("PnL (Ticks)", value=float(trade.get("ticks_result") or 0), key=f"edit_ticks_{selected}")
            pnl = d.number_input("PnL ($)", value=float(trade.get("pnl") or 0), key=f"edit_pnl_{selected}")
            exit_idea = st.text_area("Exit Idea", value=trade.get("exit_idea") or "", height=120, key=f"edit_exit_idea_{selected}", placeholder="What was your thinking/plan around the exit?")
            exit_reason = st.text_area("Exit Reason", value=trade.get("exit_reason") or "", height=120, key=f"edit_exit_reason_{selected}", placeholder="Why was the trade actually closed?")
            edit_fields.update({
                "exit_date": close_date.isoformat(),
                "exit_price": exit_price,
                "ticks_result": ticks_result,
                "pnl": pnl,
                "exit_idea": exit_idea.strip(),
                "exit_reason": exit_reason.strip(),
            })

        if st.button("Save Edited Trade", type="primary", use_container_width=True, key=f"save_edit_{selected}"):
            clean_fills = _clean_editor_fills(edited_fills)
            if not entry_idea.strip():
                st.error("Entry Idea is required.")
            elif not clean_fills:
                st.error("Keep at least one entry fill with quantity greater than zero.")
            else:
                update_trade(selected, edit_fields, clean_fills)
                st.success(f"Trade #{selected} updated successfully.")
                st.rerun()

    next_tab = 1
    if trade["trade_status"] == "LIVE":
        with tabs[next_tab]:
            with st.form(f"close_trade_form_{selected}"):
                exit_date = st.date_input("Close Date", value=date.today())
                exit_price = st.number_input("Exit Price", format="%.5f")
                ticks_result = st.number_input("PnL (Ticks)", value=0.0, help="Use a negative number for a loss.")
                pnl = st.number_input("PnL ($)", value=0.0, help="Use a negative number for a loss.")
                exit_idea = st.text_area("Exit Idea", height=130, placeholder="Write your thinking/plan around the exit...")
                exit_reason = st.text_area("Exit Reason", height=130, placeholder="Write why the trade was actually closed...")
                exit_note = st.text_input("Exit Note", placeholder="Optional")
                if st.form_submit_button("Close Trade", type="primary"):
                    if not exit_idea.strip():
                        st.error("Exit Idea is required.")
                    elif not exit_reason.strip():
                        st.error("Exit Reason is required.")
                    else:
                        close_trade(selected, exit_date.isoformat(), exit_price, exit_idea.strip(), exit_reason.strip(), ticks_result, pnl, exit_note)
                        st.success(f"Trade #{selected} is now CLOSED.")
                        st.rerun()
        next_tab += 1

    with tabs[next_tab]:
        st.warning("This permanently deletes the selected trade.")
        confirm = st.checkbox("I understand", key=f"delete_confirm_{selected}")
        if st.button("Delete Trade", disabled=not confirm, key=f"delete_trade_{selected}"):
            delete_trade(selected)
            st.success("Trade deleted.")
            st.rerun()


def page_weekly(read_only: bool):
    st.markdown('<div class="sheet-title">02 — Weekly Review</div>', unsafe_allow_html=True)
    df = raw_df()
    today = date.today()
    iso = today.isocalendar()

    c1, c2 = st.columns(2)
    year = int(c1.number_input("Year", min_value=2020, max_value=2100, value=iso.year, step=1))
    week = int(c2.number_input("ISO Week", min_value=1, max_value=53, value=iso.week, step=1))

    if df.empty:
        st.info("No trade data yet.")
        weekly_notes_box(year, week, read_only)
        return

    basis = df["exit_date"].where(df["exit_date"].notna(), df["entry_date"])
    iso_parts = basis.dt.isocalendar()
    w = df[(iso_parts.year == year) & (iso_parts.week == week)].copy()

    if w.empty:
        st.info(f"No trades found for week {week}, {year}.")
        weekly_notes_box(year, week, read_only)
        return

    closed = w[w["trade_status"] == "CLOSED"].copy()
    total_pnl = closed["pnl"].sum(skipna=True)
    total_ticks = closed["ticks_result"].sum(skipna=True)
    win_rate = ((closed["ticks_result"] > 0).sum() / len(closed) * 100) if len(closed) else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Week", f"{year}-W{week:02d}")
    m2.metric("PnL ($)", f"{total_pnl:,.2f}")
    m3.metric("PnL (Ticks)", f"{total_ticks:,.1f}")
    m4.metric("Win Rate", f"{win_rate:.1f}%")

    if not closed.empty:
        left, right = st.columns(2)
        with left:
            st.markdown("**PnL by Strategy**")
            temp = closed.copy()
            temp["Strategy"] = temp["contract_details"].fillna("").where(temp["contract_details"].fillna("") != "", temp["structure"])
            by_strategy = temp.groupby("Strategy", as_index=False)["pnl"].sum().sort_values("pnl", ascending=False)
            by_strategy.columns = ["Strategy", "PnL ($)"]
            st.dataframe(by_strategy, use_container_width=True, hide_index=True)
        with right:
            st.markdown("**PnL by Day**")
            daily = closed.groupby(closed["exit_date"].dt.date, as_index=False)["pnl"].sum()
            daily.columns = ["Date", "PnL ($)"]
            st.dataframe(daily, use_container_width=True, hide_index=True)

        daily_chart = closed.groupby(closed["exit_date"].dt.date)["pnl"].sum().reset_index()
        daily_chart.columns = ["Date", "PnL ($)"]
        fig = px.bar(daily_chart, x="Date", y="PnL ($)", title="Daily PnL — Selected Week")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Trades in selected week**")
    st.dataframe(excel_style_df(w), use_container_width=True, hide_index=True, height=350)
    weekly_notes_box(year, week, read_only)


def weekly_notes_box(year: int, week: int, read_only: bool):
    st.divider()
    st.markdown("### Weekly Notes")
    existing = get_weekly_note(year, week)
    if read_only:
        st.text_area("Notes", value=existing, height=220, disabled=True)
    else:
        notes = st.text_area("Notes", value=existing, height=220, key=f"notes_{year}_{week}", placeholder="Write the week's observations, mistakes, lessons, execution notes and improvements...")
        if st.button("Save Weekly Notes", key=f"save_notes_{year}_{week}"):
            save_weekly_note(year, week, notes)
            st.success("Weekly notes saved.")


def page_monthly():
    st.markdown('<div class="sheet-title">03 — Monthly Review</div>', unsafe_allow_html=True)
    df = raw_df()
    if df.empty:
        st.info("No trade data yet.")
        return

    years = sorted(df["entry_date"].dt.year.dropna().astype(int).unique(), reverse=True)
    c1, c2 = st.columns(2)
    year = c1.selectbox("Year", years)
    month = c2.selectbox("Month", list(range(1, 13)), index=date.today().month - 1, format_func=lambda m: datetime(2000, m, 1).strftime("%B"))

    basis = df["exit_date"].where(df["exit_date"].notna(), df["entry_date"])
    m = df[(basis.dt.year == year) & (basis.dt.month == month)].copy()
    if m.empty:
        st.info("No trades found for the selected month.")
        return

    closed = m[m["trade_status"] == "CLOSED"].copy()
    pnl = closed["pnl"].sum(skipna=True)
    ticks = closed["ticks_result"].sum(skipna=True)
    wins = int((closed["ticks_result"] > 0).sum()) if not closed.empty else 0
    win_rate = wins / len(closed) * 100 if len(closed) else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Closed Trades", len(closed))
    k2.metric("Monthly PnL ($)", f"{pnl:,.2f}")
    k3.metric("Monthly Ticks", f"{ticks:,.1f}")
    k4.metric("Win Rate", f"{win_rate:.1f}%")

    if not closed.empty:
        closed["Strategy"] = closed["contract_details"].fillna("").where(closed["contract_details"].fillna("") != "", closed["structure"])
        strat = closed.groupby("Strategy", as_index=False)["pnl"].sum().sort_values("pnl", ascending=False)
        day = closed.groupby(closed["exit_date"].dt.date, as_index=False)["pnl"].sum()
        day.columns = ["Date", "PnL ($)"]
        day["Cumulative PnL ($)"] = day["PnL ($)"].cumsum()

        left, right = st.columns(2)
        with left:
            st.markdown("**PnL by Strategy**")
            st.dataframe(strat.rename(columns={"pnl": "PnL ($)"}), use_container_width=True, hide_index=True)
        with right:
            fig = px.line(day, x="Date", y="Cumulative PnL ($)", markers=True, title="Cumulative Monthly PnL")
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Daily PnL**")
        st.dataframe(day, use_container_width=True, hide_index=True)

    st.markdown("**Trades in selected month**")
    st.dataframe(excel_style_df(m), use_container_width=True, hide_index=True, height=350)


def page_weekly_notes(read_only: bool):
    st.markdown('<div class="sheet-title">Weekly Notes Archive</div>', unsafe_allow_html=True)
    today = date.today().isocalendar()
    c1, c2 = st.columns(2)
    year = int(c1.number_input("Year", min_value=2020, max_value=2100, value=today.year, step=1, key="archive_year"))
    week = int(c2.number_input("Week", min_value=1, max_value=53, value=today.week, step=1, key="archive_week"))
    weekly_notes_box(year, week, read_only)


def main():
    login()
    inject_css()

    mentor_mode = mentor_access_active()
    if mentor_mode:
        role = "Mentor"
        read_only = True
    else:
        role = st.session_state.get("role", "Trader")
        read_only = False

    with st.sidebar:
        st.markdown("## Trade Journal")
        if mentor_mode:
            st.caption("Mentor view")
        else:
            st.caption("Signed in as **Trader**")
        page = st.radio("Workbook", ["01 — Trade Data", "02 — Weekly Review", "03 — Monthly Review", "Weekly Notes"])
        st.divider()

        if mentor_mode:
            st.info("Mentor access is read-only. No trade or note can be changed from this view.")
        else:
            st.caption(f"Database: **{get_database_backend()}**")
            st.markdown("**Mentor access**")
            st.caption("Open this link, then copy the browser address and send it to your mentor. No username or password is required for that link.")
            st.markdown(f'[Open Mentor Read-Only View](?mentor={MENTOR_TOKEN})')
            st.caption("Keep this link private. Anyone with it can view the journal.")
            st.divider()
            if st.button("Logout", use_container_width=True):
                for key in ["auth", "role", "username"]:
                    st.session_state.pop(key, None)
                st.rerun()

    st.markdown('<div class="journal-title">Energy Trade Journal</div>', unsafe_allow_html=True)
    st.markdown('<div class="journal-sub">Excel-style trade log, weekly review and monthly performance journal</div>', unsafe_allow_html=True)

    if page == "01 — Trade Data":
        page_trade_log(read_only)
    elif page == "02 — Weekly Review":
        page_weekly(read_only)
    elif page == "03 — Monthly Review":
        page_monthly()
    else:
        page_weekly_notes(read_only)


if __name__ == "__main__":
    main()
